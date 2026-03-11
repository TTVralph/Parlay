from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import re

from .models import Leg
from .identity_resolution import get_canonical_player_identity, normalize_entity_name, resolve_player_identity
from .providers.base import EventInfo, ResultsProvider
from .services.nba_game_resolver import resolve_player_game

AMBIGUOUS_EVENT_WARNING = 'multiple games found for resolved team on date'
PLAYER_TEAM_UNRESOLVED_WARNING = 'team could not be resolved from player identity'
MISSING_BET_DATE_WARNING = 'Missing bet date'
MULTIPLE_POSSIBLE_GAMES_WARNING = 'Multiple possible games. Add bet date to narrow results.'
NO_TEAM_GAME_ON_SELECTED_DATE_WARNING = 'no game found for resolved team on date'
MULTIPLE_TEAM_GAMES_WARNING = 'multiple games found for resolved team on date'
TEAM_EVENT_MISMATCH_WARNING = 'Matched event does not include player team'

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _event_candidate_payload(event: EventInfo, *, match_confidence: str | None = None, reason: str | None = None) -> dict[str, object]:
    return {
        'event_id': event.event_id,
        'event_label': event.label,
        'event_date': event.start_time.date().isoformat(),
        'event_start_time': event.start_time.isoformat(),
        'home_team': event.home_team,
        'away_team': event.away_team,
        'match_confidence': match_confidence,
        'reason': reason,
    }


def _opponent_from_leg(leg: Leg) -> str | None:
    for note in leg.notes:
        if note.startswith('Opponent context: '):
            return note.split(':', 1)[1].strip() or None
    match = re.search(r'\sv(?:s|\.|ersus)\s+([a-z0-9 .\-]+)$', leg.raw_text, re.I)
    return match.group(1).strip() if match else None


def _filter_by_opponent(candidates: list[EventInfo], opponent: str | None) -> tuple[list[EventInfo], bool]:
    if not opponent:
        return candidates, False
    norm_opp = _norm(opponent)
    if not norm_opp:
        return candidates, False
    matched = []
    for event in candidates:
        home = _norm(event.home_team)
        away = _norm(event.away_team)
        if norm_opp in {home, away} or norm_opp in home or norm_opp in away or home in norm_opp or away in norm_opp:
            matched.append(event)
    return (matched or candidates), bool(matched)


def _event_matches_slip_date(event: EventInfo, slip_value: date | datetime | None) -> bool:
    if slip_value is None:
        return True
    if isinstance(slip_value, date) and not isinstance(slip_value, datetime):
        if event.start_time.date() == slip_value:
            return True
        if event.start_time.tzinfo is not None:
            return (event.start_time - timedelta(hours=8)).date() == slip_value
        return False

    event_time = event.start_time
    if slip_value.tzinfo is None:
        return event_time.date() == slip_value.date()
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return event_time.astimezone(slip_value.tzinfo).date() == slip_value.date()


def _filter_by_slip_date(candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    if slip_value is None:
        return candidates
    return [event for event in candidates if _event_matches_slip_date(event, slip_value)]


def _filter_by_slip_date_with_historical_fallback(
    candidates: list[EventInfo],
    slip_value: date | datetime | None,
    *,
    explicit_slip_date: date | None,
    include_historical: bool,
) -> list[EventInfo]:
    filtered = _filter_by_slip_date(candidates, slip_value)
    if filtered:
        return filtered
    if explicit_slip_date is not None:
        return filtered
    if isinstance(slip_value, datetime):
        return candidates
    if include_historical:
        return candidates
    return filtered

def _event_date_match_quality(event: EventInfo, slip_value: date | datetime | None) -> str:
    if slip_value is None:
        return 'unknown'
    slip_date = slip_value.date() if isinstance(slip_value, datetime) else slip_value
    delta = abs((event.start_time.date() - slip_date).days)
    if delta == 0:
        return 'exact'
    if delta <= 2:
        return 'nearby'
    return 'mismatch'


def _build_candidate_events(events: list[EventInfo], *, slip_value: date | datetime | None, reason: str) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for event in events[:5]:
        quality = _event_date_match_quality(event, slip_value)
        payload.append(_event_candidate_payload(event, match_confidence='medium' if quality in {'exact', 'nearby'} else 'low', reason=reason))
    return payload


def _event_contains_team(event: EventInfo, team: str | None) -> bool:
    if not team:
        return False
    norm_team = _norm(team)
    return norm_team in {_norm(event.home_team), _norm(event.away_team)}


def _context_date_for_leg(slip_value: date | datetime | None) -> date | None:
    if isinstance(slip_value, datetime):
        return slip_value.date()
    return slip_value


def _context_date_for_event(event: EventInfo, slip_value: date | datetime | None) -> date:
    context_date = _context_date_for_leg(slip_value)
    return context_date or event.start_time.date()


def _team_candidates(provider: ResultsProvider, team: str, posted_at: datetime | None, include_historical: bool) -> list[EventInfo]:
    resolver = getattr(provider, 'resolve_team_event_candidates', None)
    if callable(resolver):
        try:
            return resolver(team, posted_at, include_historical=include_historical)
        except TypeError:
            return resolver(team, posted_at)
    resolve_single = getattr(provider, 'resolve_team_event', None)
    if not callable(resolve_single):
        return []
    try:
        event = resolve_single(team, posted_at, include_historical=include_historical)
    except TypeError:
        event = resolve_single(team, posted_at)
    return [event] if event else []


def _player_candidates(provider: ResultsProvider, player: str, posted_at: datetime | None, include_historical: bool) -> list[EventInfo]:
    resolver = getattr(provider, 'resolve_player_event_candidates', None)
    if callable(resolver):
        try:
            return resolver(player, posted_at, include_historical=include_historical)
        except TypeError:
            return resolver(player, posted_at)
    try:
        event = provider.resolve_player_event(player, posted_at, include_historical=include_historical)
    except TypeError:
        event = provider.resolve_player_event(player, posted_at)
    return [event] if event else []


def _merge_player_and_team_candidates(
    player_candidates: list[EventInfo],
    team_candidates: list[EventInfo],
) -> list[EventInfo]:
    if not player_candidates:
        return team_candidates
    if not team_candidates:
        return player_candidates

    def _event_key(event: EventInfo) -> tuple[str, str]:
        return (event.event_id, event.start_time.isoformat())

    player_keys = {_event_key(event) for event in player_candidates}
    team_keys = {_event_key(event) for event in team_candidates}
    overlap = player_keys & team_keys
    if overlap:
        return [event for event in player_candidates if _event_key(event) in overlap]

    merged: list[EventInfo] = []
    seen: set[tuple[str, str]] = set()
    for event in [*player_candidates, *team_candidates]:
        key = _event_key(event)
        if key in seen:
            continue
        merged.append(event)
        seen.add(key)
    return merged


def _event_ids(events: list[EventInfo]) -> list[str]:
    return [event.event_id for event in events]


def _player_team_for_date(provider: ResultsProvider, player: str, posted_at: datetime | None, include_historical: bool) -> str | None:
    resolver = getattr(provider, 'resolve_player_team', None)
    if not callable(resolver):
        return None
    try:
        return resolver(player, posted_at, include_historical=include_historical)
    except TypeError:
        return resolver(player, posted_at)


def _resolve_player_team(provider: ResultsProvider, player: str, sport: str, posted_at: datetime | None, include_historical: bool) -> str | None:
    team_from_provider = _player_team_for_date(provider, player, posted_at, include_historical=include_historical)
    if team_from_provider:
        return team_from_provider
    resolution = resolve_player_identity(player, sport=sport)
    return resolution.resolved_team


def _infer_same_game_event(
    unresolved_legs: list[Leg],
    provider: ResultsProvider,
    anchor: datetime | None,
    include_historical: bool,
    slip_filter_value: date | datetime | None,
) -> str | None:
    team_event_counts: dict[str, int] = {}
    team_set = {(_norm(leg.resolved_team or '')) for leg in unresolved_legs if leg.resolved_team}
    team_set.discard('')
    if len(team_set) != 2:
        return None
    for leg in unresolved_legs:
        team = leg.resolved_team
        if not team:
            continue
        candidates = _team_candidates(provider, team, anchor, include_historical=include_historical)
        candidates = _filter_by_slip_date_with_historical_fallback(candidates, slip_filter_value, explicit_slip_date=None, include_historical=include_historical)
        for event in candidates:
            teams = {_norm(event.home_team), _norm(event.away_team)}
            if not teams.issubset(team_set):
                continue
            team_event_counts[event.event_id] = team_event_counts.get(event.event_id, 0) + 1
    if not team_event_counts:
        return None
    event_id, hits = max(team_event_counts.items(), key=lambda item: item[1])
    return event_id if hits >= 2 else None




def _rank_player_candidates_by_appearance(provider: ResultsProvider, player: str, candidates: list[EventInfo]) -> list[EventInfo]:
    appeared: list[EventInfo] = []
    unknown: list[EventInfo] = []
    for event in candidates:
        try:
            did_appear = provider.did_player_appear(player, event.event_id)
        except Exception:
            did_appear = None
        if did_appear is True:
            appeared.append(event)
        elif did_appear is None:
            unknown.append(event)
    if len(appeared) == 1:
        return appeared
    if appeared:
        return appeared + [event for event in candidates if event not in appeared]
    return unknown or candidates

def _resolution_confidence_for_leg(leg: Leg) -> str:
    if leg.event_id and not leg.event_resolution_warnings:
        return 'high'
    if leg.event_id:
        return 'medium'
    if 'ambiguous_event_match' in leg.event_resolution_warnings or 'multiple_candidate_events' in leg.event_resolution_warnings:
        return 'low'
    return 'low'


def resolve_leg_events(
    legs: list[Leg],
    provider: ResultsProvider,
    posted_at: date | datetime | None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
    selected_player_by_leg_id: dict[str, str] | None = None,
    bet_date: date | None = None,
    screenshot_default_date: date | None = None,
) -> list[Leg]:
    explicit_slip_date = bet_date
    slip_default_date = explicit_slip_date or screenshot_default_date or (posted_at if isinstance(posted_at, date) and not isinstance(posted_at, datetime) else None)
    slip_filter_value: date | datetime | None = slip_default_date or posted_at
    default_date_reason = (
        'explicit_slip_date_used' if explicit_slip_date else (
            'screenshot_date_used' if screenshot_default_date else (
                'screenshot_date_used' if isinstance(posted_at, date) and not isinstance(posted_at, datetime) else None
            )
        )
    )

    if isinstance(posted_at, datetime):
        anchor_input: datetime | None = posted_at
    elif slip_default_date is not None:
        anchor_input = datetime.combine(slip_default_date, datetime.min.time())
    else:
        anchor_input = None
    anchor = anchor_input

    resolved: list[Leg] = []
    resolved_event_ids: set[str] = set()
    resolved_team_event_ids: dict[str, set[str]] = {}
    resolved_team_date_event_ids: dict[tuple[str, date], set[str]] = {}

    for index, leg in enumerate(legs):
        updates: dict[str, object | None] = {}
        notes = list(leg.notes)
        resolution_warnings: list[str] = []
        candidates: list[EventInfo] = []
        opponent = _opponent_from_leg(leg)
        player_team: str | None = None
        player_identity_id: str | None = None
        resolved_player_name: str | None = None
        identity_source: str | None = None
        identity_last_refreshed_at: str | None = None
        resolved_team_hint: str | None = None
        selected_player_name: str | None = None
        selected_player_identity_id: str | None = None
        selection_source: str | None = None
        selection_explanation: str | None = None
        canonical_player_name: str | None = None
        directory_loaded = bool(resolve_player_identity('Nikola Jokic', sport=leg.sport).resolved_player_id) if leg.sport == 'NBA' else True
        normalized_lookup_key = normalize_entity_name(leg.player) if leg.player else None

        if default_date_reason:
            resolution_warnings.append(default_date_reason)

        leg_id = str(leg.leg_id) if leg.leg_id is not None else str(index)
        updates['leg_id'] = leg_id

        if leg.player:
            selected_player_id = (selected_player_by_leg_id or {}).get(leg_id)
            selected_player = get_canonical_player_identity(selected_player_id, sport=leg.sport)
            resolution = resolve_player_identity(leg.player, sport=leg.sport)
            updates['selection_applied'] = False
            updates['selection_error_code'] = None
            if selected_player_id:
                if selected_player is not None:
                    selected_player_name = selected_player.full_name
                    selected_player_identity_id = selected_player.canonical_player_id
                    selection_source = 'user_selected'
                    selection_explanation = f'Used user-selected player: {selected_player_name}'
                    resolution = resolve_player_identity(selected_player_name, sport=leg.sport)
                    updates['identity_match_method'] = 'manual_selection'
                    updates['identity_match_confidence'] = 'HIGH'
                    updates['resolution_confidence'] = 1.0
                    updates['selection_applied'] = True
                    notes.append('manual player selection applied')
                else:
                    updates['selection_error_code'] = 'INVALID_SELECTED_PLAYER_ID'
                    selection_source = 'user_selected'
                    selection_explanation = 'Selected player could not be applied because the player ID was not found in the active directory.'
                    notes.append('manual player selection invalid: player id not found in directory')
            if resolution.resolved_player_id:
                player_identity_id = resolution.resolved_player_id
                updates['resolution_confidence'] = updates.get('resolution_confidence') or resolution.confidence
            updates['identity_match_method'] = updates.get('identity_match_method') or resolution.match_method
            updates['identity_match_confidence'] = updates.get('identity_match_confidence') or resolution.confidence_level
            if resolution.confidence_level == 'LOW' and 'low confidence identity match requires review' not in notes:
                notes.append('low confidence identity match requires review')
            identity_source = resolution.identity_source
            identity_last_refreshed_at = resolution.identity_last_refreshed_at
            resolved_team_hint = resolution.resolved_team
            if resolution.ambiguity_reason:
                notes.append(resolution.ambiguity_reason)
                updates['resolution_ambiguity_reason'] = resolution.ambiguity_reason
                if resolution.candidate_players:
                    updates['candidate_players'] = list(resolution.candidate_players)
                    updates['candidate_player_details'] = [
                        {
                            'player_name': candidate.player_name,
                            'team_name': candidate.team_name,
                            'player_id': candidate.player_id,
                            'match_confidence': candidate.match_confidence,
                            'rank': candidate.rank,
                            'reason': candidate.reason,
                        }
                        for candidate in resolution.candidate_player_details
                    ]
                    notes.append(f"diagnostic: closest_directory_matches={', '.join(resolution.candidate_players)}")
            player_lookup_name = selected_player_name or resolution.resolved_player_name or leg.player
            resolved_player_name = player_lookup_name
            canonical_player_name = resolved_player_name
            player_team = _resolve_player_team(provider, player_lookup_name, leg.sport, anchor, include_historical)
            notes.append(f'diagnostic: parsed_player_name={leg.player}')
            notes.append(f'diagnostic: normalized_player_lookup_key={normalized_lookup_key}')
            notes.append(f'diagnostic: sport_directory_loaded={directory_loaded}')
            notes.append(f'diagnostic: directory_candidates={len(resolution.candidate_players) or (1 if resolution.resolved_player_id else 0)}')
            notes.append(f'diagnostic: resolved_player_name={resolved_player_name}')
            notes.append(f'diagnostic: resolved_player_id={player_identity_id}')
            notes.append(f'diagnostic: resolved_team={player_team}')
            notes.append(f'diagnostic: identity_source={identity_source}')
            notes.append(f'diagnostic: identity_last_refreshed_at={identity_last_refreshed_at}')
            notes.append(f'diagnostic: resolved_team_hint={resolved_team_hint}')

        if leg.market_type in {'moneyline', 'spread'} and leg.team:
            candidates = _team_candidates(provider, leg.team, anchor, include_historical=include_historical)
            updates['matched_by'] = 'team_schedule_lookup'
        elif leg.player:
            player_lookup_name = resolved_player_name or leg.player
            if leg.sport == 'NBA' and explicit_slip_date is not None:
                try:
                    resolved_game = resolve_player_game(player_lookup_name, explicit_slip_date.isoformat(), provider=provider)
                except Exception:
                    resolved_game = None
                if resolved_game is not None:
                    candidates = [EventInfo(event_id=resolved_game.event_id, sport=resolved_game.sport, home_team=resolved_game.home_team, away_team=resolved_game.away_team, start_time=resolved_game.start_time)]
                    updates['matched_by'] = 'player_identity_team_schedule_lookup'
                    resolution_warnings.append('player_team_date_lookup_used')

            if not candidates:
                candidates = _player_candidates(provider, player_lookup_name, anchor, include_historical=include_historical)

            notes.append(f'diagnostic: candidate_events_before_filtering={len(candidates)}')

            if leg.sport == 'NBA' and not player_team and PLAYER_TEAM_UNRESOLVED_WARNING not in notes:
                notes.append(PLAYER_TEAM_UNRESOLVED_WARNING)

            if player_team:
                team_candidates = _team_candidates(provider, player_team, anchor, include_historical=include_historical)
                candidates = _merge_player_and_team_candidates(candidates, team_candidates)
                pre_team_filter_count = len(candidates)
                candidates = [event for event in candidates if _event_contains_team(event, player_team)]
                if pre_team_filter_count > 0 and not candidates:
                    if TEAM_EVENT_MISMATCH_WARNING not in notes:
                        notes.append(TEAM_EVENT_MISMATCH_WARNING)
                    updates['resolution_confidence'] = min(float(updates.get('resolution_confidence') or leg.resolution_confidence or 1.0), 0.3)
                context_date = _context_date_for_leg(slip_filter_value)
                if context_date is not None:
                    team_day_links = resolved_team_date_event_ids.get((_norm(player_team), context_date), set())
                    if len(team_day_links) == 1:
                        candidates = [event for event in candidates if event.event_id in team_day_links] or candidates
                team_links = resolved_team_event_ids.get(_norm(player_team), set())
                if len(team_links) == 1:
                    candidates = [event for event in candidates if event.event_id in team_links] or candidates
                if explicit_slip_date is not None and not candidates:
                    if NO_TEAM_GAME_ON_SELECTED_DATE_WARNING not in notes:
                        notes.append(NO_TEAM_GAME_ON_SELECTED_DATE_WARNING)
                    resolution_warnings.append('no_candidate_events')

            candidates, opponent_used = _filter_by_opponent(candidates, opponent)
            if opponent_used:
                resolution_warnings.append('screenshot_matchup_used')
            notes.append(f'diagnostic: candidate_events_after_filtering={len(candidates)}')
            updates['matched_by'] = updates.get('matched_by') or 'player_boxscore_lookup'

        all_candidates_before_date_filter = list(candidates)
        nearby_candidates = [event for event in all_candidates_before_date_filter if _event_date_match_quality(event, slip_filter_value) == 'nearby']
        exact_candidates = [event for event in all_candidates_before_date_filter if _event_date_match_quality(event, slip_filter_value) == 'exact']
        candidates = _filter_by_slip_date_with_historical_fallback(
            candidates,
            slip_filter_value,
            explicit_slip_date=explicit_slip_date,
            include_historical=include_historical,
        )

        if leg.player and leg.sport == 'NBA' and player_team and explicit_slip_date is not None and not candidates:
            if NO_TEAM_GAME_ON_SELECTED_DATE_WARNING not in notes:
                notes.append(NO_TEAM_GAME_ON_SELECTED_DATE_WARNING)
            resolution_warnings.append('no_candidate_events')

        selected_for_leg = None
        selected_from_map = False
        if selected_event_by_leg_id:
            selected_for_leg = selected_event_by_leg_id.get(leg_id)
            selected_from_map = bool(selected_for_leg)
        if not selected_for_leg:
            selected_for_leg = selected_event_id

        updates['event_selection_applied'] = False
        updates['selected_event_id'] = selected_for_leg or None
        updates['selected_event_label'] = None
        updates['event_selection_source'] = 'auto'
        updates['event_selection_explanation'] = 'Used automatically matched game candidate.'

        if selected_for_leg:
            selected_pool = all_candidates_before_date_filter or candidates
            selected_only = [event for event in selected_pool if event.event_id == selected_for_leg]
            if selected_only:
                selected_event = selected_only[0]
                candidates = [selected_event]
                updates['event_selection_applied'] = True
                updates['selected_event_id'] = selected_event.event_id
                updates['selected_event_label'] = selected_event.label
                updates['event_selection_source'] = 'user_selected' if selected_from_map else 'auto'
                updates['event_selection_explanation'] = f"Used user-selected game override: {selected_event.label}" if selected_from_map else f"Used selected game override: {selected_event.label}"
                resolution_warnings = [warning for warning in resolution_warnings if warning not in {'multiple_candidate_events', 'ambiguous_event_match'}]
                notes.append(f'diagnostic: selected_event_override_applied={selected_event.event_id}')
            elif selected_from_map:
                updates['selection_error_code'] = 'INVALID_SELECTED_EVENT_ID'
                updates['event_selection_source'] = 'user_selected'
                updates['event_selection_explanation'] = 'Selected game could not be applied because the event ID was not found for this leg.'
                updates['event_resolution_status'] = 'review'
                updates['event_resolution_method'] = 'invalid_selected_event'
                updates['event_review_reason_code'] = 'invalid_selected_event_id'
                updates['event_review_reason_text'] = 'Selected game could not be applied; choose a listed game for this leg.'
                notes.append('manual event selection invalid: selected event id not found for leg')

        if leg.player and leg.sport == 'NBA' and len(candidates) > 1:
            ranked = _rank_player_candidates_by_appearance(provider, resolved_player_name or leg.player, candidates)
            if len(ranked) == 1:
                candidates = ranked
                resolution_warnings.append('player_appearance_used')
            else:
                candidates = ranked

        if resolved_event_ids:
            same_event_phrase = bool(re.search(r'\b(same\s*game\s*parlay|sgp|sgpx)\b', leg.raw_text, re.I))
            if same_event_phrase and len(resolved_event_ids) == 1:
                linked = [event for event in candidates if event.event_id in resolved_event_ids]
                if linked:
                    candidates = linked

        updates['selection_applied'] = bool(updates.get('selection_applied'))
        updates['selection_error_code'] = updates.get('selection_error_code')
        notes.append(f"diagnostic: selection_applied={updates['selection_applied']}")
        notes.append(f"diagnostic: selection_error_code={updates.get('selection_error_code') or 'none'}")
        notes.append(f"diagnostic: event_selection_applied={updates.get('event_selection_applied', False)}")
        updates['parsed_player_name'] = leg.parsed_player_name or leg.player
        updates['normalized_stat_type'] = leg.normalized_stat_type or leg.market_type
        updates['resolved_player_name'] = resolved_player_name
        updates['resolved_player_id'] = player_identity_id
        updates['selected_player_name'] = selected_player_name
        updates['selected_player_id'] = selected_player_identity_id
        updates['selection_source'] = selection_source or ('auto' if resolved_player_name else None)
        updates['selection_explanation'] = selection_explanation
        updates['canonical_player_name'] = canonical_player_name
        updates['resolved_team'] = player_team
        updates['identity_source'] = identity_source
        updates['identity_last_refreshed_at'] = identity_last_refreshed_at
        updates['identity_match_method'] = updates.get('identity_match_method')
        updates['identity_match_confidence'] = updates.get('identity_match_confidence')
        updates['resolved_team_hint'] = resolved_team_hint
        updates['selected_bet_date'] = explicit_slip_date.isoformat() if explicit_slip_date else None
        updates['slip_default_date'] = slip_default_date.isoformat() if slip_default_date else None
        updates['resolution_ambiguity_reason'] = updates.get('resolution_ambiguity_reason')
        updates['candidate_players'] = list(updates.get('candidate_players', []))
        updates['candidate_player_details'] = list(updates.get('candidate_player_details', []))
        updates['notes'] = notes

        if updates.get('selection_error_code') == 'INVALID_SELECTED_EVENT_ID':
            resolution_warnings.append('invalid_selected_event_id')
            updates['event_candidates'] = _build_candidate_events(candidates or all_candidates_before_date_filter, slip_value=slip_filter_value, reason='invalid selected game id')
            updates['event_resolution_warnings'] = list(dict.fromkeys(resolution_warnings))
            unresolved_leg = leg.model_copy(update=updates)
            updates['event_resolution_confidence'] = _resolution_confidence_for_leg(unresolved_leg)
            resolved.append(leg.model_copy(update=updates))
            continue

        if len(candidates) == 1:
            event = candidates[0]
            resolved_event_ids.add(event.event_id)
            if leg.team:
                resolved_team_event_ids.setdefault(_norm(leg.team), set()).add(event.event_id)
                resolved_team_date_event_ids.setdefault((_norm(leg.team), _context_date_for_event(event, slip_filter_value)), set()).add(event.event_id)
            if player_team:
                resolved_team_event_ids.setdefault(_norm(player_team), set()).add(event.event_id)
                resolved_team_date_event_ids.setdefault((_norm(player_team), _context_date_for_event(event, slip_filter_value)), set()).add(event.event_id)
            updates['event_id'] = event.event_id
            updates['event_label'] = event.label
            updates['event_start_time'] = event.start_time
            updates['selected_event_id'] = updates.get('selected_event_id') or event.event_id
            updates['selected_event_label'] = updates.get('selected_event_label') or event.label
            updates['event_selection_source'] = updates.get('event_selection_source') or 'auto'
            updates['event_selection_explanation'] = updates.get('event_selection_explanation') or ('Used user-selected game override.' if updates.get('event_selection_applied') else 'Used automatically matched game candidate.')
            updates['event_candidates'] = []
            updates['matched_event_id'] = event.event_id
            updates['matched_event_label'] = event.label
            updates['matched_event_date'] = event.start_time.date().isoformat()
            updates['matched_team'] = player_team or leg.team
            updates['event_resolution_status'] = 'resolved'
            updates['event_resolution_method'] = updates.get('matched_by') or 'event_lookup'
            updates['event_review_reason_code'] = None
            updates['event_review_reason_text'] = None
            updates['event_date_match_quality'] = _event_date_match_quality(event, slip_filter_value)
            updates['roster_validation_result'] = 'unknown'
            updates['event_resolution_warnings'] = list(dict.fromkeys(resolution_warnings))
            resolved_leg = leg.model_copy(update=updates)
            updates['event_resolution_confidence'] = _resolution_confidence_for_leg(resolved_leg)
            resolved.append(leg.model_copy(update=updates))
            continue

        if len(candidates) > 1:
            updates['event_candidates'] = _build_candidate_events(candidates, slip_value=slip_filter_value, reason='multiple plausible games for resolved player/date')
            resolution_warnings.extend(['multiple_candidate_events', 'ambiguous_event_match'])
            if AMBIGUOUS_EVENT_WARNING not in notes:
                notes.append(AMBIGUOUS_EVENT_WARNING)
            if leg.player and leg.sport == 'NBA':
                if slip_filter_value is None and MISSING_BET_DATE_WARNING not in notes:
                    notes.append(MISSING_BET_DATE_WARNING)
                if slip_filter_value is None and MULTIPLE_POSSIBLE_GAMES_WARNING not in notes:
                    notes.append(MULTIPLE_POSSIBLE_GAMES_WARNING)
                if MULTIPLE_TEAM_GAMES_WARNING not in notes:
                    notes.append(MULTIPLE_TEAM_GAMES_WARNING)
            updates['notes'] = notes
            updates['matched_by'] = None
            updates['event_resolution_status'] = 'review'
            updates['event_resolution_method'] = 'multi_candidate_review'
            updates['event_review_reason_code'] = 'multiple_plausible_events'
            updates['event_review_reason_text'] = 'Multiple plausible games were found for this player/date.'
            updates['event_date_match_quality'] = 'exact' if exact_candidates else ('nearby' if nearby_candidates else 'unknown')
            updates['roster_validation_result'] = 'unknown'
            updates['event_resolution_warnings'] = list(dict.fromkeys(resolution_warnings))
            updates['event_resolution_confidence'] = 'low'
            resolved.append(leg.model_copy(update=updates))
            continue

        if not candidates:
            resolution_warnings.append('no_candidate_events')
            updates['event_resolution_status'] = 'review'
            updates['event_resolution_method'] = 'no_event_match'
            updates['roster_validation_result'] = 'unknown'
            if nearby_candidates:
                updates['event_candidates'] = _build_candidate_events(nearby_candidates, slip_value=slip_filter_value, reason='nearby-date game; confirm slip date')
                updates['event_review_reason_code'] = 'nearby_date_candidates_only'
                updates['event_review_reason_text'] = 'Only nearby-date games were found; confirm the correct date.'
                updates['event_date_match_quality'] = 'nearby'
            else:
                updates['event_review_reason_code'] = 'no_matching_event_for_team_date'
                updates['event_review_reason_text'] = 'No matching game was found for the resolved team/date.'
                updates['event_date_match_quality'] = 'unknown'
        updates['event_resolution_warnings'] = list(dict.fromkeys(resolution_warnings))
        unresolved_leg = leg.model_copy(update=updates)
        updates['event_resolution_confidence'] = _resolution_confidence_for_leg(unresolved_leg)
        resolved.append(leg.model_copy(update=updates))

    non_total_event_ids = {leg.event_id for leg in resolved if leg.market_type != 'game_total' and leg.event_id}
    inferred_event = next(iter(non_total_event_ids)) if len(non_total_event_ids) == 1 else None
    unresolved_player_legs = [leg for leg in resolved if leg.sport == 'NBA' and leg.player and not leg.event_id]
    inferred_same_game_event_id = _infer_same_game_event(unresolved_player_legs, provider, anchor, include_historical, slip_filter_value)

    inferred_same_game_event: EventInfo | None = None
    if inferred_same_game_event_id:
        event_lookup = getattr(provider, 'get_event_info', None)
        if callable(event_lookup):
            inferred_same_game_event = event_lookup(inferred_same_game_event_id)
        if inferred_same_game_event is None:
            for leg in unresolved_player_legs:
                if not leg.resolved_team:
                    continue
                for event in _team_candidates(provider, leg.resolved_team, anchor, include_historical=include_historical):
                    if event.event_id == inferred_same_game_event_id:
                        inferred_same_game_event = event
                        break
                if inferred_same_game_event is not None:
                    break

    final_resolved: list[Leg] = []
    for leg in resolved:
        if leg.market_type == 'game_total' and not leg.event_id and inferred_event:
            donor = next(item for item in resolved if item.event_id == inferred_event)
            final_resolved.append(leg.model_copy(update={'event_id': donor.event_id, 'event_label': donor.event_label, 'event_start_time': donor.event_start_time, 'matched_by': 'ticket_event_inference', 'notes': list(leg.notes), 'event_candidates': [], 'matched_event_id': donor.event_id, 'matched_event_label': donor.event_label, 'matched_event_date': donor.event_start_time.date().isoformat() if donor.event_start_time else None, 'event_resolution_confidence': 'medium'}))
            continue
        if leg.event_id is None and inferred_same_game_event is not None and leg.player and leg.resolved_team:
            teams = {_norm(inferred_same_game_event.home_team), _norm(inferred_same_game_event.away_team)}
            if _norm(leg.resolved_team) in teams:
                notes = list(leg.notes)
                warnings = list(leg.event_resolution_warnings)
                warnings.append('same_game_team_cluster_inference')
                notes.append(f'diagnostic: shared_event_inference={inferred_same_game_event.event_id}')
                final_resolved.append(leg.model_copy(update={'event_id': inferred_same_game_event.event_id, 'event_label': inferred_same_game_event.label, 'event_start_time': inferred_same_game_event.start_time, 'matched_by': 'same_game_team_cluster_inference', 'event_candidates': [], 'notes': notes, 'matched_event_id': inferred_same_game_event.event_id, 'matched_event_label': inferred_same_game_event.label, 'matched_event_date': inferred_same_game_event.start_time.date().isoformat(), 'matched_team': leg.resolved_team, 'event_resolution_warnings': list(dict.fromkeys(warnings)), 'event_resolution_confidence': 'medium'}))
                continue
        if leg.event_id is None:
            notes = list(leg.notes)
            if 'Could not confidently resolve event/date for this leg' not in notes:
                notes.append('Could not confidently resolve event/date for this leg')
            final_resolved.append(leg.model_copy(update={'notes': notes, 'event_resolution_confidence': 'low'}))
            continue
        final_resolved.append(leg)

    event_dates = {leg.matched_event_date for leg in final_resolved if leg.matched_event_date}
    mixed_dates = len(event_dates) > 1
    out: list[Leg] = []
    for leg in final_resolved:
        warnings = list(leg.event_resolution_warnings)
        if mixed_dates and not leg.event_id:
            warnings.append('mixed_event_dates_detected')
        leg_updates: dict[str, object] = {
            'mixed_event_dates_detected': mixed_dates,
            'event_resolution_warnings': list(dict.fromkeys(warnings)),
        }
        if leg.event_id and not leg.event_resolution_status:
            leg_updates['event_resolution_status'] = 'resolved'
            leg_updates['event_resolution_method'] = leg.matched_by or 'event_lookup'
            leg_updates['event_review_reason_code'] = None
            leg_updates['event_review_reason_text'] = None
            leg_updates['event_date_match_quality'] = leg.event_date_match_quality or ('exact' if explicit_slip_date and leg.matched_event_date == explicit_slip_date.isoformat() else 'unknown')
            leg_updates['roster_validation_result'] = leg.roster_validation_result or 'unknown'
        out.append(leg.model_copy(update=leg_updates))
    return out

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import re

from .models import Leg
from .identity_resolution import normalize_entity_name, resolve_player_identity
from .providers.base import EventInfo, ResultsProvider

AMBIGUOUS_EVENT_WARNING = 'multiple games found for resolved team on date'
PLAYER_TEAM_UNRESOLVED_WARNING = 'team could not be resolved from player identity'
MISSING_BET_DATE_WARNING = 'Missing bet date'
MULTIPLE_POSSIBLE_GAMES_WARNING = 'Multiple possible games. Add bet date to narrow results.'
NO_TEAM_GAME_ON_SELECTED_DATE_WARNING = 'no game found for resolved team on date'
MULTIPLE_TEAM_GAMES_WARNING = 'multiple games found for resolved team on date'

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def _event_candidate_payload(event: EventInfo) -> dict[str, object]:
    return {
        'event_id': event.event_id,
        'event_label': event.label,
        'event_start_time': event.start_time.isoformat(),
    }


def _opponent_from_leg(leg: Leg) -> str | None:
    for note in leg.notes:
        if note.startswith('Opponent context: '):
            return note.split(':', 1)[1].strip() or None
    match = re.search(r'\sv(?:s|\.|ersus)\s+([a-z0-9 .\-]+)$', leg.raw_text, re.I)
    return match.group(1).strip() if match else None


def _filter_by_opponent(candidates: list[EventInfo], opponent: str | None) -> list[EventInfo]:
    if not opponent:
        return candidates
    norm_opp = _norm(opponent)
    if not norm_opp:
        return candidates
    matched = []
    for event in candidates:
        home = _norm(event.home_team)
        away = _norm(event.away_team)
        if norm_opp in {home, away} or norm_opp in home or norm_opp in away or home in norm_opp or away in norm_opp:
            matched.append(event)
    return matched or candidates


def _event_matches_slip_date(event: EventInfo, slip_value: date | datetime | None) -> bool:
    if slip_value is None:
        return True
    if isinstance(slip_value, date) and not isinstance(slip_value, datetime):
        if event.start_time.date() == slip_value:
            return True
        # ESPN start times are UTC and can roll to the next day for late US tipoffs.
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
    if team_candidates:
        return team_candidates
    return player_candidates


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


def resolve_leg_events(
    legs: list[Leg],
    provider: ResultsProvider,
    posted_at: date | datetime | None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
    bet_date: date | None = None,
) -> list[Leg]:
    explicit_slip_date = bet_date or (posted_at if isinstance(posted_at, date) and not isinstance(posted_at, datetime) else None)
    slip_filter_value: date | datetime | None = explicit_slip_date or posted_at
    anchor_input: datetime | None
    if isinstance(posted_at, datetime):
        anchor_input = posted_at
    elif explicit_slip_date is not None:
        anchor_input = datetime.combine(explicit_slip_date, datetime.min.time())
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
        candidates: list[EventInfo] = []
        opponent = _opponent_from_leg(leg)
        player_team: str | None = None
        player_identity_id: str | None = None
        resolved_player_name: str | None = None
        identity_source: str | None = None
        identity_last_refreshed_at: str | None = None
        resolved_team_hint: str | None = None
        directory_loaded = bool(resolve_player_identity('Nikola Jokic', sport=leg.sport).resolved_player_id) if leg.sport == 'NBA' else True
        normalized_lookup_key = normalize_entity_name(leg.player) if leg.player else None
        if leg.player:
            resolution = resolve_player_identity(leg.player, sport=leg.sport)
            if resolution.resolved_player_name and leg.player != resolution.resolved_player_name:
                updates['player'] = resolution.resolved_player_name
            if resolution.resolved_player_id:
                player_identity_id = resolution.resolved_player_id
                updates['resolution_confidence'] = resolution.confidence
            identity_source = resolution.identity_source
            identity_last_refreshed_at = resolution.identity_last_refreshed_at
            resolved_team_hint = resolution.resolved_team
            if resolution.ambiguity_reason:
                notes.append(resolution.ambiguity_reason)
                updates['resolution_ambiguity_reason'] = resolution.ambiguity_reason
                if resolution.candidate_players:
                    updates['candidate_players'] = list(resolution.candidate_players)
                    notes.append(f"diagnostic: closest_directory_matches={', '.join(resolution.candidate_players)}")
            player_lookup_name = str(updates.get('player', leg.player))
            resolved_player_name = player_lookup_name
            player_team = _resolve_player_team(provider, player_lookup_name, leg.sport, anchor, include_historical)
            logger.debug(
                'NBA prop player resolution: parsed_player=%s resolved_player=%s resolved_player_id=%s resolved_team=%s',
                leg.player,
                player_lookup_name,
                player_identity_id,
                player_team,
            )
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
            player_lookup_name = str(updates.get('player', leg.player))
            candidates = _player_candidates(provider, player_lookup_name, anchor, include_historical=include_historical)
            notes.append(f'diagnostic: candidate_events_before_filtering={len(candidates)}')
            logger.debug('NBA prop candidate games before team filtering: player=%s candidates=%s', player_lookup_name, _event_ids(candidates))
            if leg.sport == 'NBA' and not player_team and PLAYER_TEAM_UNRESOLVED_WARNING not in notes:
                notes.append(PLAYER_TEAM_UNRESOLVED_WARNING)

            if player_team:
                team_candidates = _team_candidates(provider, player_team, anchor, include_historical=include_historical)
                if explicit_slip_date is not None:
                    team_candidates = _filter_by_slip_date(team_candidates, explicit_slip_date)
                candidates = _merge_player_and_team_candidates(candidates, team_candidates)
                if explicit_slip_date is not None:
                    candidates = _filter_by_slip_date(candidates, explicit_slip_date)
                candidates = [event for event in candidates if _event_contains_team(event, player_team)]
                logger.debug(
                    'NBA prop candidate games after team filtering: player=%s team=%s candidates=%s',
                    player_lookup_name,
                    player_team,
                    _event_ids(candidates),
                )
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
            candidates = _filter_by_opponent(candidates, opponent)
            notes.append(f'diagnostic: candidate_events_after_filtering={len(candidates)}')
            updates['matched_by'] = 'player_boxscore_lookup'

        candidates = _filter_by_slip_date_with_historical_fallback(
            candidates,
            slip_filter_value,
            explicit_slip_date=explicit_slip_date,
            include_historical=include_historical,
        )
        if leg.player and leg.sport == 'NBA' and player_team and explicit_slip_date is not None and not candidates:
            if NO_TEAM_GAME_ON_SELECTED_DATE_WARNING not in notes:
                notes.append(NO_TEAM_GAME_ON_SELECTED_DATE_WARNING)

        selected_for_leg = None
        if selected_event_by_leg_id:
            selected_for_leg = selected_event_by_leg_id.get(str(index))
        if not selected_for_leg:
            selected_for_leg = selected_event_id

        if selected_for_leg:
            selected_only = [event for event in candidates if event.event_id == selected_for_leg]
            if selected_only:
                candidates = selected_only

        if resolved_event_ids:
            same_event_phrase = bool(re.search(r'\b(same\s*game\s*parlay|sgp|sgpx)\b', leg.raw_text, re.I))
            if same_event_phrase and len(resolved_event_ids) == 1:
                linked = [event for event in candidates if event.event_id in resolved_event_ids]
                if linked:
                    candidates = linked

        updates['parsed_player_name'] = leg.parsed_player_name or leg.player
        updates['normalized_stat_type'] = leg.normalized_stat_type or leg.market_type
        updates['resolved_player_name'] = resolved_player_name
        updates['resolved_player_id'] = player_identity_id
        updates['resolved_team'] = player_team
        updates['identity_source'] = identity_source
        updates['identity_last_refreshed_at'] = identity_last_refreshed_at
        updates['resolved_team_hint'] = resolved_team_hint
        updates['selected_bet_date'] = explicit_slip_date.isoformat() if explicit_slip_date else None
        updates['resolution_ambiguity_reason'] = updates.get('resolution_ambiguity_reason')
        updates['candidate_players'] = list(updates.get('candidate_players', []))
        updates['notes'] = notes

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
            updates['event_candidates'] = []
            logger.debug('NBA prop final selected game: player=%s selected=%s', leg.player, event.event_id)
            resolved.append(leg.model_copy(update=updates))
            continue

        if len(candidates) > 1:
            updates['event_candidates'] = [_event_candidate_payload(event) for event in candidates[:5]]
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
            logger.debug('NBA prop final selected game: player=%s selected=%s reason=ambiguous candidates=%s', leg.player, None, _event_ids(candidates))
            resolved.append(leg.model_copy(update=updates))
            continue

        resolved.append(leg.model_copy(update=updates))

    # Second pass: infer event for game totals from other legs when the ticket appears to target one game.
    non_total_event_ids = {leg.event_id for leg in resolved if leg.market_type != 'game_total' and leg.event_id}
    inferred_event = next(iter(non_total_event_ids)) if len(non_total_event_ids) == 1 else None
    final_resolved: list[Leg] = []
    for leg in resolved:
        if leg.market_type == 'game_total' and not leg.event_id and inferred_event:
            donor = next(item for item in resolved if item.event_id == inferred_event)
            final_resolved.append(
                leg.model_copy(
                    update={
                        'event_id': donor.event_id,
                        'event_label': donor.event_label,
                        'event_start_time': donor.event_start_time,
                        'matched_by': 'ticket_event_inference',
                        'notes': list(leg.notes),
                        'event_candidates': [],
                    }
                )
            )
            continue
        if leg.event_id is None:
            notes = list(leg.notes)
            if 'Could not confidently resolve event/date for this leg' not in notes:
                notes.append('Could not confidently resolve event/date for this leg')
            final_resolved.append(leg.model_copy(update={'notes': notes}))
            continue
        final_resolved.append(leg)
    return final_resolved

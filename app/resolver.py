from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

from .models import Leg
from .providers.base import EventInfo, ResultsProvider

AMBIGUOUS_EVENT_WARNING = 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'


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
    if include_historical:
        return candidates
    return filtered

def _event_contains_team(event: EventInfo, team: str | None) -> bool:
    if not team:
        return False
    norm_team = _norm(team)
    return norm_team in {_norm(event.home_team), _norm(event.away_team)}


def _team_candidates(provider: ResultsProvider, team: str, posted_at: datetime | None, include_historical: bool) -> list[EventInfo]:
    resolver = getattr(provider, 'resolve_team_event_candidates', None)
    if callable(resolver):
        try:
            return resolver(team, posted_at, include_historical=include_historical)
        except TypeError:
            return resolver(team, posted_at)
    try:
        event = provider.resolve_team_event(team, posted_at, include_historical=include_historical)
    except TypeError:
        event = provider.resolve_team_event(team, posted_at)
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


def _player_team_for_date(provider: ResultsProvider, player: str, posted_at: datetime | None, include_historical: bool) -> str | None:
    resolver = getattr(provider, 'resolve_player_team', None)
    if not callable(resolver):
        return None
    try:
        return resolver(player, posted_at, include_historical=include_historical)
    except TypeError:
        return resolver(player, posted_at)


def _resolve_anchor(posted_at: datetime | None) -> datetime:
    if posted_at is not None:
        return posted_at
    return datetime.utcnow()


def resolve_leg_events(
    legs: list[Leg],
    provider: ResultsProvider,
    posted_at: date | datetime | None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
) -> list[Leg]:
    explicit_slip_date = posted_at if isinstance(posted_at, date) and not isinstance(posted_at, datetime) else None
    slip_filter_value: date | datetime | None = explicit_slip_date or posted_at
    anchor_input: datetime | None
    if isinstance(posted_at, datetime):
        anchor_input = posted_at
    elif explicit_slip_date is not None:
        anchor_input = datetime.combine(explicit_slip_date, datetime.min.time())
    else:
        anchor_input = None
    anchor = _resolve_anchor(anchor_input)
    locked_event: EventInfo | None = None
    lock_failed = False
    moneyline_legs = [leg for leg in legs if leg.market_type == 'moneyline' and leg.team]
    for ml_leg in moneyline_legs:
        ml_candidates = _team_candidates(provider, ml_leg.team or '', anchor, include_historical=include_historical)
        ml_candidates = _filter_by_slip_date_with_historical_fallback(
            ml_candidates,
            slip_filter_value,
            explicit_slip_date=explicit_slip_date,
            include_historical=include_historical,
        )
        if selected_event_id:
            ml_candidates = [event for event in ml_candidates if event.event_id == selected_event_id]
        if len(ml_candidates) == 1:
            locked_event = ml_candidates[0]
            break
        if explicit_slip_date is not None and not ml_candidates:
            lock_failed = True
            break

    shared_event: EventInfo | None = None
    resolved: list[Leg] = []
    for leg in legs:
        updates: dict[str, object | None] = {}
        notes = list(leg.notes)
        candidates: list[EventInfo] = []
        opponent = _opponent_from_leg(leg)
        player_team: str | None = None
        if leg.player:
            player_team = _player_team_for_date(provider, leg.player, anchor, include_historical=include_historical)

        if locked_event is not None:
            if leg.market_type in {'moneyline', 'spread'} and _event_contains_team(locked_event, leg.team):
                candidates = [locked_event]
            elif leg.market_type in {'player_points', 'player_assists', 'player_rebounds', 'player_threes', 'game_total'}:
                if player_team is None or _event_contains_team(locked_event, player_team):
                    candidates = [locked_event]
        elif leg.market_type in {'moneyline', 'spread'} and leg.team:
            candidates = _team_candidates(provider, leg.team, anchor, include_historical=include_historical)
            updates['matched_by'] = 'team_schedule_lookup'
        elif leg.player:
            candidates = _player_candidates(provider, leg.player, anchor, include_historical=include_historical)
            if explicit_slip_date is not None:
                candidates = _filter_by_slip_date_with_historical_fallback(
                    candidates,
                    slip_filter_value,
                    explicit_slip_date=explicit_slip_date,
                    include_historical=include_historical,
                )
            if player_team:
                candidates = [event for event in candidates if _event_contains_team(event, player_team)]
            candidates = _filter_by_opponent(candidates, opponent)
            if opponent is None:
                candidates = _filter_by_slip_date_with_historical_fallback(
                    candidates,
                    slip_filter_value,
                    explicit_slip_date=explicit_slip_date,
                    include_historical=include_historical,
                )
            updates['matched_by'] = 'player_boxscore_lookup'

        if not leg.player:
            candidates = _filter_by_slip_date_with_historical_fallback(
                candidates,
                slip_filter_value,
                explicit_slip_date=explicit_slip_date,
                include_historical=include_historical,
            )

        if lock_failed:
            candidates = []


        if selected_event_id:
            selected_only = [event for event in candidates if event.event_id == selected_event_id]
            if selected_only:
                candidates = selected_only

        if shared_event is not None:
            linked = [event for event in candidates if event.event_id == shared_event.event_id]
            if linked:
                candidates = linked

        if len(candidates) == 1:
            event = candidates[0]
            shared_event = shared_event or event
            updates['event_id'] = event.event_id
            updates['event_label'] = event.label
            updates['event_start_time'] = event.start_time
            updates['event_candidates'] = []
            resolved.append(leg.model_copy(update=updates))
            continue

        if len(candidates) > 1:
            updates['event_candidates'] = [_event_candidate_payload(event) for event in candidates[:5]]
            if AMBIGUOUS_EVENT_WARNING not in notes:
                notes.append(AMBIGUOUS_EVENT_WARNING)
            updates['notes'] = notes
            updates['matched_by'] = None
            resolved.append(leg.model_copy(update=updates))
            continue

        resolved.append(leg)

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

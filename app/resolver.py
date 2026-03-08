from __future__ import annotations

from datetime import datetime
import re

from .models import Leg
from .providers.base import EventInfo, ResultsProvider

AMBIGUOUS_EVENT_WARNING = 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


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


def _team_candidates(provider: ResultsProvider, team: str, posted_at: datetime | None) -> list[EventInfo]:
    resolver = getattr(provider, 'resolve_team_event_candidates', None)
    if callable(resolver):
        return resolver(team, posted_at)
    event = provider.resolve_team_event(team, posted_at)
    return [event] if event else []


def _player_candidates(provider: ResultsProvider, player: str, posted_at: datetime | None) -> list[EventInfo]:
    resolver = getattr(provider, 'resolve_player_event_candidates', None)
    if callable(resolver):
        return resolver(player, posted_at)
    event = provider.resolve_player_event(player, posted_at)
    return [event] if event else []


def resolve_leg_events(legs: list[Leg], provider: ResultsProvider, posted_at: datetime | None) -> list[Leg]:
    resolved: list[Leg] = []
    for leg in legs:
        updates: dict[str, object | None] = {}
        notes = list(leg.notes)
        candidates: list[EventInfo] = []
        opponent = _opponent_from_leg(leg)
        if leg.market_type in {'moneyline', 'spread'} and leg.team:
            candidates = _team_candidates(provider, leg.team, posted_at)
            updates['matched_by'] = 'team_schedule_lookup'
        elif leg.player:
            candidates = _player_candidates(provider, leg.player, posted_at)
            candidates = _filter_by_opponent(candidates, opponent)
            updates['matched_by'] = 'player_boxscore_lookup'

        if len(candidates) == 1:
            event = candidates[0]
            updates['event_id'] = event.event_id
            updates['event_label'] = event.label
            updates['event_start_time'] = event.start_time
            resolved.append(leg.model_copy(update=updates))
            continue

        if len(candidates) > 1 and AMBIGUOUS_EVENT_WARNING not in notes:
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

from __future__ import annotations

from datetime import datetime

from .models import Leg
from .providers.base import ResultsProvider


def resolve_leg_events(legs: list[Leg], provider: ResultsProvider, posted_at: datetime | None) -> list[Leg]:
    resolved: list[Leg] = []
    for leg in legs:
        updates: dict[str, object | None] = {}
        event = None
        if leg.market_type in {'moneyline', 'spread'} and leg.team:
            event = provider.resolve_team_event(leg.team, posted_at)
            updates['matched_by'] = 'team_schedule_lookup'
        elif leg.player:
            event = provider.resolve_player_event(leg.player, posted_at)
            updates['matched_by'] = 'player_boxscore_lookup'

        if event is not None:
            updates['event_id'] = event.event_id
            updates['event_label'] = event.label
            updates['event_start_time'] = event.start_time
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
            notes.append('Could not confidently resolve event/date for this leg')
            final_resolved.append(leg.model_copy(update={'notes': notes}))
            continue
        final_resolved.append(leg)
    return final_resolved

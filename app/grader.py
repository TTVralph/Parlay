from __future__ import annotations

from datetime import datetime

from .models import GradeResponse, GradedLeg, Leg
from .providers.base import ResultsProvider
from .providers.factory import get_results_provider
from .resolver import resolve_leg_events
from .parser import parse_text


def settle_leg(leg: Leg, provider: ResultsProvider) -> GradedLeg:
    if leg.confidence < 0.75:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Low-confidence parse; send to manual review')

    if not leg.event_id:
        return GradedLeg(leg=leg, settlement='unmatched', reason='No event resolved from post timestamp / schedule lookup')

    if leg.market_type in {'moneyline', 'spread', 'game_total'}:
        team_key = leg.team
        lookup_team = team_key
        if leg.market_type == 'game_total' and not lookup_team:
            # use either team from event by querying any team result from labels once event already resolved
            event_label = leg.event_label or ''
            if ' @ ' in event_label:
                away, home = event_label.split(' @ ', 1)
                lookup_team = home
        if not lookup_team:
            return GradedLeg(leg=leg, settlement='unmatched', reason='No team/event context identified')
        team_result = provider.get_team_result(lookup_team, event_id=leg.event_id)
        if not team_result:
            return GradedLeg(leg=leg, settlement='unmatched', reason='No team result found for resolved event')

        if leg.market_type == 'moneyline':
            won = team_result.moneyline_win if leg.team == lookup_team else provider.get_team_result(leg.team or '', event_id=leg.event_id).moneyline_win  # type: ignore[union-attr]
            return GradedLeg(
                leg=leg,
                settlement='win' if won else 'loss',
                actual_value=1 if won else 0,
                reason=f'{leg.team} in {team_result.event.label}: ' + ('team won game' if won else 'team lost game'),
            )

        if leg.market_type == 'spread':
            if not leg.team or leg.line is None:
                return GradedLeg(leg=leg, settlement='unmatched', reason='Missing team or line for spread settlement')
            margin = team_result.team_margin(leg.team)
            covered_value = margin + leg.line
            if covered_value == 0:
                return GradedLeg(leg=leg, settlement='push', actual_value=float(margin), reason=f'{leg.team} margin {margin} landed exactly on spread {leg.line}')
            won = covered_value > 0
            return GradedLeg(leg=leg, settlement='win' if won else 'loss', actual_value=float(margin), reason=f'{leg.team} margin {margin} vs spread {leg.line} in {team_result.event.label}')

        if leg.market_type == 'game_total':
            if leg.line is None or leg.direction is None:
                return GradedLeg(leg=leg, settlement='unmatched', reason='Missing total line or direction')
            total_points = team_result.total_points
            if total_points == leg.line:
                return GradedLeg(leg=leg, settlement='push', actual_value=float(total_points), reason='Game total landed exactly on line')
            won = total_points > leg.line if leg.direction == 'over' else total_points < leg.line
            return GradedLeg(leg=leg, settlement='win' if won else 'loss', actual_value=float(total_points), reason=f'Game total {total_points} vs {leg.direction} {leg.line} in {team_result.event.label}')

    if not leg.player:
        return GradedLeg(leg=leg, settlement='unmatched', reason='No player identified')

    actual_value = provider.get_player_result(leg.player, leg.market_type, event_id=leg.event_id)
    if actual_value is None or leg.line is None or leg.direction is None:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Missing values required for settlement')

    if leg.direction == 'over':
        won = actual_value > leg.line
        if actual_value == leg.line:
            return GradedLeg(leg=leg, settlement='push', actual_value=actual_value, reason='Landed exactly on line')
    else:
        won = actual_value < leg.line
        if actual_value == leg.line:
            return GradedLeg(leg=leg, settlement='push', actual_value=actual_value, reason='Landed exactly on line')

    return GradedLeg(
        leg=leg,
        settlement='win' if won else 'loss',
        actual_value=float(actual_value),
        reason=f'{leg.player} in {leg.event_label}: actual {actual_value} vs line {leg.line}',
    )



def grade_text(text: str, provider: ResultsProvider | None = None, posted_at: datetime | None = None) -> GradeResponse:
    provider = provider or get_results_provider()
    legs = parse_text(text)
    resolved_legs = resolve_leg_events(legs, provider, posted_at)
    graded = [settle_leg(leg, provider) for leg in resolved_legs]

    settlements = {item.settlement for item in graded}
    if 'loss' in settlements:
        overall = 'lost'
    elif 'unmatched' in settlements:
        overall = 'needs_review'
    elif settlements <= {'win', 'push'}:
        overall = 'cashed'
    else:
        overall = 'pending'

    return GradeResponse(overall=overall, legs=graded)

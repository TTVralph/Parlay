from __future__ import annotations

from datetime import datetime

from .models import GradeResponse, GradedLeg, Leg
from .providers.base import ResultsProvider
from .providers.factory import get_results_provider
from .event_matcher import resolve_leg_events
from .parser import parse_text


_SUPPORTED_NBA_MARKETS = {
    'moneyline',
    'player_points',
    'player_assists',
    'player_rebounds',
    'player_threes',
    'player_pra',
    'player_pr',
    'player_pa',
    'player_ra',
}

_COMBO_COMPONENTS = {
    'player_pra': ('player_points', 'player_rebounds', 'player_assists'),
    'player_pr': ('player_points', 'player_rebounds'),
    'player_pa': ('player_points', 'player_assists'),
    'player_ra': ('player_rebounds', 'player_assists'),
}


_MARKET_LABELS = {
    'moneyline': 'Moneyline',
    'spread': 'Spread',
    'game_total': 'Game Total',
    'player_points': 'Points',
    'player_rebounds': 'Rebounds',
    'player_assists': 'Assists',
    'player_threes': 'Threes Made',
    'player_pra': 'PRA',
    'player_pr': 'PR',
    'player_pa': 'PA',
    'player_ra': 'RA',
    'player_passing_yards': 'Passing Yards',
    'player_rushing_yards': 'Rushing Yards',
    'player_receiving_yards': 'Receiving Yards',
    'player_hits': 'Hits',
}

_COMPONENT_LABELS = {
    'player_points': 'Points',
    'player_rebounds': 'Rebounds',
    'player_assists': 'Assists',
}


def _base_leg_kwargs(leg: Leg) -> dict:
    return {
        'matched_event': leg.event_label,
        'line': leg.line,
        'normalized_market': _MARKET_LABELS.get(leg.market_type, leg.market_type),
        'candidate_games': leg.event_candidates,
    }


def _event_status(provider: ResultsProvider, event_id: str | None) -> str | None:
    if not event_id:
        return None
    status_fn = getattr(provider, 'get_event_status', None)
    if callable(status_fn):
        try:
            return status_fn(event_id)
        except Exception:
            return None
    return None

def settle_leg(leg: Leg, provider: ResultsProvider) -> GradedLeg:
    base_kwargs = _base_leg_kwargs(leg)
    if leg.confidence < 0.75:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Low-confidence parse; send to manual review', explanation_reason='Low-confidence parse; send to manual review', **base_kwargs)

    if not leg.event_id:
        reason = 'event unresolved'
        if len(leg.event_candidates) > 1:
            reason = 'multiple candidate games'
        return GradedLeg(leg=leg, settlement='unmatched', reason='No event resolved from post timestamp / schedule lookup', explanation_reason=reason, **base_kwargs)

    if leg.sport == 'NBA' and leg.market_type not in _SUPPORTED_NBA_MARKETS:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Unsupported NBA bet type for ESPN-backed grading', explanation_reason='stat unavailable', **base_kwargs)

    if leg.market_type in {'moneyline', 'spread', 'game_total'}:
        team_key = leg.team
        lookup_team = team_key
        if leg.market_type == 'game_total' and not lookup_team:
            event_label = leg.event_label or ''
            if ' @ ' in event_label:
                _, home = event_label.split(' @ ', 1)
                lookup_team = home
        if not lookup_team:
            return GradedLeg(leg=leg, settlement='unmatched', reason='No team/event context identified', explanation_reason='no valid same-team game found', **base_kwargs)
        team_result = provider.get_team_result(lookup_team, event_id=leg.event_id)
        if not team_result:
            status = _event_status(provider, leg.event_id)
            if status == 'live':
                return GradedLeg(leg=leg, settlement='pending', reason='Game is in progress', explanation_reason='event unresolved', **base_kwargs)
            return GradedLeg(leg=leg, settlement='unmatched', reason='Could not verify team result from trusted data source', explanation_reason='event unresolved', **base_kwargs)

        if leg.market_type == 'moneyline':
            won = team_result.moneyline_win if leg.team == lookup_team else provider.get_team_result(leg.team or '', event_id=leg.event_id).moneyline_win  # type: ignore[union-attr]
            return GradedLeg(leg=leg, settlement='win' if won else 'loss', actual_value=1 if won else 0, reason=f'{leg.team} in {team_result.event.label}: ' + ('team won game' if won else 'team lost game'), explanation_reason='event resolved', **base_kwargs)

        if leg.market_type == 'spread':
            if not leg.team or leg.line is None:
                return GradedLeg(leg=leg, settlement='unmatched', reason='Missing team or line for spread settlement', explanation_reason='stat unavailable', **base_kwargs)
            margin = team_result.team_margin(leg.team)
            covered_value = margin + leg.line
            if covered_value == 0:
                return GradedLeg(leg=leg, settlement='push', actual_value=float(margin), reason=f'{leg.team} margin {margin} landed exactly on spread {leg.line}', explanation_reason='event resolved', **base_kwargs)
            won = covered_value > 0
            return GradedLeg(leg=leg, settlement='win' if won else 'loss', actual_value=float(margin), reason=f'{leg.team} margin {margin} vs spread {leg.line} in {team_result.event.label}', explanation_reason='event resolved', **base_kwargs)

        if leg.market_type == 'game_total':
            if leg.line is None or leg.direction is None:
                return GradedLeg(leg=leg, settlement='unmatched', reason='Missing total line or direction', explanation_reason='stat unavailable', **base_kwargs)
            total_points = team_result.total_points
            if total_points == leg.line:
                return GradedLeg(leg=leg, settlement='push', actual_value=float(total_points), reason='Game total landed exactly on line', explanation_reason='event resolved', **base_kwargs)
            won = total_points > leg.line if leg.direction == 'over' else total_points < leg.line
            return GradedLeg(leg=leg, settlement='win' if won else 'loss', actual_value=float(total_points), reason=f'Game total {total_points} vs {leg.direction} {leg.line} in {team_result.event.label}', explanation_reason='event resolved', **base_kwargs)

    if not leg.player:
        return GradedLeg(leg=leg, settlement='unmatched', reason='No player identified', explanation_reason='player identity ambiguous', **base_kwargs)

    actual_value = provider.get_player_result(leg.player, leg.market_type, event_id=leg.event_id)
    component_values_dict = None
    if leg.market_type in _COMBO_COMPONENTS:
        component_values_dict = {}
        for component_market in _COMBO_COMPONENTS[leg.market_type]:
            component_value = provider.get_player_result(leg.player, component_market, event_id=leg.event_id)
            if component_value is None:
                component_values_dict = None
                break
            component_values_dict[_COMPONENT_LABELS.get(component_market, component_market)] = float(component_value)
        if actual_value is None and component_values_dict:
            actual_value = float(sum(component_values_dict.values()))
    if leg.line is None or leg.direction is None:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Missing values required for settlement', explanation_reason='stat unavailable', component_values=component_values_dict, **base_kwargs)
    if actual_value is None:
        status = _event_status(provider, leg.event_id)
        if status == 'live':
            return GradedLeg(leg=leg, settlement='pending', reason='Game is in progress', explanation_reason='event unresolved', component_values=component_values_dict, **base_kwargs)
        did_appear_fn = getattr(provider, 'did_player_appear', None)
        appeared = None
        if callable(did_appear_fn):
            try:
                appeared = did_appear_fn(leg.player, event_id=leg.event_id)
            except TypeError:
                appeared = did_appear_fn(leg.player, leg.event_id)
            except Exception:
                appeared = None
            if appeared is False:
                return GradedLeg(leg=leg, settlement='void', reason=f'{leg.player} did not appear in box score (DNP)', explanation_reason='player did not appear in box score / game log', player_found_in_boxscore=False, component_values=component_values_dict, **base_kwargs)
        return GradedLeg(leg=leg, settlement='unmatched', reason='Could not verify player stat from trusted data source', explanation_reason='stat unavailable', player_found_in_boxscore=appeared, component_values=component_values_dict, **base_kwargs)

    if leg.direction == 'over':
        won = actual_value > leg.line
        if actual_value == leg.line:
            return GradedLeg(leg=leg, settlement='push', actual_value=actual_value, reason='Landed exactly on line', explanation_reason='event resolved', component_values=component_values_dict, **base_kwargs)
    else:
        won = actual_value < leg.line
        if actual_value == leg.line:
            return GradedLeg(leg=leg, settlement='push', actual_value=actual_value, reason='Landed exactly on line', explanation_reason='event resolved', component_values=component_values_dict, **base_kwargs)

    return GradedLeg(
        leg=leg,
        settlement='win' if won else 'loss',
        actual_value=float(actual_value),
        reason=f'{leg.player} in {leg.event_label}: actual {actual_value} vs line {leg.line}',
        explanation_reason='event resolved',
        component_values=component_values_dict,
        **base_kwargs,
    )



def grade_text(
    text: str,
    provider: ResultsProvider | None = None,
    posted_at: datetime | None = None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
) -> GradeResponse:
    provider = provider or get_results_provider()
    legs = parse_text(text)
    resolved_legs = resolve_leg_events(
        legs,
        provider,
        posted_at,
        include_historical=include_historical,
        selected_event_id=selected_event_id,
        selected_event_by_leg_id=selected_event_by_leg_id,
    )
    has_confident_match = any(leg.event_id for leg in resolved_legs)
    if not has_confident_match and not include_historical:
        resolved_legs = resolve_leg_events(
            legs,
            provider,
            posted_at,
            include_historical=True,
            selected_event_id=selected_event_id,
            selected_event_by_leg_id=selected_event_by_leg_id,
        )
    graded = [settle_leg(leg, provider) for leg in resolved_legs]

    settlements = [item.settlement for item in graded]
    if any(settlement == 'loss' for settlement in settlements):
        overall = 'lost'
    elif settlements and all(settlement == 'win' for settlement in settlements):
        overall = 'cashed'
    elif any(settlement == 'pending' for settlement in settlements) and not any(settlement == 'unmatched' for settlement in settlements):
        overall = 'pending'
    else:
        overall = 'needs_review'

    return GradeResponse(overall=overall, legs=graded)

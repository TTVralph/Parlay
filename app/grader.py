from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

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


@dataclass
class ValidationResult:
    is_valid: bool
    warnings: list[str]
    confidence: str = 'HIGH'


def _event_info_for_leg(leg: Leg, provider: ResultsProvider):
    if not leg.event_id:
        return None
    event_info_fn = getattr(provider, 'get_event_info', None)
    if callable(event_info_fn):
        return event_info_fn(leg.event_id)
    if leg.event_label and ' @ ' in leg.event_label:
        away, home = leg.event_label.split(' @ ', 1)
        return {'home_team': home, 'away_team': away}
    return None


def validate_player_event_match(player: str, event: object, resolved_team: str | None, provider: ResultsProvider, event_id: str | None = None) -> ValidationResult:
    warnings: list[str] = []
    home_team = getattr(event, 'home_team', None) if event is not None else None
    away_team = getattr(event, 'away_team', None) if event is not None else None
    if isinstance(event, dict):
        home_team = event.get('home_team')
        away_team = event.get('away_team')

    if resolved_team and home_team and away_team:
        normalized_event_teams = {home_team.lower(), away_team.lower()}
        if resolved_team.lower() not in normalized_event_teams:
            warnings.append('Matched event does not include player team')

    roster_fn = getattr(provider, 'is_player_on_event_roster', None)
    if callable(roster_fn) and event_id:
        try:
            is_on_roster = roster_fn(player, event_id=event_id)
        except TypeError:
            is_on_roster = roster_fn(player, event_id)
        if is_on_roster is False:
            warnings.append('Player is not on either roster for matched event')

    if warnings:
        return ValidationResult(is_valid=False, warnings=warnings, confidence='LOW')
    return ValidationResult(is_valid=True, warnings=[])


def _dnp_settlement_mode(provider: ResultsProvider) -> str:
    rules_fn = getattr(provider, 'get_sportsbook_rules', None)
    if callable(rules_fn):
        rules = rules_fn() or {}
        mode = str(rules.get('dnp_player_prop_settlement', 'VOID')).upper()
        if mode in {'VOID', 'NEEDS_REVIEW'}:
            return mode
    return 'VOID'


def _base_leg_kwargs(leg: Leg) -> dict:
    return {
        'matched_event': leg.event_label,
        'line': leg.line,
        'normalized_market': _MARKET_LABELS.get(leg.market_type, leg.market_type),
        'candidate_games': leg.event_candidates,
        'candidate_events': leg.event_candidates,
        'resolved_player_name': leg.resolved_player_name,
        'resolved_team': leg.resolved_team,
        'selected_bet_date': leg.selected_bet_date,
        'parsed_player_name': leg.parsed_player_name,
        'normalized_stat_type': leg.normalized_stat_type or _MARKET_LABELS.get(leg.market_type, leg.market_type),
        'resolved_player_id': leg.resolved_player_id,
        'resolution_confidence': leg.resolution_confidence,
        'parse_confidence': leg.parse_confidence or leg.confidence,
        'resolution_ambiguity_reason': leg.resolution_ambiguity_reason,
        'candidate_players': leg.candidate_players,
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

def _review_reason_from_notes(leg: Leg) -> str:
    lowered_notes = [note.lower() for note in leg.notes]
    if any('multiple possible games. add bet date to narrow results.' in note for note in lowered_notes):
        return 'Multiple possible games. Add bet date to narrow results.'
    if any('missing bet date' in note for note in lowered_notes):
        return 'missing bet date'
    if any('could not parse stat type' in note for note in lowered_notes):
        return 'Could not parse stat type'
    if any('player identity ambiguous' in note for note in lowered_notes):
        return 'player identity ambiguous'
    if any('player not found in sport directory' in note for note in lowered_notes):
        return 'player not found in sport directory'
    if any('team could not be resolved from player identity' in note for note in lowered_notes):
        return 'team could not be resolved from player identity'
    if any('no game found for resolved team on date' in note for note in lowered_notes):
        return 'no game found for resolved team on date'
    if any('matched event does not include player team' in note for note in lowered_notes):
        return 'Matched event does not include player team'
    if any('multiple games found for resolved team on date' in note for note in lowered_notes):
        return 'multiple games found for resolved team on date'
    if len(leg.event_candidates) > 1:
        return 'multiple games found for resolved team on date'
    if any('could not confidently resolve event/date for this leg' in note for note in lowered_notes):
        return 'Could not resolve NBA player'
    return 'event unresolved'


def settle_leg(leg: Leg, provider: ResultsProvider) -> GradedLeg:
    base_kwargs = _base_leg_kwargs(leg)
    base_kwargs['validation_warnings'] = []
    if leg.confidence < 0.75:
        return GradedLeg(leg=leg, settlement='unmatched', reason='Could not parse stat type', explanation_reason='Could not parse stat type', review_reason='Could not parse stat type', **base_kwargs)

    if not leg.event_id:
        reason = _review_reason_from_notes(leg)
        return GradedLeg(leg=leg, settlement='unmatched', reason='No event resolved from post timestamp / schedule lookup', explanation_reason=reason, review_reason=reason, **base_kwargs)

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

    event_info = _event_info_for_leg(leg, provider)
    validation = validate_player_event_match(leg.player, event_info, leg.resolved_team, provider, event_id=leg.event_id)
    if validation.confidence == 'LOW':
        base_kwargs['resolution_confidence'] = min(float(leg.resolution_confidence or 1.0), 0.3)
        base_kwargs['validation_warnings'] = list(validation.warnings)
    if not validation.is_valid:
        return GradedLeg(
            leg=leg,
            settlement='unmatched',
            reason='Impossible player/event match rejected',
            explanation_reason='Leg marked void/review instead of graded',
            review_reason='; '.join(validation.warnings),
            **base_kwargs,
        )

    matched_boxscore_player_name = None
    detail_lookup = getattr(provider, 'get_player_result_details', None)
    actual_value = None
    if callable(detail_lookup):
        details = detail_lookup(leg.player, leg.market_type, event_id=leg.event_id)
        if details:
            actual_value = details.get('actual_value')
            matched_boxscore_player_name = details.get('matched_boxscore_player_name')
    if actual_value is None:
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
                dnp_mode = _dnp_settlement_mode(provider)
                dnp_warnings = ['Player did not appear in box score', 'Leg marked void/review instead of graded']
                dnp_kwargs = {**base_kwargs, 'validation_warnings': dnp_warnings}
                if dnp_mode == 'NEEDS_REVIEW':
                    return GradedLeg(leg=leg, settlement='unmatched', reason=f'{leg.player} did not appear in box score (DNP)', explanation_reason='Leg marked void/review instead of graded', review_reason='Player did not appear in box score', player_found_in_boxscore=False, component_values=component_values_dict, matched_boxscore_player_name=matched_boxscore_player_name, **dnp_kwargs)
                return GradedLeg(leg=leg, settlement='void', reason=f'{leg.player} did not appear in box score (DNP)', explanation_reason='player did not appear in box score / game log', player_found_in_boxscore=False, component_values=component_values_dict, matched_boxscore_player_name=matched_boxscore_player_name, **dnp_kwargs)
        return GradedLeg(leg=leg, settlement='unmatched', reason='Matched event but no stat result', explanation_reason='Matched event but no stat result', player_found_in_boxscore=appeared, component_values=component_values_dict, matched_boxscore_player_name=matched_boxscore_player_name, **base_kwargs)

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
        matched_boxscore_player_name=matched_boxscore_player_name or leg.resolved_player_name or leg.player,
        player_found_in_boxscore=True,
        **base_kwargs,
    )



def grade_text(
    text: str,
    provider: ResultsProvider | None = None,
    posted_at: datetime | date | None = None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
    bet_date: date | None = None,
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
        bet_date=bet_date,
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
            bet_date=bet_date,
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

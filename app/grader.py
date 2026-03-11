from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .models import GradeResponse, GradedLeg, Leg
from .services import grade_reason_codes as reason_codes
from .services.settlement_explainer import build_settlement_explanation, with_explanation
from .services.market_registry import MARKET_REGISTRY, player_market_to_canonical
from .services.play_by_play_provider import ESPNPlayByPlayProvider, PlayByPlayEvent
from .services.provider_router import ProviderRouter
from .services.event_snapshot import EventSnapshot, EventSnapshotService
from .providers.base import ResultsProvider
from .providers.factory import get_results_provider
from .event_matcher import resolve_leg_events
from .parser import filter_valid_legs, parse_text


_MARKET_LABELS = {
    'moneyline': 'Moneyline',
    'spread': 'Spread',
    'game_total': 'Game Total',
    'player_points': 'Points',
    'player_rebounds': 'Rebounds',
    'player_assists': 'Assists',
    'player_threes': 'Threes Made',
    'player_steals': 'Steals',
    'player_blocks': 'Blocks',
    'player_turnovers': 'Turnovers',
    'player_pra': 'PRA',
    'player_pr': 'PR',
    'player_pa': 'PA',
    'player_ra': 'RA',
    'player_passing_yards': 'Passing Yards',
    'player_rushing_yards': 'Rushing Yards',
    'player_receiving_yards': 'Receiving Yards',
    'player_hits': 'Hits',
    'player_first_basket': 'First Basket',
    'player_first_rebound': 'First Rebound',
    'player_first_assist': 'First Assist',
    'player_first_three': 'First Three',
    'player_last_basket': 'Last Basket',
    'player_first_steal': 'First Steal',
    'player_first_block': 'First Block',
}


_STAT_COMPONENT_TO_PLAYER_MARKET = {
    'PTS': 'player_points',
    'REB': 'player_rebounds',
    'AST': 'player_assists',
    '3PM': 'player_threes',
    'STL': 'player_steals',
    'BLK': 'player_blocks',
    'TOV': 'player_turnovers',
}


_STAT_COMPONENT_LABELS = {
    'PTS': 'Points',
    'REB': 'Rebounds',
    'AST': 'Assists',
    '3PM': 'Threes Made',
    'STL': 'Steals',
    'BLK': 'Blocks',
    'TOV': 'Turnovers',
}

@dataclass
class ValidationResult:
    is_valid: bool
    warnings: list[str]
    confidence: str = 'HIGH'


def _name_matches(target_player: str, candidate: str | None) -> bool:
    if not candidate:
        return False
    target_tokens = [token for token in target_player.lower().replace('.', '').split() if token]
    candidate_tokens = [token for token in candidate.lower().replace('.', '').split() if token]
    if not target_tokens or not candidate_tokens:
        return False
    return ''.join(target_tokens) == ''.join(candidate_tokens) or target_tokens[-1] == candidate_tokens[-1]


_SNAPSHOT_STAT_ALIASES = {
    'PTS': {'PTS', 'points'},
    'REB': {'REB', 'rebounds'},
    'AST': {'AST', 'assists'},
    'PR': {'PR'},
    'PA': {'PA'},
    'RA': {'RA'},
    'PRA': {'PRA'},
}


def _snapshot_player_entry(
    snapshot: EventSnapshot,
    *,
    player_id: str | None,
    player_name: str | None,
) -> dict | None:
    for entry in snapshot.normalized_player_stats.values():
        if player_id and str(entry.get('player_id') or '').strip() == str(player_id).strip():
            return entry
    if player_name:
        normalized_name = ''.join(ch for ch in player_name.lower() if ch.isalnum())
        return snapshot.normalized_player_stats.get(normalized_name)
    return None


def get_player_stat(
    snapshot: EventSnapshot,
    player_id: str | None,
    stat_key: str,
    *,
    player_name: str | None = None,
) -> float | None:
    entry = _snapshot_player_entry(snapshot, player_id=player_id, player_name=player_name)
    if not entry:
        return None
    stats = entry.get('stats') or {}
    for alias in _SNAPSHOT_STAT_ALIASES.get(stat_key, {stat_key}):
        value = stats.get(alias)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def get_player_combo_stat(
    snapshot: EventSnapshot,
    player_id: str | None,
    stat_key: str,
    *,
    player_name: str | None = None,
) -> float | None:
    total = get_player_stat(snapshot, player_id, stat_key, player_name=player_name)
    if total is not None:
        return total
    combo_components = {
        'PR': ('PTS', 'REB'),
        'PA': ('PTS', 'AST'),
        'RA': ('REB', 'AST'),
        'PRA': ('PTS', 'REB', 'AST'),
    }
    components = combo_components.get(stat_key)
    if not components:
        return None
    values: list[float] = []
    for component in components:
        value = get_player_stat(snapshot, player_id, component, player_name=player_name)
        if value is None:
            return None
        values.append(value)
    return float(sum(values))


def _select_event_sequence_winner(market_type: str, events: list[PlayByPlayEvent]) -> str | None:
    if market_type == 'player_first_basket':
        event = next((evt for evt in events if evt.is_made_shot), None)
        return event.primary_player if event else None
    if market_type == 'player_last_basket':
        basket_events = [evt for evt in events if evt.is_made_shot]
        return basket_events[-1].primary_player if basket_events else None
    if market_type == 'player_first_three':
        event = next((evt for evt in events if evt.is_three_pointer_made), None)
        return event.primary_player if event else None
    if market_type == 'player_first_rebound':
        event = next((evt for evt in events if evt.is_rebound), None)
        return event.primary_player if event else None
    if market_type == 'player_first_assist':
        event = next((evt for evt in events if evt.is_assist), None)
        return event.assist_player if event else None
    if market_type == 'player_first_steal':
        event = next((evt for evt in events if evt.is_steal), None)
        return event.steal_player if event else None
    if market_type == 'player_first_block':
        event = next((evt for evt in events if evt.is_block), None)
        return event.block_player if event else None
    return None


def _event_info_for_leg(leg: Leg, provider: ResultsProvider):
    if leg.identity_match_confidence == 'LOW':
        return GradedLeg(leg=leg, settlement='unmatched', reason='Low-confidence identity match requires review', explanation_reason='player identity ambiguous', review_reason='player identity ambiguous', **base_kwargs)

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


def _base_leg_kwargs(leg: Leg, *, input_source_path: str = 'manual_text') -> dict:
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
        'candidate_player_details': leg.candidate_player_details,
        'identity_source': leg.identity_source,
        'identity_last_refreshed_at': leg.identity_last_refreshed_at,
        'identity_match_method': leg.identity_match_method,
        'identity_match_confidence': leg.identity_match_confidence,
        'matched_event_date': leg.matched_event_date,
        'matched_team': leg.matched_team,
        'event_resolution_confidence': leg.event_resolution_confidence,
        'event_resolution_warnings': leg.event_resolution_warnings,
        'slip_default_date': leg.slip_default_date,
        'mixed_event_dates_detected': leg.mixed_event_dates_detected,
        'event_resolution_status': leg.event_resolution_status,
        'event_resolution_method': leg.event_resolution_method,
        'event_review_reason_code': leg.event_review_reason_code,
        'event_review_reason_text': leg.event_review_reason_text,
        'event_date_match_quality': leg.event_date_match_quality,
        'roster_validation_result': leg.roster_validation_result,
        'input_source_path': input_source_path,
        'selected_player_name': leg.selected_player_name,
        'selected_player_id': leg.selected_player_id,
        'selection_source': leg.selection_source,
        'selection_explanation': leg.selection_explanation,
        'selection_applied': leg.selection_applied,
        'selection_error_code': leg.selection_error_code,
        'canonical_player_name': leg.canonical_player_name,
        'event_selection_applied': leg.event_selection_applied,
        'selected_event_id': leg.selected_event_id,
        'selected_event_label': leg.selected_event_label,
        'event_selection_source': leg.event_selection_source,
        'event_selection_explanation': leg.event_selection_explanation,
        'override_used_for_grading': leg.override_used_for_grading,
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



def _extract_candidate_count_from_notes(notes: list[str], key: str) -> int | None:
    prefix = f'diagnostic: {key}='
    for note in notes:
        if note.startswith(prefix):
            try:
                return int(note.split('=', 1)[1])
            except ValueError:
                return None
    return None


def _default_settlement_diagnostics(leg: Leg) -> dict[str, object]:
    return {
        'resolved_player_identity': leg.resolved_player_name or leg.player,
        'resolved_player_team': leg.resolved_team,
        'candidate_events_found': leg.event_candidates,
        'final_matched_event': leg.event_label,
        'event_match_rejection_reason': None,
        'roster_validation_result': None,
        'stat_lookup_result': None,
        'settlement_failure_reason': None,
        'unmatched_reason_code': None,
        'event_resolution_worked': bool(leg.event_id),
        'stat_extraction_worked': False,
        'market_mapping': None,
        'candidate_events_before_filtering': _extract_candidate_count_from_notes(leg.notes, 'candidate_events_before_filtering'),
        'candidate_events_after_filtering': _extract_candidate_count_from_notes(leg.notes, 'candidate_events_after_filtering'),
        'event_resolution_status': leg.event_resolution_status,
        'event_resolution_method': leg.event_resolution_method,
        'event_review_reason_code': leg.event_review_reason_code,
        'event_review_reason_text': leg.event_review_reason_text,
        'event_date_match_quality': leg.event_date_match_quality,
    }

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
    if any('manual player selection invalid' in note for note in lowered_notes):
        return 'Selected player could not be applied because the player ID was not found in the active directory.'
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


def _input_source_from_code_path(code_path: str) -> str:
    return 'screenshot' if 'screenshot' in code_path else 'manual_text'


def _review_reason_text(review_reason: str | None, reason_code: str) -> str | None:
    value = (review_reason or '').lower()
    explicit = {
        reason_codes.IDENTITY_MATCH_AMBIGUOUS: 'Review: Multiple plausible player matches found; select the correct player.',
        reason_codes.INVALID_SELECTED_PLAYER_ID: 'Review: Selected player could not be applied; please choose again.',
        'invalid_selected_event_id': 'Review: Selected game could not be applied; choose a listed game for this leg.',
        reason_codes.PLAYER_NOT_ON_EVENT_ROSTER: 'Review: Matched game does not contain the resolved player on the roster.',
        reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER: 'Review: Matched game does not contain the resolved player on the roster.',
        reason_codes.EVENT_UNRESOLVED: 'Review: No matching game was found for the resolved team/date.',
        reason_codes.NO_CANDIDATE_EVENTS: 'Review: No matching game was found for the resolved team/date.',
    }
    if reason_code in explicit:
        if reason_code == reason_codes.IDENTITY_MATCH_AMBIGUOUS:
            if 'likely refers to' in value and review_reason:
                return f'Review: {review_reason}'
            if 'not found' in value or 'could not be resolved' in value:
                return 'Review: Player name could not be resolved confidently.'
        if reason_code in {reason_codes.EVENT_UNRESOLVED, reason_codes.NO_CANDIDATE_EVENTS} and review_reason and any(
            token in value for token in ('multiple plausible games', 'nearby-date', 'roster', 'no matching game')
        ):
            return f'Review: {review_reason}'
        return explicit[reason_code]
    if reason_code in {reason_codes.MATCHED_EVENT_TEAM_MISMATCH, reason_codes.EVENT_TEAM_MISMATCH}:
        return 'Review: Matched game does not contain the resolved player on the roster.'
    if reason_code in {reason_codes.MISSING_STAT_SOURCE, reason_codes.STAT_NOT_FOUND, reason_codes.MARKET_MAPPING_MISSING} and any(k in value for k in ('combo', 'component', 'stat')):
        return 'Review: combo component stats incomplete'
    if review_reason:
        return f'Review: {review_reason}'
    return None


def _build_debug_comparison(leg: Leg, *, graded: GradedLeg, reason_code: str, review_reason: str | None, input_source_path: str) -> dict[str, object]:
    return {
        'input_source_path': input_source_path,
        'raw_player_text': leg.player,
        'normalized_player_name': leg.resolved_player_name or leg.player,
        'normalized_market': graded.normalized_market or leg.normalized_stat_type or leg.market_type,
        'line': leg.line,
        'selection': f"{leg.direction} {leg.line}" if leg.direction is not None and leg.line is not None else leg.direction,
        'matched_event': leg.event_label,
        'matched_event_date': leg.matched_event_date,
        'candidate_event_count': len(leg.event_candidates),
        'unmatched_reason_code': (graded.settlement_diagnostics or {}).get('unmatched_reason_code'),
        'settlement_reason_code': reason_code,
        'grading_confidence': graded.resolution_confidence,
        'review_downgrade_reason': review_reason,
    }


def settle_leg(
    leg: Leg,
    provider: ResultsProvider,
    *,
    play_by_play_provider: ESPNPlayByPlayProvider | None = None,
    event_snapshot: EventSnapshot | None = None,
    code_path: str = 'manual_text_slip_grading',
    input_source_path: str = 'manual_text',
) -> GradedLeg:
    base_kwargs = _base_leg_kwargs(leg, input_source_path=input_source_path)
    base_kwargs['validation_warnings'] = []
    settlement_diagnostics = _default_settlement_diagnostics(leg)
    settlement_diagnostics['source_equivalence_policy'] = 'source-neutral; confidence-driven only'
    base_kwargs['settlement_diagnostics'] = settlement_diagnostics

    def explained(
        *,
        settlement: str,
        reason: str,
        reason_code: str,
        reason_message: str,
        review_reason: str | None = None,
        actual_value: float | None = None,
        **kwargs,
    ) -> GradedLeg:
        if settlement in {'unmatched', 'pending', 'void'} and settlement_diagnostics.get('unmatched_reason_code') is None:
            settlement_diagnostics['unmatched_reason_code'] = reason_code
        graded = GradedLeg(
            leg=leg,
            settlement=settlement,  # type: ignore[arg-type]
            reason=reason,
            actual_value=actual_value,
            review_reason=review_reason,
            **base_kwargs,
            **kwargs,
        )
        explanation = build_settlement_explanation(
            leg,
            settlement=graded.settlement,
            reason_code=reason_code,
            reason_message=reason_message,
            actual_stat_value=actual_value,
            warnings=graded.validation_warnings,
            grading_confidence=graded.resolution_confidence,
            settlement_diagnostics=settlement_diagnostics,
            stat_components=kwargs.get('stat_components'),
            component_values=kwargs.get('component_values'),
            computed_total=kwargs.get('computed_total'),
        )
        graded = with_explanation(graded, explanation)
        graded.review_reason_text = _review_reason_text(review_reason, reason_code)
        graded.debug_comparison = _build_debug_comparison(
            leg,
            graded=graded,
            reason_code=reason_code,
            review_reason=review_reason,
            input_source_path=input_source_path,
        )
        return graded

    if leg.selection_error_code == 'INVALID_SELECTED_PLAYER_ID':
        return explained(
            settlement='unmatched',
            reason='Selected player override is invalid',
            reason_code=reason_codes.INVALID_SELECTED_PLAYER_ID,
            reason_message='Selected player could not be applied because the player ID was not found in the active directory.',
            review_reason='Selected player could not be applied because the player ID was not found in the active directory.',
            explanation_reason='Selected player could not be applied because the player ID was not found in the active directory.',
        )

    if leg.selection_error_code == 'INVALID_SELECTED_EVENT_ID':
        return explained(
            settlement='unmatched',
            reason='Selected event override is invalid',
            reason_code='invalid_selected_event_id',
            reason_message='Selected game could not be applied because the event ID was not found for this leg.',
            review_reason='Selected game could not be applied because the event ID was not found for this leg.',
            explanation_reason='Selected game could not be applied because the event ID was not found for this leg.',
        )

    if leg.confidence < 0.75:
        return explained(
            settlement='unmatched',
            reason='Could not parse stat type',
            reason_code=reason_codes.PARSER_LOW_CONFIDENCE,
            reason_message='Could not parse stat type with sufficient confidence',
            review_reason='Could not parse stat type',
            explanation_reason='Could not parse stat type',
        )

    if leg.identity_match_confidence == 'LOW':
        ambiguity_reason = leg.resolution_ambiguity_reason or 'player identity ambiguous'
        return explained(
            settlement='unmatched',
            reason='Low-confidence identity match requires review',
            reason_code=reason_codes.IDENTITY_MATCH_AMBIGUOUS,
            reason_message='Player identity match is ambiguous',
            review_reason=ambiguity_reason,
            explanation_reason=ambiguity_reason,
        )

    if not leg.event_id:
        reason = leg.event_review_reason_text or _review_reason_from_notes(leg)
        settlement_diagnostics['settlement_failure_reason'] = reason
        settlement_diagnostics['unmatched_reason_code'] = reason_codes.NO_CANDIDATE_EVENTS
        return explained(
            settlement='unmatched',
            reason='No event resolved from post timestamp / schedule lookup',
            reason_code=reason_codes.EVENT_UNRESOLVED,
            reason_message=reason,
            review_reason=reason,
            explanation_reason=reason,
        )


    canonical_market = player_market_to_canonical(leg.market_type)
    registry_entry = MARKET_REGISTRY.get(canonical_market) if canonical_market else None
    settlement_diagnostics['market_normalization'] = {
        'code_path': code_path,
        'raw_market_text': leg.market_type,
        'normalized_market': canonical_market,
        'registry_entry_found': bool(registry_entry),
    }
    router = ProviderRouter(box_score_provider=provider, play_by_play_provider=play_by_play_provider)
    route = router.route(leg.market_type)
    settlement_diagnostics['provider_route'] = route.data_source

    if leg.sport == 'NBA' and leg.market_type.startswith('player_') and canonical_market is None:
        return explained(
            settlement='unmatched',
            reason='Unsupported NBA bet type for ESPN-backed grading',
            reason_code=reason_codes.UNSUPPORTED_MARKET,
            reason_message='Unsupported market for this provider',
            explanation_reason='stat unavailable',
        )

    if leg.market_type in {'moneyline', 'spread', 'game_total'}:
        team_key = leg.team
        lookup_team = team_key
        if leg.market_type == 'game_total' and not lookup_team:
            event_label = leg.event_label or ''
            if ' @ ' in event_label:
                _, home = event_label.split(' @ ', 1)
                lookup_team = home
        if not lookup_team:
            return explained(settlement='unmatched', reason='No team/event context identified', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='No team/event context identified', explanation_reason='no valid same-team game found')
        team_result = provider.get_team_result(lookup_team, event_id=leg.event_id)
        if not team_result:
            status = _event_status(provider, leg.event_id)
            if status == 'live':
                return explained(settlement='pending', reason='Game is in progress', reason_code=reason_codes.EVENT_UNRESOLVED, reason_message='Game is in progress', explanation_reason='event unresolved')
            return explained(settlement='unmatched', reason='Could not verify team result from trusted data source', reason_code=reason_codes.MISSING_STAT_SOURCE, reason_message='Could not verify team result from trusted data source', explanation_reason='event unresolved')

        if leg.market_type == 'moneyline':
            won = team_result.moneyline_win if leg.team == lookup_team else provider.get_team_result(leg.team or '', event_id=leg.event_id).moneyline_win  # type: ignore[union-attr]
            return explained(
                settlement='win' if won else 'loss',
                actual_value=1 if won else 0,
                reason=f'{leg.team} in {team_result.event.label}: ' + ('team won game' if won else 'team lost game'),
                reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE,
                reason_message='Team won game' if won else 'Team lost game',
                explanation_reason='event resolved',
            )

        if leg.market_type == 'spread':
            if not leg.team or leg.line is None:
                return explained(settlement='unmatched', reason='Missing team or line for spread settlement', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='Missing team or line for spread settlement', explanation_reason='stat unavailable')
            margin = team_result.team_margin(leg.team)
            covered_value = margin + leg.line
            if covered_value == 0:
                return explained(settlement='push', actual_value=float(margin), reason=f'{leg.team} margin {margin} landed exactly on spread {leg.line}', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{margin} landed exactly on spread {leg.line}', explanation_reason='event resolved')
            won = covered_value > 0
            return explained(settlement='win' if won else 'loss', actual_value=float(margin), reason=f'{leg.team} margin {margin} vs spread {leg.line} in {team_result.event.label}', reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE, reason_message=f'{margin} vs spread {leg.line}', explanation_reason='event resolved')

        if leg.market_type == 'game_total':
            if leg.line is None or leg.direction is None:
                return explained(settlement='unmatched', reason='Missing total line or direction', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='Missing total line or direction', explanation_reason='stat unavailable')
            total_points = team_result.total_points
            if total_points == leg.line:
                return explained(settlement='push', actual_value=float(total_points), reason='Game total landed exactly on line', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{total_points} landed exactly on line {leg.line}', explanation_reason='event resolved')
            won = total_points > leg.line if leg.direction == 'over' else total_points < leg.line
            comparator = 'above' if total_points > leg.line else 'below'
            return explained(settlement='win' if won else 'loss', actual_value=float(total_points), reason=f'Game total {total_points} vs {leg.direction} {leg.line} in {team_result.event.label}', reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if comparator == 'above' else reason_codes.ACTUAL_STAT_BELOW_LINE, reason_message=f'{total_points} is {comparator} {leg.line}', explanation_reason='event resolved')

    if not leg.player:
        return explained(settlement='unmatched', reason='No player identified', reason_code=reason_codes.NO_PLAYER_IDENTIFIED, reason_message='No player identified', explanation_reason='player identity ambiguous')

    player_lookup_name = leg.resolved_player_name or leg.player

    if route.data_source == 'play_by_play':
        if route.provider is None:
            settlement_diagnostics['settlement_failure_reason'] = 'play-by-play provider unavailable'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.MISSING_STAT_SOURCE
            return explained(
                settlement='unmatched',
                reason='Play-by-play provider unavailable',
                reason_code=reason_codes.MISSING_STAT_SOURCE,
                reason_message='Play-by-play provider unavailable',
                review_reason='Play-by-play provider unavailable',
                explanation_reason='stat unavailable',
            )
        events = event_snapshot.normalized_play_by_play if event_snapshot is not None else None
        if events is None:
            events = route.provider.get_normalized_events(leg.event_id)
        if not events:
            settlement_diagnostics['settlement_failure_reason'] = 'missing play-by-play payload'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.MISSING_STAT_SOURCE
            return explained(
                settlement='unmatched',
                reason='Missing play-by-play payload for event',
                reason_code=reason_codes.MISSING_STAT_SOURCE,
                reason_message='Missing play-by-play payload for event',
                review_reason='Missing play-by-play payload for event',
                explanation_reason='stat unavailable',
            )
        winning_player = _select_event_sequence_winner(leg.market_type, events)
        if not winning_player:
            settlement_diagnostics['settlement_failure_reason'] = 'unresolved play-by-play market winner'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.STAT_NOT_FOUND
            return explained(
                settlement='unmatched',
                reason='Could not determine event-sequence winner from play-by-play',
                reason_code=reason_codes.MISSING_STAT_SOURCE,
                reason_message='Could not determine event-sequence winner from play-by-play',
                review_reason='Could not determine event-sequence winner from play-by-play',
                explanation_reason='stat unavailable',
            )
        direction = leg.direction or 'yes'
        is_match = _name_matches(player_lookup_name, winning_player)
        won = is_match if direction == 'yes' else not is_match
        settlement_diagnostics['stat_extraction_worked'] = True
        return explained(
            settlement='win' if won else 'loss',
            actual_value=1.0 if is_match else 0.0,
            reason=f'{winning_player} is the resolved {(_MARKET_LABELS.get(leg.market_type, leg.market_type)).lower()}',
            reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE,
            reason_message=f'{winning_player} resolved this market',
            explanation_reason='event resolved',
            matched_boxscore_player_name=winning_player,
            player_found_in_boxscore=True,
        )

    event_info = {
        'home_team': (event_snapshot.home_team or {}).get('name'),
        'away_team': (event_snapshot.away_team or {}).get('name'),
    } if event_snapshot is not None else _event_info_for_leg(leg, provider)
    settlement_diagnostics['final_matched_event'] = leg.event_label
    validation = validate_player_event_match(player_lookup_name, event_info, leg.resolved_team, provider, event_id=leg.event_id)
    settlement_diagnostics['roster_validation_result'] = 'pass' if validation.is_valid else 'fail'
    base_kwargs['roster_validation_result'] = settlement_diagnostics['roster_validation_result']
    if validation.confidence == 'LOW':
        base_kwargs['resolution_confidence'] = min(float(leg.resolution_confidence or 1.0), 0.3)
        base_kwargs['validation_warnings'] = list(validation.warnings)
    if not validation.is_valid:
        code = reason_codes.MATCHED_EVENT_TEAM_MISMATCH
        if any('not on either roster' in warning.lower() for warning in validation.warnings):
            code = reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER
        settlement_diagnostics['event_match_rejection_reason'] = '; '.join(validation.warnings)
        settlement_diagnostics['settlement_failure_reason'] = '; '.join(validation.warnings)
        if code == reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER:
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_NOT_ON_EVENT_ROSTER
        else:
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.EVENT_TEAM_MISMATCH
        review_text = 'Matched game does not contain the resolved player on the roster.' if code == reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER else 'Matched game does not contain the resolved player team.'
        base_kwargs['event_review_reason_text'] = review_text
        base_kwargs['event_review_reason_code'] = 'matched_event_rejected_by_roster_validation' if code == reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER else 'matched_event_team_mismatch'
        return explained(settlement='unmatched', reason='Impossible player/event match rejected', reason_code=code, reason_message='; '.join(validation.warnings), review_reason=review_text, explanation_reason='Leg marked void/review instead of graded')

    matched_boxscore_player_name = None
    market_diag_fn = getattr(provider, 'get_market_mapping_diagnostics', None)
    if callable(market_diag_fn):
        settlement_diagnostics['market_mapping'] = market_diag_fn(leg.market_type, event_id=leg.event_id)
        if settlement_diagnostics['market_mapping'] and settlement_diagnostics['market_mapping'].get('mapping_failed'):
            settlement_diagnostics['settlement_failure_reason'] = 'market mapping missing'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.MARKET_MAPPING_MISSING

    snapshot_supported_markets = {
        'player_points',
        'player_rebounds',
        'player_assists',
        'player_pr',
        'player_pa',
        'player_ra',
        'player_pra',
    }
    used_snapshot = False
    snapshot_entry = None
    if event_snapshot is not None and leg.market_type in snapshot_supported_markets:
        snapshot_entry = _snapshot_player_entry(
            event_snapshot,
            player_id=leg.resolved_player_id,
            player_name=player_lookup_name,
        )
        if snapshot_entry:
            matched_boxscore_player_name = snapshot_entry.get('display_name')

    detail_lookup = getattr(provider, 'get_player_result_details', None)
    actual_value = None
    if event_snapshot is not None and leg.market_type in snapshot_supported_markets:
        if leg.market_type == 'player_points':
            actual_value = get_player_stat(event_snapshot, leg.resolved_player_id, 'PTS', player_name=player_lookup_name)
        elif leg.market_type == 'player_rebounds':
            actual_value = get_player_stat(event_snapshot, leg.resolved_player_id, 'REB', player_name=player_lookup_name)
        elif leg.market_type == 'player_assists':
            actual_value = get_player_stat(event_snapshot, leg.resolved_player_id, 'AST', player_name=player_lookup_name)
        elif leg.market_type == 'player_pr':
            actual_value = get_player_combo_stat(event_snapshot, leg.resolved_player_id, 'PR', player_name=player_lookup_name)
        elif leg.market_type == 'player_pa':
            actual_value = get_player_combo_stat(event_snapshot, leg.resolved_player_id, 'PA', player_name=player_lookup_name)
        elif leg.market_type == 'player_ra':
            actual_value = get_player_combo_stat(event_snapshot, leg.resolved_player_id, 'RA', player_name=player_lookup_name)
        elif leg.market_type == 'player_pra':
            actual_value = get_player_combo_stat(event_snapshot, leg.resolved_player_id, 'PRA', player_name=player_lookup_name)
        used_snapshot = actual_value is not None

    if actual_value is None and callable(detail_lookup):
        details = detail_lookup(player_lookup_name, leg.market_type, event_id=leg.event_id)
        if details:
            actual_value = details.get('actual_value')
            matched_boxscore_player_name = details.get('matched_boxscore_player_name')
    if actual_value is None:
        actual_value = provider.get_player_result(player_lookup_name, leg.market_type, event_id=leg.event_id)

    component_values_dict = None
    stat_components: list[str] | None = None
    computed_total: float | None = None
    market_entry = registry_entry
    if market_entry and market_entry['market_type'] == 'combo_stat':
        component_values_dict = {}
        stat_components = list(market_entry['stat_components'])
        for component in stat_components:
            component_label = _STAT_COMPONENT_LABELS.get(component, component)
            component_value = None
            if event_snapshot is not None and leg.market_type in snapshot_supported_markets:
                component_value = get_player_stat(event_snapshot, leg.resolved_player_id, component, player_name=player_lookup_name)
            if component_value is None:
                lookup_market = _STAT_COMPONENT_TO_PLAYER_MARKET.get(component)
                if not lookup_market:
                    component_values_dict = None
                    break
                component_value = provider.get_player_result(player_lookup_name, lookup_market, event_id=leg.event_id)
            if component_value is None:
                component_values_dict = None
                break
            component_values_dict[component_label] = float(component_value)
        if component_values_dict:
            computed_total = float(sum(component_values_dict.values()))
            actual_value = computed_total

    settlement_diagnostics['stat_source'] = 'snapshot' if used_snapshot else 'provider'

    settlement_diagnostics['stat_lookup_result'] = 'found' if actual_value is not None else 'missing'
    if leg.line is None or leg.direction is None:
        return explained(settlement='unmatched', reason='Missing values required for settlement', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='Missing values required for settlement', explanation_reason='stat unavailable', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
    if actual_value is None:
        status = _event_status(provider, leg.event_id)
        if status == 'live':
            settlement_diagnostics['settlement_failure_reason'] = 'event not final'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.EVENT_NOT_FINAL
            return explained(settlement='pending', reason='Game is in progress', reason_code=reason_codes.EVENT_UNRESOLVED, reason_message='Game is in progress', explanation_reason='event unresolved', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
        did_appear_fn = getattr(provider, 'did_player_appear', None)
        appeared = None
        if callable(did_appear_fn):
            try:
                appeared = did_appear_fn(player_lookup_name, event_id=leg.event_id)
            except TypeError:
                appeared = did_appear_fn(player_lookup_name, leg.event_id)
            except Exception:
                appeared = None
            if appeared is False:
                dnp_mode = _dnp_settlement_mode(provider)
                dnp_warnings = ['Player did not appear in box score', 'Leg marked void/review instead of graded']
                dnp_kwargs = {**base_kwargs, 'validation_warnings': dnp_warnings}
                base_kwargs.update(dnp_kwargs)
                if dnp_mode == 'NEEDS_REVIEW':
                    settlement_diagnostics['settlement_failure_reason'] = 'player did not play'
                    settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_DID_NOT_PLAY
                    return explained(settlement='unmatched', reason=f'{player_lookup_name} did not appear in box score (DNP)', reason_code=reason_codes.DNP_REVIEW_REQUIRED, reason_message='Player did not appear in box score', review_reason='Player did not appear in box score', explanation_reason='Leg marked void/review instead of graded', player_found_in_boxscore=False, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)
                settlement_diagnostics['settlement_failure_reason'] = 'player did not play'
                settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_DID_NOT_PLAY
                return explained(settlement='void', reason=f'{player_lookup_name} did not appear in box score (DNP)', reason_code=reason_codes.PLAYER_DID_NOT_PLAY, reason_message='Player did not appear in box score', explanation_reason='player did not appear in box score / game log', player_found_in_boxscore=False, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)
        settlement_diagnostics['settlement_failure_reason'] = 'stat not found'
        settlement_diagnostics['unmatched_reason_code'] = reason_codes.STAT_NOT_FOUND
        review_reason = 'combo component stats incomplete' if market_entry and market_entry.get('market_type') == 'combo_stat' else 'Matched event but no stat result'
        return explained(settlement='unmatched', reason='Matched event but no stat result', reason_code=reason_codes.MISSING_STAT_SOURCE, reason_message='Matched event but no stat result', review_reason=review_reason, explanation_reason='Matched event but no stat result', player_found_in_boxscore=appeared, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)

    if leg.direction == 'over':
        won = actual_value > leg.line
        if actual_value == leg.line:
            return explained(settlement='push', actual_value=float(actual_value), reason='Landed exactly on line', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{actual_value} landed exactly on {leg.line}', explanation_reason='event resolved', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
        reason_code = reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE
        comparison = 'above' if won else 'below'
        readable = f'{actual_value} is {comparison} {leg.line}'
    else:
        won = actual_value < leg.line
        if actual_value == leg.line:
            return explained(settlement='push', actual_value=float(actual_value), reason='Landed exactly on line', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{actual_value} landed exactly on {leg.line}', explanation_reason='event resolved', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
        reason_code = reason_codes.ACTUAL_STAT_BELOW_LINE if won else reason_codes.ACTUAL_STAT_ABOVE_LINE
        comparison = 'below' if won else 'above'
        readable = f'{actual_value} is {comparison} {leg.line}'


    if market_entry and market_entry['market_type'] == 'combo_stat' and component_values_dict:
        breakdown = ' + '.join(f"{key} {value:g}" for key, value in component_values_dict.items())
        readable = f"{actual_value:g} {market_entry['display_name']} is {comparison} {leg.line} ({breakdown})"
    settlement_diagnostics['stat_extraction_worked'] = True
    return explained(
        settlement='win' if won else 'loss',
        actual_value=float(actual_value),
        reason=f'{player_lookup_name} in {leg.event_label}: actual {actual_value} vs line {leg.line}',
        reason_code=reason_code,
        reason_message=readable,
        explanation_reason='event resolved',
        component_values=component_values_dict,
        stat_components=stat_components,
        computed_total=computed_total,
        matched_boxscore_player_name=matched_boxscore_player_name or leg.resolved_player_name or leg.player,
        player_found_in_boxscore=True,
    )
def grade_text(
    text: str,
    provider: ResultsProvider | None = None,
    posted_at: datetime | date | None = None,
    *,
    include_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
    selected_player_by_leg_id: dict[str, str] | None = None,
    bet_date: date | None = None,
    screenshot_default_date: date | None = None,
    code_path: str = 'manual_text_slip_grading',
    play_by_play_provider: ESPNPlayByPlayProvider | None = None,
) -> GradeResponse:
    provider = provider or get_results_provider()
    play_by_play_provider = play_by_play_provider or ESPNPlayByPlayProvider()
    parsed_legs = parse_text(text)
    legs = filter_valid_legs(parsed_legs)
    resolved_legs = resolve_leg_events(
        legs,
        provider,
        posted_at,
        include_historical=include_historical,
        selected_event_id=selected_event_id,
        selected_event_by_leg_id=selected_event_by_leg_id,
        selected_player_by_leg_id=selected_player_by_leg_id,
        bet_date=bet_date,
        screenshot_default_date=screenshot_default_date,
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
            selected_player_by_leg_id=selected_player_by_leg_id,
            bet_date=bet_date,
            screenshot_default_date=screenshot_default_date,
        )
    input_source_path = _input_source_from_code_path(code_path)

    snapshots_by_event_id: dict[str, EventSnapshot] = {}
    from .providers.espn_provider import ESPNNBAResultsProvider
    if isinstance(provider, ESPNNBAResultsProvider):
        router = ProviderRouter(box_score_provider=provider, play_by_play_provider=play_by_play_provider)
        event_to_legs: dict[str, list[Leg]] = {}
        for leg in resolved_legs:
            if leg.event_id:
                event_to_legs.setdefault(leg.event_id, []).append(leg)
        if event_to_legs:
            snapshot_service = EventSnapshotService(play_by_play_provider=play_by_play_provider)
            event_dates = {
                event_id: next((leg.matched_event_date for leg in legs if leg.matched_event_date), '')
                for event_id, legs in event_to_legs.items()
            }
            include_play_by_play_event_ids = {
                event_id
                for event_id, legs in event_to_legs.items()
                if any(router.route(leg.market_type).data_source == 'play_by_play' for leg in legs)
            }
            snapshots_by_event_id = snapshot_service.get_many_event_snapshots(
                list(event_to_legs.keys()),
                event_dates={k: v for k, v in event_dates.items() if v},
                include_play_by_play_event_ids=include_play_by_play_event_ids,
            )

    graded = [
        settle_leg(
            leg,
            provider,
            play_by_play_provider=play_by_play_provider,
            event_snapshot=snapshots_by_event_id.get(leg.event_id or ''),
            code_path=code_path,
            input_source_path=input_source_path,
        )
        for leg in resolved_legs
    ]

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

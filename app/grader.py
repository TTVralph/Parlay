from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .models import GradeResponse, GradedLeg, Leg, SlipGroup
from .services import grade_reason_codes as reason_codes
from .services.settlement_explainer import build_settlement_explanation, with_explanation
from .services.leg_explainer import explain_sold_legs
from .services.confidence_scoring import confidence_recommendation, score_leg_confidence, score_slip_confidence
from .services.market_registry import MARKET_REGISTRY, player_market_to_canonical
from .services.slip_fingerprint import generate_slip_hash, register_slip_hash
from .services.play_by_play_provider import ESPNPlayByPlayProvider, PlayByPlayEvent
from .services.provider_router import ProviderRouter
from .services.event_snapshot import EventSnapshot, EventSnapshotService
from .services.event_snapshot_cache import get_event_snapshot_cache
from .services.player_alias_index import resolve_snapshot_player
from .rules.registry import get_stat_rule
from .rules.helpers import get_player_stat as _rule_get_player_stat, compute_combo_stat
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
    'player_strikeouts': 'Strikeouts',
    'player_total_bases': 'Total Bases',
    'player_runs': 'Runs',
    'player_rbis': 'RBIs',
    'player_home_runs': 'Home Runs',
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


def _compute_leg_progress(*, actual_value: float | None, line: float | None) -> float | None:
    if actual_value is None or line is None:
        return None
    target = float(line)
    if target == 0.0:
        return None
    progress = float(actual_value) / target
    return round(max(0.0, progress), 2)


def _compute_slip_progress(graded_legs: list[GradedLeg]) -> float | None:
    graded_progress = [float(item.progress) for item in graded_legs if item.progress is not None]
    if not graded_progress:
        return None
    return round(sum(graded_progress) / len(graded_progress), 2)


def _name_matches(target_player: str, candidate: str | None) -> bool:
    if not candidate:
        return False
    target_tokens = [token for token in target_player.lower().replace('.', '').split() if token]
    candidate_tokens = [token for token in candidate.lower().replace('.', '').split() if token]
    if not target_tokens or not candidate_tokens:
        return False
    return ''.join(target_tokens) == ''.join(candidate_tokens) or target_tokens[-1] == candidate_tokens[-1]


_SNAPSHOT_DERIVED_MARKET_COMPONENTS = {
    'player_double_double': ('PTS', 'REB', 'AST', 'STL', 'BLK'),
    'player_triple_double': ('PTS', 'REB', 'AST', 'STL', 'BLK'),
}




_LIVE_PROGRESS_MARKETS = {
    'player_points': ('PTS',),
    'player_rebounds': ('REB',),
    'player_assists': ('AST',),
    'player_pr': ('PTS', 'REB'),
    'player_pa': ('PTS', 'AST'),
    'player_ra': ('REB', 'AST'),
    'player_pra': ('PTS', 'REB', 'AST'),
}


def _build_live_progress_payload(
    leg: Leg,
    *,
    actual_value: float | None,
    line: float | None,
    component_values: dict[str, float] | None,
) -> dict[str, object] | None:
    rule = get_stat_rule(leg.sport, leg.market_type)
    stat_keys = tuple(rule.live_progress_components) if rule and rule.supports_live_progress else _LIVE_PROGRESS_MARKETS.get(leg.market_type)
    if not stat_keys or line is None:
        return None
    target_value = float(line)
    current_value = float(actual_value) if actual_value is not None else 0.0
    remaining = max(0.0, target_value - current_value) if leg.direction == 'over' else max(0.0, current_value - target_value)
    status = 'On pace'
    if remaining <= 0:
        status = 'Line hit'
    elif current_value <= 0:
        status = 'No stats yet'

    payload: dict[str, object] = {
        'current_stat_value': round(current_value, 2),
        'target_value': round(target_value, 2),
        'remaining_to_hit': round(remaining, 2),
        'live_status_text': status,
    }
    if len(stat_keys) > 1:
        breakdown: dict[str, float] = {}
        values = component_values or {}
        for key in stat_keys:
            label = _STAT_COMPONENT_LABELS.get(key, key)
            raw = values.get(label)
            if raw is None:
                raw = values.get(key)
            if raw is None:
                continue
            breakdown[key] = float(raw)
        payload['component_breakdown'] = breakdown
    return payload


def _build_live_progress_timeline(
    leg: Leg,
    snapshot: EventSnapshot | None,
    *,
    player_name: str,
) -> list[dict[str, object]]:
    rule = get_stat_rule(leg.sport, leg.market_type)
    stat_keys = tuple(rule.live_progress_components) if rule and rule.supports_live_progress else _LIVE_PROGRESS_MARKETS.get(leg.market_type)
    if not stat_keys or snapshot is None or not snapshot.normalized_play_by_play:
        return []
    player_norm = player_name.lower().strip()
    cumulative = {key: 0.0 for key in stat_keys}
    by_period: dict[str, dict[str, object]] = {}

    for event in snapshot.normalized_play_by_play:
        period_label = f"Q{event.period}" if event.period is not None else 'game'
        changed: set[str] = set()
        primary = str(event.primary_player or '').lower().strip()
        assister = str(event.assist_player or '').lower().strip()
        if 'PTS' in stat_keys and event.is_made_shot and primary == player_norm:
            cumulative['PTS'] += 3.0 if event.is_three_pointer_made else 2.0
            changed.add('PTS')
        if 'REB' in stat_keys and event.is_rebound and primary == player_norm:
            cumulative['REB'] += 1.0
            changed.add('REB')
        if 'AST' in stat_keys and event.is_assist and assister == player_norm:
            cumulative['AST'] += 1.0
            changed.add('AST')
        if not changed:
            continue
        bucket = by_period.setdefault(period_label, {'period_label': period_label, 'cumulative': {}, 'components': {}})
        bucket['cumulative'] = {k: round(v, 2) for k, v in cumulative.items()}
        bucket['components'] = {k: round(cumulative[k], 2) for k in stat_keys}

    return [by_period[key] for key in sorted(by_period.keys(), key=lambda x: (x != 'game', x))]


def _snapshot_player_entry(
    snapshot: EventSnapshot,
    *,
    player_id: str | None,
    player_name: str | None,
) -> dict | None:
    return resolve_snapshot_player(
        player_entries=snapshot.normalized_player_stats.values(),
        player_id=player_id,
        player_name=player_name,
    ).entry


def _snapshot_player_match_result(
    snapshot: EventSnapshot,
    *,
    player_id: str | None,
    player_name: str | None,
) -> tuple[dict | None, str]:
    match = resolve_snapshot_player(
        player_entries=snapshot.normalized_player_stats.values(),
        player_id=player_id,
        player_name=player_name,
    )
    return match.entry, match.strategy


def get_player_stat(
    snapshot: EventSnapshot,
    player_id: str | None,
    stat_key: str,
    *,
    player_name: str | None = None,
) -> float | None:
    return _rule_get_player_stat(snapshot, player_id, stat_key, player_name=player_name)


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
    return compute_combo_stat(snapshot, player_id, components, player_name=player_name)


def get_player_milestone_stat(
    snapshot: EventSnapshot,
    player_id: str | None,
    market_type: str,
    *,
    player_name: str | None = None,
) -> tuple[float | None, list[str]]:
    component_keys = list(_SNAPSHOT_DERIVED_MARKET_COMPONENTS.get(market_type) or ())
    if not component_keys:
        return None, []

    component_values: list[float] = []
    missing_keys: list[str] = []
    for key in component_keys:
        value = get_player_stat(snapshot, player_id, key, player_name=player_name)
        if value is None:
            missing_keys.append(key)
            continue
        component_values.append(value)

    if missing_keys:
        return None, missing_keys

    qualifying_categories = sum(1 for value in component_values if value >= 10.0)
    threshold = 3 if market_type == 'player_triple_double' else 2
    return (2.0 if qualifying_categories >= threshold else 0.0), []


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


def _is_high_confidence_player_event_match(leg: Leg) -> bool:
    identity_is_confident = leg.identity_match_confidence == 'HIGH' or (
        bool(leg.resolved_player_id) and float(leg.resolution_confidence or 0.0) >= 0.85
    )
    event_is_confident = leg.event_resolution_confidence == 'high' or (
        bool(leg.event_id)
        and len(leg.event_candidates or []) <= 1
        and not leg.event_review_reason_code
    )
    return identity_is_confident and event_is_confident


def _player_confirmed_dnp(provider: ResultsProvider, player: str, event_id: str | None) -> bool | None:
    if not event_id:
        return None
    did_appear_fn = getattr(provider, 'did_player_appear', None)
    if callable(did_appear_fn):
        try:
            appeared = did_appear_fn(player, event_id=event_id)
        except TypeError:
            appeared = did_appear_fn(player, event_id)
        except Exception:
            appeared = None
        if appeared is False:
            return True
        if appeared is True:
            return False
    return None


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



def _is_final_event_status(status: str | None) -> bool:
    return str(status or '').strip().lower() in {'final', 'complete', 'completed', 'closed', 'settled', 'post'}


def _to_int_score(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalized_team_key(value: str | None) -> str:
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


def _snapshot_team_side(event_snapshot: EventSnapshot, team: str | None) -> str | None:
    if not team:
        return None
    normalized = _normalized_team_key(team)
    if not normalized:
        return None

    def _candidates(team_obj: dict[str, object]) -> set[str]:
        return {
            _normalized_team_key(str(team_obj.get('id') or '')),
            _normalized_team_key(str(team_obj.get('abbr') or '')),
            _normalized_team_key(str(team_obj.get('name') or '')),
        }

    home_candidates = _candidates(event_snapshot.home_team or {})
    away_candidates = _candidates(event_snapshot.away_team or {})
    for key, team_obj in (event_snapshot.normalized_team_map or {}).items():
        team_side = None
        key_norm = _normalized_team_key(str(key))
        obj_candidates = _candidates(team_obj)
        if key_norm in home_candidates or obj_candidates & home_candidates:
            team_side = 'home'
        elif key_norm in away_candidates or obj_candidates & away_candidates:
            team_side = 'away'
        if team_side and normalized in ({key_norm} | obj_candidates):
            return team_side

    if normalized in home_candidates:
        return 'home'
    if normalized in away_candidates:
        return 'away'
    return None


def _snapshot_team_result_payload(event_snapshot: EventSnapshot) -> dict[str, object]:
    result = dict(event_snapshot.normalized_event_result or {})
    event_status = str(result.get('event_status') or event_snapshot.event_status or '').strip() or None
    home_score = result.get('home_score')
    away_score = result.get('away_score')
    if not isinstance(home_score, int):
        home_score = _to_int_score((event_snapshot.home_team or {}).get('score'))
    if not isinstance(away_score, int):
        away_score = _to_int_score((event_snapshot.away_team or {}).get('score'))
    margin = result.get('margin')
    if not isinstance(margin, int) and isinstance(home_score, int) and isinstance(away_score, int):
        margin = home_score - away_score
    combined_total = result.get('combined_total')
    if not isinstance(combined_total, int) and isinstance(home_score, int) and isinstance(away_score, int):
        combined_total = home_score + away_score
    winner = result.get('winner')
    if winner not in {'home', 'away', 'push'} and isinstance(margin, int):
        if margin > 0:
            winner = 'home'
        elif margin < 0:
            winner = 'away'
        else:
            winner = 'push'
    return {
        'event_status': event_status,
        'is_final': bool(result.get('is_final')) if result.get('is_final') is not None else _is_final_event_status(event_status),
        'home_score': home_score,
        'away_score': away_score,
        'margin': margin,
        'combined_total': combined_total,
        'winner': winner,
    }


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
        'snapshot_stat_diagnostics': {
            'used_snapshot': False,
            'provider_fallback_used': False,
            'requested_stat_key': None,
            'required_component_stat_keys': [],
            'player_id_resolved': bool(leg.resolved_player_id),
            'player_snapshot_found': False,
            'player_match_result': 'not_attempted',
            'missing_snapshot_stat_key': None,
            'missing_snapshot_stat_keys': [],
            'snapshot_coverage': None,
            'event_status_used': None,
            'team_snapshot_fields_used': [],
            'missing_snapshot_event_fields': [],
            'settlement_path': 'provider',
        },
    }


def _aggregate_snapshot_run_diagnostics(graded: list[GradedLeg]) -> dict[str, object]:
    snapshot_stats_used = 0
    provider_fallbacks = 0
    missing_snapshot_keys: set[str] = set()
    players_missing_stats: set[str] = set()
    event_ids: set[str] = set()
    bet_dates: set[str] = set()
    sports: set[str] = set()
    leagues: set[str] = set()
    market_snapshot_details: list[dict[str, object]] = []

    for item in graded:
        leg = item.leg
        if leg:
            if leg.event_id:
                event_ids.add(str(leg.event_id))
            elif leg.matched_event_id:
                event_ids.add(str(leg.matched_event_id))

            selected_date = leg.selected_bet_date or leg.matched_event_date
            if selected_date:
                bet_dates.add(str(selected_date))

            if leg.sport:
                sport = str(leg.sport)
                sports.add(sport)
                leagues.add(sport)

        settlement_diag = item.settlement_diagnostics or {}
        snapshot_diag = settlement_diag.get('snapshot_stat_diagnostics') or {}
        market_type = str(leg.market_type) if leg and leg.market_type else 'unknown'
        requested_stat_key = snapshot_diag.get('requested_stat_key')
        stat_family = 'unknown'
        if requested_stat_key:
            stat_family = str(requested_stat_key)
        elif '_' in market_type:
            stat_family = market_type.split('_', 1)[1]
        market_snapshot_details.append({
            'market_type': market_type,
            'stat_family': stat_family,
            'snapshot_used': bool(snapshot_diag.get('used_snapshot')),
            'provider_fallback': bool(snapshot_diag.get('provider_fallback_used')),
            'used_snapshot': bool(snapshot_diag.get('used_snapshot')),
            'provider_fallback_used': bool(snapshot_diag.get('provider_fallback_used')),
            'requested_stat_key': requested_stat_key,
            'required_component_stat_keys': list(snapshot_diag.get('required_component_stat_keys') or []),
            'player_id_resolved': bool(snapshot_diag.get('player_id_resolved')),
            'player_snapshot_found': bool(snapshot_diag.get('player_snapshot_found')),
            'player_match_result': snapshot_diag.get('player_match_result'),
            'missing_snapshot_stat_key': snapshot_diag.get('missing_snapshot_stat_key'),
            'missing_snapshot_stat_keys': list(snapshot_diag.get('missing_snapshot_stat_keys') or []),
            'event_id': str(((leg.event_id or leg.matched_event_id) if leg else '') or ''),
            'sport': str((leg.sport if leg else '') or ''),
            'league': str((leg.sport if leg else '') or ''),
        })
        if snapshot_diag.get('used_snapshot'):
            snapshot_stats_used += 1
        if snapshot_diag.get('provider_fallback_used'):
            provider_fallbacks += 1
        missing_key = snapshot_diag.get('missing_snapshot_stat_key')
        if missing_key:
            missing_snapshot_keys.add(str(missing_key))
        for key in snapshot_diag.get('missing_snapshot_stat_keys') or []:
            if key:
                missing_snapshot_keys.add(str(key))
        if snapshot_diag.get('player_id_resolved') and not snapshot_diag.get('player_snapshot_found'):
            player_name = item.resolved_player_name or (item.leg.player if item.leg else None)
            if player_name:
                players_missing_stats.add(str(player_name))

    return {
        'snapshot_stats_used': snapshot_stats_used,
        'provider_fallbacks': provider_fallbacks,
        'missing_snapshot_keys': sorted(missing_snapshot_keys),
        'players_missing_stats': sorted(players_missing_stats),
        'event_ids': sorted(event_ids),
        'bet_dates': sorted(bet_dates),
        'sports': sorted(sports),
        'leagues': sorted(leagues),
        'market_snapshot_details': market_snapshot_details,
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
        'confidence_score': graded.confidence_score,
        'confidence_breakdown': graded.confidence_breakdown,
        'player_match_score': graded.player_match_score,
        'event_match_score': graded.event_match_score,
        'stat_parse_score': graded.stat_parse_score,
        'ocr_quality_score': graded.ocr_quality_score,
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
    leg_confidence = score_leg_confidence(leg, input_source_path=input_source_path)
    settlement_diagnostics['confidence_score'] = leg_confidence.confidence_score
    settlement_diagnostics['confidence_breakdown'] = leg_confidence.as_dict()
    settlement_diagnostics['player_match_score'] = leg_confidence.player_match_score
    settlement_diagnostics['event_match_score'] = leg_confidence.event_match_score
    settlement_diagnostics['stat_parse_score'] = leg_confidence.stat_parse_score
    settlement_diagnostics['ocr_quality_score'] = leg_confidence.ocr_quality_score
    base_kwargs['settlement_diagnostics'] = settlement_diagnostics

    def explained(
        *,
        settlement: str,
        reason: str,
        reason_code: str,
        reason_message: str,
        review_reason: str | None = None,
        actual_value: float | None = None,
        progress: float | None = None,
        **kwargs,
    ) -> GradedLeg:
        if settlement in {'unmatched', 'pending', 'void', 'review'} and settlement_diagnostics.get('unmatched_reason_code') is None:
            settlement_diagnostics['unmatched_reason_code'] = reason_code
        graded = GradedLeg(
            leg=leg,
            settlement=settlement,  # type: ignore[arg-type]
            reason=reason,
            actual_value=actual_value,
            progress=progress,
            review_reason=review_reason,
            confidence_score=leg_confidence.confidence_score,
            confidence_breakdown=leg_confidence.as_dict(),
            player_match_score=leg_confidence.player_match_score,
            event_match_score=leg_confidence.event_match_score,
            stat_parse_score=leg_confidence.stat_parse_score,
            ocr_quality_score=leg_confidence.ocr_quality_score,
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
        snapshot_diag = settlement_diagnostics.get('snapshot_stat_diagnostics')
        team_key = leg.team
        lookup_team = team_key
        if leg.market_type == 'game_total' and not lookup_team:
            event_label = leg.event_label or ''
            if ' @ ' in event_label:
                _, home = event_label.split(' @ ', 1)
                lookup_team = home
        if not lookup_team:
            return explained(settlement='unmatched', reason='No team/event context identified', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='No team/event context identified', explanation_reason='no valid same-team game found')

        snapshot_settlement = None
        if isinstance(snapshot_diag, dict):
            snapshot_diag['requested_stat_key'] = leg.market_type
            snapshot_diag['player_id_resolved'] = False
            snapshot_diag['player_snapshot_found'] = False
            snapshot_diag['player_match_result'] = 'not_applicable_team_market'

        if event_snapshot is not None and isinstance(snapshot_diag, dict):
            payload = _snapshot_team_result_payload(event_snapshot)
            snapshot_diag['event_status_used'] = payload.get('event_status')
            snapshot_diag['team_snapshot_fields_used'] = ['event_status', 'home_score', 'away_score', 'margin', 'combined_total', 'winner']
            missing_fields: list[str] = []
            if not payload.get('is_final'):
                missing_fields.append('event_not_final')
            if payload.get('home_score') is None:
                missing_fields.append('home_score')
            if payload.get('away_score') is None:
                missing_fields.append('away_score')

            team_side = _snapshot_team_side(event_snapshot, leg.team)
            if leg.market_type in {'moneyline', 'spread'} and not team_side:
                missing_fields.append('team_side')
            if leg.market_type == 'spread' and leg.line is None:
                missing_fields.append('line')
            if leg.market_type == 'game_total' and (leg.line is None or leg.direction is None):
                missing_fields.append('line_or_direction')

            snapshot_diag['missing_snapshot_event_fields'] = missing_fields
            snapshot_diag['missing_snapshot_stat_keys'] = list(missing_fields)
            snapshot_diag['missing_snapshot_stat_key'] = missing_fields[0] if missing_fields else None

            if not missing_fields:
                snapshot_diag['used_snapshot'] = True
                snapshot_diag['provider_fallback_used'] = False
                snapshot_diag['settlement_path'] = 'snapshot'
                settlement_diagnostics['stat_source'] = 'snapshot'
                settlement_diagnostics['stat_lookup_result'] = 'found'
                settlement_diagnostics['stat_extraction_worked'] = True
                margin = int(payload['margin'])
                combined_total = int(payload['combined_total'])
                if leg.market_type == 'moneyline':
                    won = (margin > 0 and team_side == 'home') or (margin < 0 and team_side == 'away')
                    snapshot_settlement = explained(
                        settlement='win' if won else 'loss',
                        actual_value=1.0 if won else 0.0,
                        reason=f'{leg.team} in {leg.event_label}: ' + ('team won game' if won else 'team lost game'),
                        reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE,
                        reason_message='Team won game' if won else 'Team lost game',
                        explanation_reason='event resolved',
                    )
                elif leg.market_type == 'spread':
                    covered_value = margin + float(leg.line)
                    if covered_value == 0:
                        snapshot_settlement = explained(
                            settlement='push',
                            actual_value=float(margin),
                            reason=f'{leg.team} margin {margin} landed exactly on spread {leg.line}',
                            reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH,
                            reason_message=f'{margin} landed exactly on spread {leg.line}',
                            explanation_reason='event resolved',
                        )
                    else:
                        won = covered_value > 0
                        snapshot_settlement = explained(
                            settlement='win' if won else 'loss',
                            actual_value=float(margin),
                            reason=f'{leg.team} margin {margin} vs spread {leg.line} in {leg.event_label}',
                            reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE,
                            reason_message=f'{margin} vs spread {leg.line}',
                            explanation_reason='event resolved',
                        )
                elif leg.market_type == 'game_total':
                    if combined_total == leg.line:
                        snapshot_settlement = explained(
                            settlement='push',
                            actual_value=float(combined_total),
                            reason='Game total landed exactly on line',
                            reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH,
                            reason_message=f'{combined_total} landed exactly on line {leg.line}',
                            explanation_reason='event resolved',
                        )
                    else:
                        won = combined_total > leg.line if leg.direction == 'over' else combined_total < leg.line
                        comparator = 'above' if combined_total > leg.line else 'below'
                        snapshot_settlement = explained(
                            settlement='win' if won else 'loss',
                            actual_value=float(combined_total),
                            reason=f'Game total {combined_total} vs {leg.direction} {leg.line} in {leg.event_label}',
                            reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if comparator == 'above' else reason_codes.ACTUAL_STAT_BELOW_LINE,
                            reason_message=f'{combined_total} is {comparator} {leg.line}',
                            explanation_reason='event resolved',
                        )

            if snapshot_settlement is not None:
                return snapshot_settlement
            snapshot_diag['provider_fallback_used'] = True
            snapshot_diag['settlement_path'] = 'provider_fallback'

        team_result = provider.get_team_result(lookup_team, event_id=leg.event_id)
        if not team_result:
            status = _event_status(provider, leg.event_id)
            if status is not None and not _is_final_event_status(status):
                return explained(settlement='live', reason='Game is in progress', reason_code=reason_codes.EVENT_NOT_FINAL, reason_message='Game is in progress', explanation_reason='event unresolved')
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
        roster_mismatch = any('not on either roster' in warning.lower() for warning in validation.warnings)
        if roster_mismatch:
            code = reason_codes.PLAYER_NOT_FOUND_ON_EVENT_ROSTER

        high_confidence_match = _is_high_confidence_player_event_match(leg)
        confirmed_dnp = roster_mismatch and high_confidence_match and _player_confirmed_dnp(provider, player_lookup_name, leg.event_id)
        if confirmed_dnp:
            settlement_diagnostics['event_match_rejection_reason'] = '; '.join(validation.warnings)
            settlement_diagnostics['settlement_failure_reason'] = 'player did not play'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_DID_NOT_PLAY
            return explained(
                settlement='void',
                reason='Leg voided: player did not appear in the matched game.',
                reason_code=reason_codes.PLAYER_DID_NOT_PLAY,
                reason_message='Player did not appear in the matched game',
                explanation_reason='player did not appear in box score / game log',
                player_found_in_boxscore=False,
            )

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

    stat_rule = get_stat_rule(leg.sport, leg.market_type)
    snapshot_supported_markets = set(_SNAPSHOT_DERIVED_MARKET_COMPONENTS)
    if stat_rule is not None:
        snapshot_supported_markets.add(leg.market_type)
    used_snapshot = False
    snapshot_entry = None
    snapshot_diag = settlement_diagnostics.get('snapshot_stat_diagnostics')
    if isinstance(snapshot_diag, dict):
        snapshot_diag['player_id_resolved'] = bool(leg.resolved_player_id)
    if event_snapshot is not None and leg.market_type in snapshot_supported_markets:
        if isinstance(snapshot_diag, dict):
            requested_stat_key = stat_rule.stat_dependencies[0] if stat_rule and len(stat_rule.stat_dependencies) == 1 else leg.market_type
            snapshot_diag['requested_stat_key'] = requested_stat_key
            snapshot_diag['required_component_stat_keys'] = list(_SNAPSHOT_DERIVED_MARKET_COMPONENTS.get(leg.market_type) or [])
            snapshot_diag['snapshot_coverage'] = event_snapshot.get_stat_coverage()
        snapshot_entry, player_match_result = _snapshot_player_match_result(
            event_snapshot,
            player_id=leg.resolved_player_id,
            player_name=player_lookup_name,
        )
        if snapshot_entry:
            matched_boxscore_player_name = snapshot_entry.get('display_name')
            if isinstance(snapshot_diag, dict):
                snapshot_diag['player_snapshot_found'] = True
                snapshot_diag['player_match_result'] = player_match_result
        elif isinstance(snapshot_diag, dict):
            snapshot_diag['player_match_result'] = 'match_failed'

    detail_lookup = getattr(provider, 'get_player_result_details', None)
    actual_value = None
    if event_snapshot is not None and leg.market_type in snapshot_supported_markets:
        if stat_rule is not None:
            actual_value = stat_rule.compute_actual_value(event_snapshot, leg.resolved_player_id, player_lookup_name)
            if isinstance(snapshot_diag, dict) and actual_value is None:
                snapshot_diag['missing_snapshot_stat_key'] = leg.market_type
                snapshot_diag['missing_snapshot_stat_keys'] = list(stat_rule.stat_dependencies)
        elif leg.market_type in _SNAPSHOT_DERIVED_MARKET_COMPONENTS:
            actual_value, missing_keys = get_player_milestone_stat(event_snapshot, leg.resolved_player_id, leg.market_type, player_name=player_lookup_name)
            if isinstance(snapshot_diag, dict):
                snapshot_diag['required_component_stat_keys'] = list(_SNAPSHOT_DERIVED_MARKET_COMPONENTS[leg.market_type])
                snapshot_diag['missing_snapshot_stat_keys'] = list(missing_keys)
                snapshot_diag['missing_snapshot_stat_key'] = missing_keys[0] if missing_keys else None
        used_snapshot = actual_value is not None
        if isinstance(snapshot_diag, dict):
            snapshot_diag['used_snapshot'] = used_snapshot

    if actual_value is None and callable(detail_lookup):
        if isinstance(snapshot_diag, dict) and event_snapshot is not None and leg.market_type in snapshot_supported_markets:
            snapshot_diag['provider_fallback_used'] = True
        details = detail_lookup(player_lookup_name, leg.market_type, event_id=leg.event_id)
        if details:
            actual_value = details.get('actual_value')
            matched_boxscore_player_name = details.get('matched_boxscore_player_name')
    if actual_value is None:
        if isinstance(snapshot_diag, dict) and event_snapshot is not None and leg.market_type in snapshot_supported_markets:
            snapshot_diag['provider_fallback_used'] = True
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

    live_progress = _build_live_progress_payload(
        leg,
        actual_value=actual_value,
        line=leg.line,
        component_values=component_values_dict,
    )
    live_timeline = _build_live_progress_timeline(
        leg,
        event_snapshot,
        player_name=player_lookup_name,
    )

    status = (event_snapshot.event_status if event_snapshot is not None else None) or _event_status(provider, leg.event_id)
    is_final_status = _is_final_event_status(status) if status is not None else False
    kill_reason: str | None = None
    if (
        stat_rule is not None
        and stat_rule.supports_kill_moment
        and actual_value is not None
        and leg.line is not None
        and leg.direction is not None
    ):
        normalized_status = 'final' if is_final_status else (str(status).lower() if status is not None else None)
        kill_reason = stat_rule.kill_condition(float(actual_value), float(leg.line), leg.direction, normalized_status)

    if status is not None and not is_final_status:
        if kill_reason is not None:
            settlement_diagnostics['stat_extraction_worked'] = True
            return explained(
                settlement='loss',
                reason=f'{player_lookup_name} in {leg.event_label}: actual {actual_value} vs line {leg.line}',
                reason_code=reason_codes.ACTUAL_STAT_ABOVE_LINE if leg.direction == 'under' else reason_codes.ACTUAL_STAT_BELOW_LINE,
                reason_message=f'Kill moment triggered: {kill_reason}',
                explanation_reason='event resolved',
                actual_value=float(actual_value),
                progress=_compute_leg_progress(actual_value=float(actual_value), line=leg.line),
                component_values=component_values_dict,
                stat_components=stat_components,
                computed_total=computed_total,
                live_progress=live_progress,
                live_progress_timeline=live_timeline,
                matched_boxscore_player_name=matched_boxscore_player_name or leg.resolved_player_name or leg.player,
                player_found_in_boxscore=True,
                kill_moment=True,
                kill_reason=kill_reason,
            )
        settlement_diagnostics['settlement_failure_reason'] = 'event not final'
        settlement_diagnostics['unmatched_reason_code'] = reason_codes.EVENT_NOT_FINAL
        if live_progress is not None:
            settlement_diagnostics['live_progress'] = live_progress
        if live_timeline:
            settlement_diagnostics['live_progress_timeline'] = live_timeline
        return explained(
            settlement='live',
            reason='Game is in progress',
            reason_code=reason_codes.EVENT_NOT_FINAL,
            reason_message='Game is in progress',
            explanation_reason='event unresolved',
            actual_value=float(actual_value) if actual_value is not None else None,
            progress=_compute_leg_progress(actual_value=float(actual_value) if actual_value is not None else None, line=leg.line),
            component_values=component_values_dict,
            stat_components=stat_components,
            computed_total=computed_total,
            live_progress=live_progress,
            live_progress_timeline=live_timeline,
        )

    settlement_diagnostics['stat_lookup_result'] = 'found' if actual_value is not None else 'missing'
    if leg.line is None or leg.direction is None:
        return explained(settlement='unmatched', reason='Missing values required for settlement', reason_code=reason_codes.MISSING_SETTLEMENT_INPUTS, reason_message='Missing values required for settlement', explanation_reason='stat unavailable', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
    if actual_value is None:
        status = _event_status(provider, leg.event_id)
        if status is not None and not _is_final_event_status(status):
            settlement_diagnostics['settlement_failure_reason'] = 'event not final'
            settlement_diagnostics['unmatched_reason_code'] = reason_codes.EVENT_NOT_FINAL
            if live_progress is not None:
                settlement_diagnostics['live_progress'] = live_progress
            if live_timeline:
                settlement_diagnostics['live_progress_timeline'] = live_timeline
            return explained(settlement='live', reason='Game is in progress', reason_code=reason_codes.EVENT_NOT_FINAL, reason_message='Game is in progress', explanation_reason='event unresolved', actual_value=float(actual_value) if actual_value is not None else None, progress=_compute_leg_progress(actual_value=float(actual_value) if actual_value is not None else None, line=leg.line), component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, live_progress=live_progress, live_progress_timeline=live_timeline)
        appeared = None
        if leg.event_id:
            dnp_confirmed = _player_confirmed_dnp(provider, player_lookup_name, leg.event_id)
            if dnp_confirmed is not None:
                appeared = not dnp_confirmed
            if appeared is False:
                dnp_mode = _dnp_settlement_mode(provider)
                dnp_warnings = ['Player did not appear in box score', 'Leg marked void/review instead of graded']
                dnp_kwargs = {**base_kwargs, 'validation_warnings': dnp_warnings}
                base_kwargs.update(dnp_kwargs)
                if dnp_mode == 'NEEDS_REVIEW':
                    settlement_diagnostics['settlement_failure_reason'] = 'player did not play'
                    settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_DID_NOT_PLAY
                    return explained(settlement='unmatched', reason='Leg voided: player did not appear in the matched game.', reason_code=reason_codes.DNP_REVIEW_REQUIRED, reason_message='Player did not appear in box score', review_reason='Player did not appear in box score', explanation_reason='Leg marked void/review instead of graded', player_found_in_boxscore=False, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)
                settlement_diagnostics['settlement_failure_reason'] = 'player did not play'
                settlement_diagnostics['unmatched_reason_code'] = reason_codes.PLAYER_DID_NOT_PLAY
                return explained(settlement='void', reason='Leg voided: player did not appear in the matched game.', reason_code=reason_codes.PLAYER_DID_NOT_PLAY, reason_message='Player did not appear in box score', explanation_reason='player did not appear in box score / game log', player_found_in_boxscore=False, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)
        settlement_diagnostics['settlement_failure_reason'] = 'stat not found'
        settlement_diagnostics['unmatched_reason_code'] = reason_codes.STAT_NOT_FOUND
        review_reason = 'combo component stats incomplete' if market_entry and market_entry.get('market_type') == 'combo_stat' else 'Matched event but no stat result'
        return explained(settlement='unmatched', reason='Matched event but no stat result', reason_code=reason_codes.MISSING_STAT_SOURCE, reason_message='Matched event but no stat result', review_reason=review_reason, explanation_reason='Matched event but no stat result', player_found_in_boxscore=appeared, component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total, matched_boxscore_player_name=matched_boxscore_player_name)

    if leg.direction in {'yes', 'no'}:
        is_yes = actual_value >= 1.0
        won = is_yes if leg.direction == 'yes' else not is_yes
        reason_code = reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE
        readable = 'milestone achieved' if is_yes else 'milestone not achieved'
        settlement_diagnostics['stat_extraction_worked'] = True
        return explained(
            settlement='win' if won else 'loss',
            actual_value=float(actual_value),
            progress=_compute_leg_progress(actual_value=float(actual_value), line=leg.line),
            reason=f'{player_lookup_name} in {leg.event_label}: {readable}',
            reason_code=reason_code,
            reason_message=readable,
            explanation_reason='event resolved',
            component_values=component_values_dict,
            stat_components=stat_components,
            computed_total=computed_total,
            matched_boxscore_player_name=matched_boxscore_player_name or leg.resolved_player_name or leg.player,
            player_found_in_boxscore=True,
        )

    if leg.direction == 'over':
        won = actual_value > leg.line
        if actual_value == leg.line:
            return explained(settlement='push', actual_value=float(actual_value), progress=_compute_leg_progress(actual_value=float(actual_value), line=leg.line), reason='Landed exactly on line', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{actual_value} landed exactly on {leg.line}', explanation_reason='event resolved', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
        reason_code = reason_codes.ACTUAL_STAT_ABOVE_LINE if won else reason_codes.ACTUAL_STAT_BELOW_LINE
        comparison = 'above' if won else 'below'
        readable = f'{actual_value} is {comparison} {leg.line}'
    else:
        won = actual_value < leg.line
        if actual_value == leg.line:
            return explained(settlement='push', actual_value=float(actual_value), progress=_compute_leg_progress(actual_value=float(actual_value), line=leg.line), reason='Landed exactly on line', reason_code=reason_codes.ACTUAL_STAT_EQUAL_PUSH, reason_message=f'{actual_value} landed exactly on {leg.line}', explanation_reason='event resolved', component_values=component_values_dict, stat_components=stat_components, computed_total=computed_total)
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
        progress=_compute_leg_progress(actual_value=float(actual_value), line=leg.line),
        reason=f'{player_lookup_name} in {leg.event_label}: actual {actual_value} vs line {leg.line}',
        reason_code=reason_code,
        reason_message=readable,
        explanation_reason='event resolved',
        component_values=component_values_dict,
        stat_components=stat_components,
        computed_total=computed_total,
        matched_boxscore_player_name=matched_boxscore_player_name or leg.resolved_player_name or leg.player,
        player_found_in_boxscore=True,
        kill_moment=kill_reason is not None and not won,
        kill_reason=kill_reason if not won else None,
    )


def build_slip_groups(legs: list[Leg]) -> list[SlipGroup]:
    grouped: dict[tuple[str, str], list[Leg]] = {}
    for leg in legs:
        event_id = str(leg.event_id or '').strip()
        sport = str(leg.sport or '').strip()
        if not event_id or not sport:
            continue
        grouped.setdefault((event_id, sport), []).append(leg)

    slip_groups: list[SlipGroup] = []
    for index, ((event_id, sport), group_legs) in enumerate(grouped.items(), start=1):
        group_id = f"sgp-{sport.lower()}-{event_id}-{index}"
        is_sgp = len(group_legs) > 1
        for leg in group_legs:
            leg.group_id = group_id
            leg.event_id = event_id
            leg.is_same_game_parlay = is_sgp
        slip_groups.append(SlipGroup(group_id=group_id, event_id=event_id, sport=sport, legs=group_legs))
    return slip_groups


def _sgp_diagnostics(groups: list[SlipGroup]) -> dict[str, object]:
    return {
        'sgp_group_count': len(groups),
        'sgp_groups': [
            {
                'group_id': group.group_id,
                'event_id': group.event_id,
                'sport': group.sport,
                'leg_count': len(group.legs),
                'is_same_game_parlay': len(group.legs) > 1,
            }
            for group in groups
        ],
        'legs_per_group': {group.group_id: len(group.legs) for group in groups},
    }


def _compute_parlay_closeness(graded_legs: list[GradedLeg]) -> tuple[float | None, dict | None, dict | None]:
    finalized_settlements = {'win', 'loss', 'push'}
    distances: list[tuple[GradedLeg, float]] = []
    losing: list[tuple[GradedLeg, float]] = []
    for item in graded_legs:
        if item.settlement not in finalized_settlements or item.settlement == 'void':
            continue
        if item.line is None or item.actual_value is None:
            continue
        distance = abs(float(item.actual_value) - float(item.line))
        distances.append((item, distance))
        if item.settlement == 'loss':
            losing.append((item, distance))

    if not distances:
        return None, None, None

    avg_distance = sum(distance for _, distance in distances) / len(distances)
    score = max(0.0, min(100.0, round(100.0 / (1.0 + avg_distance), 1)))

    def _miss_leg_payload(pair: tuple[GradedLeg, float] | None) -> dict | None:
        if pair is None:
            return None
        leg, distance = pair
        diff = float(leg.actual_value) - float(leg.line)
        miss_amount = abs(diff)
        direction = '-' if diff < 0 else '+'
        return {
            'leg': leg.leg.raw_text,
            'player_or_team': leg.leg.player or leg.leg.team,
            'market': leg.normalized_market or leg.leg.market_type,
            'target_line': leg.line,
            'final_stat': leg.actual_value,
            'miss_distance': round(distance, 2),
            'delta': round(diff, 2),
            'delta_display': f"{direction}{round(miss_amount, 2):g}",
            'event_name': leg.matched_event,
        }

    closest = min(losing, key=lambda row: row[1]) if losing else None
    worst = max(losing, key=lambda row: row[1]) if losing else None
    return score, _miss_leg_payload(closest), _miss_leg_payload(worst)

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
    legs = parsed_legs
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

    slip_groups = build_slip_groups(resolved_legs)
    snapshots_by_event_id: dict[str, EventSnapshot] = {}
    from .providers.espn_provider import ESPNNBAResultsProvider
    if isinstance(provider, ESPNNBAResultsProvider):
        router = ProviderRouter(box_score_provider=provider, play_by_play_provider=play_by_play_provider)
        event_to_legs = {group.event_id: group.legs for group in slip_groups if group.event_id}
        if event_to_legs:
            snapshot_service = EventSnapshotService(play_by_play_provider=play_by_play_provider)
            snapshot_cache = get_event_snapshot_cache()
            event_dates = {
                event_id: next((leg.matched_event_date for leg in grouped_legs if leg.matched_event_date), '')
                for event_id, grouped_legs in event_to_legs.items()
            }
            event_sports = {
                event_id: next((leg.sport for leg in grouped_legs if leg.sport), None)
                for event_id, grouped_legs in event_to_legs.items()
            }
            include_play_by_play_event_ids = {
                event_id
                for event_id, grouped_legs in event_to_legs.items()
                if any(router.route(leg.market_type).data_source == 'play_by_play' for leg in grouped_legs)
            }
            try:
                for event_id in event_to_legs.keys():
                    include_play_by_play = event_id in include_play_by_play_event_ids
                    snapshots_by_event_id[event_id] = snapshot_cache.get_snapshot(
                        sport=event_sports.get(event_id),
                        event_id=event_id,
                        include_play_by_play=include_play_by_play,
                        fetcher=lambda event_id=event_id, include_play_by_play=include_play_by_play: snapshot_service.get_event_snapshot(
                            event_id,
                            event_date=(event_dates.get(event_id) or None),
                            include_play_by_play=include_play_by_play,
                        ),
                    )
                snapshots_by_event_id = {k: v for k, v in snapshots_by_event_id.items() if v is not None}
            except Exception:
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

    run_snapshot_diagnostics = _aggregate_snapshot_run_diagnostics(graded)
    if 'debug' in (code_path or '').lower():
        print(f"snapshot diagnostics: {run_snapshot_diagnostics}")

    settlements = [item.settlement for item in graded]
    if any(settlement == 'loss' for settlement in settlements):
        overall = 'lost'
    elif settlements and all(settlement == 'win' for settlement in settlements):
        overall = 'cashed'
    elif any(settlement in {'pending', 'live'} for settlement in settlements) and not any(settlement in {'unmatched', 'review'} for settlement in settlements):
        overall = 'pending'
    else:
        overall = 'needs_review'

    leg_confidence_scores = [float(item.confidence_score) for item in graded if item.confidence_score is not None]
    slip_confidence = score_slip_confidence(leg_confidence_scores)
    confidence_tier, confidence_action = confidence_recommendation(slip_confidence)

    if confidence_action == 'needs_review':
        overall = 'needs_review'

    slip_hash = generate_slip_hash(resolved_legs)
    _, duplicate_slip_count, unique_slip_count = register_slip_hash(slip_hash)
    response = GradeResponse(
        overall=overall,
        legs=graded,
        slip_progress=_compute_slip_progress(graded),
        slip_hash=slip_hash,
        leg_count=len(resolved_legs),
        sport_set=sorted({str(leg.sport) for leg in resolved_legs if leg.sport}),
        event_ids=sorted({str(leg.event_id or leg.matched_event_id) for leg in resolved_legs if (leg.event_id or leg.matched_event_id)}),
        grading_diagnostics={
            'snapshot': run_snapshot_diagnostics,
            'sgp': _sgp_diagnostics(slip_groups),
            'fingerprint': {
                'duplicate_slip_count': duplicate_slip_count,
                'unique_slip_count': unique_slip_count,
            },
        },
        slip_confidence=slip_confidence,
        confidence_tier=confidence_tier,
        confidence_recommendation=confidence_action,
    )
    closeness_score, closest_miss_leg, worst_miss_leg = _compute_parlay_closeness(graded)
    response.parlay_closeness_score = closeness_score
    response.closest_miss_leg = closest_miss_leg
    response.worst_miss_leg = worst_miss_leg
    response.grading_diagnostics['snapshot'].update(get_event_snapshot_cache().get_stats())
    try:
        sold_leg_explanations = explain_sold_legs(response, snapshots_by_event_id)
    except Exception:
        sold_leg_explanations = []
    response.sold_leg_explanations = sold_leg_explanations
    if sold_leg_explanations:
        by_event_market = {(item.event_id, item.market_type): item for item in sold_leg_explanations}
        for idx, graded_leg in enumerate(response.legs):
            explanation = by_event_market.get((graded_leg.leg.event_id, graded_leg.leg.market_type))
            if explanation is not None and graded_leg.settlement == 'loss':
                response.legs[idx].sold_leg_explanation = explanation
    return response

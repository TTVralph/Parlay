from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .betstack_provider import BetStackProvider
from .line_value_analyzer import SUPPORTED_PROP_MARKETS, analyze_line_value, analyze_line_value_against_market_line
from ..models import AnalyzeLegRisk, AnalyzeSlipResponse, Leg

SUPPORTED_MARKETS = {
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_threes',
    'player_pr',
    'player_pa',
    'player_ra',
    'player_pra',
    'moneyline',
    'spread',
    'game_total',
}

COMBO_MARKETS = {'player_pr', 'player_pa', 'player_ra', 'player_pra'}
OUTCOME_DEPENDENT_MARKETS = {'moneyline', 'spread'}

PLAYER_BASELINES: dict[str, float] = {
    'player_points': 22.0,
    'player_rebounds': 6.5,
    'player_assists': 4.8,
    'player_threes': 2.4,
    'player_pr': 28.5,
    'player_pa': 26.5,
    'player_ra': 11.5,
    'player_pra': 33.0,
}

TEAM_BASELINES: dict[str, float] = {
    'spread': 0.0,
    'game_total': 228.0,
}


@dataclass(frozen=True)
class _OddsContext:
    implied_probability: float | None
    offered_american_odds: int | None


def classify_risk_label(score: float) -> str:
    if score < 3.5:
        return 'low'
    if score < 6.8:
        return 'medium'
    return 'high'


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _implied_probability(american_odds: int | None) -> float | None:
    if american_odds is None:
        return None
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return abs(american_odds) / (abs(american_odds) + 100.0)


def _subject_name(leg: Leg) -> str:
    return leg.player or leg.team or leg.raw_text


def _baseline_for_leg(leg: Leg) -> float | None:
    if leg.market_type in PLAYER_BASELINES:
        return PLAYER_BASELINES[leg.market_type]
    return TEAM_BASELINES.get(leg.market_type)


def _has_alt_line_marker(leg: Leg) -> bool:
    raw = leg.raw_text.strip().lower()
    if raw.endswith('+'):
        return True
    return bool(re.search(r'\b\d+(?:\.\d+)?\+', raw))


def _line_penalty(leg: Leg, baseline: float | None) -> tuple[float, str | None]:
    if baseline is None or leg.line is None:
        return 0.7, 'missing_baseline_fallback'

    delta = abs(leg.line - baseline)
    if leg.market_type == 'spread':
        return _clamp(delta / 3.0, 0.0, 2.8), None
    if leg.market_type == 'game_total':
        return _clamp(delta / 7.0, 0.0, 3.0), None
    return _clamp(delta / 4.5, 0.0, 3.2), None


def _direction_penalty(leg: Leg) -> float:
    if leg.direction == 'under':
        return 0.6
    if leg.direction in {'yes', 'no'}:
        return 1.2
    return 0.0


def _odds_adjustment(odds_ctx: _OddsContext) -> tuple[float, list[str]]:
    if odds_ctx.implied_probability is None:
        return 1.0, ['missing_data_confidence_penalty']

    p = odds_ctx.implied_probability
    codes: list[str] = []
    if p < 0.45:
        codes.append('longshot_price_penalty')
        return 2.0, codes
    if p < 0.50:
        codes.append('plus_money_penalty')
        return 1.3, codes
    if p > 0.60:
        codes.append('favored_price_discount')
        return -0.6, codes
    return 0.2, codes


def _line_value_text(line_label: str, has_market_data: bool, source: str | None = None) -> str:
    if not has_market_data:
        return 'Consensus line unavailable. Using statistical baseline.'
    if line_label == 'good':
        return 'Good line versus market consensus'
    if line_label == 'bad':
        return 'Less favorable line versus market consensus'
    return 'Neutral line versus market consensus'


def _friendly_explanation(subject: str, market_type: str, risk_label: str, line_value_label: str, has_market_data: bool, line_source: str | None = None) -> str:
    market_name = market_type.replace('_', ' ')
    market_part = f'{subject}: {market_name} leg graded as {risk_label} risk.'
    if has_market_data:
        line_part = {
            'good': 'Market check says you are getting a better-than-average number.',
            'bad': 'Market check says your number is worse than the average book line.',
        }.get(line_value_label, 'Market check says this line is close to average.')
    else:
        line_part = 'Consensus line unavailable. Using statistical baseline.'
    return f'{market_part} {line_part}'


def _short_advisory_text(risk_label: str, confidence: float, has_market_data: bool, line_source: str | None = None) -> str:
    confidence_label = 'high' if confidence >= 0.8 else ('medium' if confidence >= 0.55 else 'low')
    if not has_market_data:
        return f'{risk_label.title()} risk read with {confidence_label} confidence. Consensus line unavailable. Using statistical baseline.'
    return f'{risk_label.title()} risk read with {confidence_label} confidence.'


def _correlation_group_key(leg: Leg) -> str | None:
    return leg.event_id or leg.matched_event_id or leg.selected_event_id or leg.event_label or leg.matched_event_label or leg.selected_event_label


def _analyze_same_game_correlation(parsed_legs: list[Leg]) -> tuple[int, int, str, str]:
    groups: dict[str, list[Leg]] = {}
    for leg in parsed_legs:
        key = _correlation_group_key(leg)
        if key:
            groups.setdefault(key, []).append(leg)

    same_game_groups = [legs for legs in groups.values() if len(legs) > 1]
    same_game_group_count = len(same_game_groups)
    same_game_leg_count = sum(len(group) for group in same_game_groups)
    if same_game_group_count == 0:
        return 0, 0, 'low', 'No same-game grouping detected.'

    over_count = 0
    outcome_count = 0
    for group in same_game_groups:
        for leg in group:
            if leg.direction == 'over':
                over_count += 1
            if leg.market_type in OUTCOME_DEPENDENT_MARKETS:
                outcome_count += 1

    heuristic_points = 0
    notes: list[str] = []
    if over_count >= 2:
        heuristic_points += 1
        notes.append('multiple overs in the same game can increase volatility')
    if outcome_count >= 2:
        heuristic_points += 1
        notes.append('multiple outcome-dependent legs in one game can be tightly coupled')

    if heuristic_points >= 2:
        label = 'high'
    elif heuristic_points == 1:
        label = 'medium'
    else:
        label = 'medium'
        notes.append('same-game legs may move together')

    return (
        same_game_group_count,
        same_game_leg_count,
        label,
        f"Detected {same_game_leg_count} legs across {same_game_group_count} same-game group(s); " + '; '.join(notes) + '.',
    )


def analyze_leg_risk(leg: Leg, context: dict[str, Any] | None = None) -> AnalyzeLegRisk:
    market_type = leg.market_type
    subject = _subject_name(leg)
    baseline = _baseline_for_leg(leg)
    odds_ctx = _OddsContext(
        implied_probability=_implied_probability(leg.american_odds),
        offered_american_odds=leg.american_odds,
    )

    penalties: list[float] = []
    reason_codes: list[str] = []

    special_market_hint = any(token in leg.raw_text.lower() for token in ('first ', 'race to', 'first half', 'first quarter'))
    supported = market_type in SUPPORTED_MARKETS and not special_market_hint
    if not supported:
        penalties.append(3.6)
        reason_codes.append('unsupported_market')

    line_penalty, line_code = _line_penalty(leg, baseline)
    penalties.append(line_penalty)
    if line_code:
        reason_codes.append(line_code)

    direction_penalty = _direction_penalty(leg)
    if direction_penalty:
        penalties.append(direction_penalty)
        reason_codes.append('direction_volatility_penalty')

    odds_penalty, odds_codes = _odds_adjustment(odds_ctx)
    penalties.append(odds_penalty)
    reason_codes.extend(odds_codes)

    if market_type in COMBO_MARKETS:
        penalties.append(1.5)
        reason_codes.append('combo_market_inflation_penalty')

    if _has_alt_line_marker(leg):
        penalties.append(0.9)
        reason_codes.append('alt_line_inflation_penalty')

    if special_market_hint:
        penalties.append(2.2)
        reason_codes.append('special_market_uncertainty_penalty')

    parse_conf = leg.parse_confidence if leg.parse_confidence is not None else leg.confidence
    if parse_conf < 0.55:
        penalties.append(1.4)
        reason_codes.append('limited_confidence')

    raw_score = 1.2 + sum(penalties)
    risk_score = round(_clamp(raw_score, 0.0, 10.0), 2)
    risk_label = classify_risk_label(risk_score)

    confidence = _clamp(parse_conf, 0.2, 0.98)
    confidence = round(confidence if supported else confidence * 0.65, 2)

    betstack = BetStackProvider.from_env()
    odds_rows = context.get('betstack_odds_rows') if context else None
    if odds_rows is None:
        odds_rows = betstack.fetch_nba_odds()
    betstack_line = betstack.lookup_leg_line_from_odds(leg, odds_rows)
    if betstack_line and betstack_line.get('line') is not None:
        line_value = analyze_line_value_against_market_line(leg, float(betstack_line['line']), 'betstack_consensus')
    elif betstack_line and leg.market_type == 'moneyline' and betstack_line.get('american_odds') is not None:
        line_value = analyze_line_value_against_market_line(leg, float(betstack_line['american_odds']), 'betstack_consensus')
    else:
        line_value = analyze_line_value(leg)
        if line_value.market_average_line is None:
            line_value = line_value.__class__(
                market_average_line=line_value.market_average_line,
                user_line=line_value.user_line,
                line_difference=line_value.line_difference,
                line_value_score=line_value.line_value_score,
                line_value_label=line_value.line_value_label,
                line_value_source='statistical_baseline',
                providers_used=line_value.providers_used,
            )
    has_market_data = line_value.market_average_line is not None
    if leg.market_type in SUPPORTED_PROP_MARKETS and not has_market_data:
        reason_codes.append('line_value_missing_market_data')

    if not has_market_data:
        if line_value.line_value_label == 'unknown':
            reason_codes.append('line_value_unknown')
        reason_codes.append('market_comparison_unavailable')

    explanation = _friendly_explanation(subject, market_type, risk_label, line_value.line_value_label, has_market_data, line_value.line_value_source)
    short_advisory_text = _short_advisory_text(risk_label, confidence, has_market_data, line_value.line_value_source)
    line_value_text = _line_value_text(line_value.line_value_label, has_market_data, line_value.line_value_source)

    return AnalyzeLegRisk(
        leg_id=leg.leg_id,
        raw_leg_text=leg.raw_text,
        market_type=market_type,
        subject_name=subject,
        line=leg.line,
        estimated_baseline=baseline,
        risk_score=risk_score,
        risk_label=risk_label,
        short_advisory_text=short_advisory_text,
        explanation=explanation,
        confidence=confidence,
        advisory_reason_codes=sorted(set(reason_codes)),
        supported_market=supported,
        offered_american_odds=leg.american_odds,
        market_average_line=line_value.market_average_line,
        user_line=line_value.user_line,
        market_line=line_value.market_average_line,
        line_difference=line_value.line_difference,
        line_value_score=line_value.line_value_score,
        line_value_label=line_value.line_value_label,
        line_value_text=line_value_text,
        line_value_source=line_value.line_value_source,
        original_leg_text=leg.original_leg_text or leg.raw_text,
        normalized_line_value=leg.normalized_line_value if leg.normalized_line_value is not None else leg.line,
    )


def detect_trap_leg(parsed_legs: list[Leg], context: dict[str, Any] | None = None) -> tuple[AnalyzeLegRisk | None, float, list[str]]:
    if not parsed_legs:
        return None, 0.0, []

    trap_candidates: list[tuple[float, AnalyzeLegRisk, list[str]]] = []
    for leg in parsed_legs:
        analyzed = analyze_leg_risk(leg, context)
        baseline = _baseline_for_leg(leg)
        implied_probability = _implied_probability(leg.american_odds)
        reason_codes: list[str] = []
        trap_score = 0.0

        if baseline is None or leg.line is None:
            trap_score += 0.6
            reason_codes.append('trap_missing_baseline_fallback')
        else:
            delta = abs(leg.line - baseline)
            if leg.market_type == 'spread':
                line_pressure = _clamp(delta / 2.5, 0.0, 4.0)
            elif leg.market_type == 'game_total':
                line_pressure = _clamp(delta / 6.5, 0.0, 4.0)
            else:
                line_pressure = _clamp(delta / 3.6, 0.0, 4.0)
            trap_score += line_pressure
            if line_pressure > 0.0:
                reason_codes.append('trap_line_distance_penalty')

        if leg.market_type in COMBO_MARKETS:
            trap_score += 1.5
            reason_codes.append('trap_combo_market_inflation_penalty')

        if _has_alt_line_marker(leg):
            trap_score += 1.0
            reason_codes.append('trap_alt_line_penalty')

        if implied_probability is None:
            trap_score += 0.7
            reason_codes.append('trap_missing_odds_penalty')
        elif implied_probability < 0.45:
            trap_score += 1.8
            reason_codes.append('trap_longshot_odds_penalty')
        elif implied_probability < 0.5:
            trap_score += 1.0
            reason_codes.append('trap_plus_money_odds_penalty')

        trap_candidates.append((round(_clamp(trap_score, 0.0, 10.0), 2), analyzed, sorted(set(reason_codes))))

    score, trap_leg, codes = max(trap_candidates, key=lambda item: (item[0], item[1].risk_score, item[1].confidence * -1))
    return trap_leg, score, codes


def analyze_slip_risk(parsed_legs: list[Leg]) -> AnalyzeSlipResponse:
    betstack = BetStackProvider.from_env()
    odds_rows = betstack.fetch_nba_odds() if betstack.enabled else []
    shared_context = {'betstack_odds_rows': odds_rows}
    analyzed = [analyze_leg_risk(leg, context=shared_context) for leg in parsed_legs]
    if not analyzed:
        return AnalyzeSlipResponse(
            ok=False,
            message='Paste at least one leg first.',
            slip_risk_score=0.0,
            slip_risk_label='low',
            weakest_leg=None,
            safest_leg=None,
            likely_seller=None,
            trap_leg=None,
            trap_score=0.0,
            trap_reason_codes=[],
            leg_risk_scores=[],
            supported_leg_count=0,
            unsupported_leg_count=0,
            same_game_group_count=0,
            same_game_leg_count=0,
            correlation_risk_label='low',
            correlation_note='No same-game grouping detected.',
            advisory_only=True,
        )

    weighted_total = 0.0
    total_weight = 0.0
    for leg in analyzed:
        weight = 1.15 if not leg.supported_market else 1.0
        weighted_total += leg.risk_score * weight
        total_weight += weight
    slip_score = round(_clamp(weighted_total / max(total_weight, 1.0), 0.0, 10.0), 2)
    slip_label = classify_risk_label(slip_score)

    weakest = max(analyzed, key=lambda item: (item.risk_score, item.confidence * -1))
    safest = min(analyzed, key=lambda item: (item.risk_score, item.confidence * -1))
    likely_seller = weakest
    trap_leg, trap_score, trap_reason_codes = detect_trap_leg(parsed_legs, shared_context)

    supported_count = sum(1 for leg in analyzed if leg.supported_market)
    unsupported_count = len(analyzed) - supported_count
    group_count, leg_count, correlation_label, correlation_note = _analyze_same_game_correlation(parsed_legs)

    return AnalyzeSlipResponse(
        ok=True,
        message='Advisory generated using deterministic heuristics.',
        slip_risk_score=slip_score,
        slip_risk_label=slip_label,
        weakest_leg=weakest,
        safest_leg=safest,
        likely_seller=likely_seller,
        trap_leg=trap_leg,
        trap_score=trap_score,
        trap_reason_codes=trap_reason_codes,
        leg_risk_scores=analyzed,
        supported_leg_count=supported_count,
        unsupported_leg_count=unsupported_count,
        same_game_group_count=group_count,
        same_game_leg_count=leg_count,
        correlation_risk_label=correlation_label,
        correlation_note=correlation_note,
        advisory_only=True,
    )

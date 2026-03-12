from __future__ import annotations

import re
from math import prod
from typing import Any

from ..models import AnalyzeLegRisk, AnalyzeSlipResponse, Leg, RewrittenLegSuggestion
from .slip_risk_analyzer import COMBO_MARKETS, PLAYER_BASELINES, SUPPORTED_MARKETS, TEAM_BASELINES, analyze_slip_risk

MILESTONE_DOWNGRADE_MAP: dict[float, float] = {
    10.0: 8.0,
    8.0: 6.0,
    6.0: 4.0,
}

LOWER_RISK_SINGLE_MARKET: dict[str, str] = {
    'player_pra': 'player_points',
    'player_pr': 'player_points',
    'player_pa': 'player_assists',
    'player_ra': 'player_rebounds',
}

LINE_DOWNGRADE_BY_MARKET: dict[str, float] = {
    'player_points': 3.0,
    'player_rebounds': 2.0,
    'player_assists': 2.0,
    'player_threes': 1.0,
}



def _line_to_text(line: float | None) -> str:
    if line is None:
        return '—'
    if float(line).is_integer():
        return str(int(line))
    return f'{line:.1f}'.rstrip('0').rstrip('.')



def _format_leg_text(leg: Leg, override_market: str | None = None, override_line: float | None = None) -> str:
    market = override_market or leg.market_type
    subject = leg.player or leg.team or 'Selection'
    direction = (leg.direction or '').title()
    line = override_line if override_line is not None else leg.line
    if market == 'moneyline':
        return f"{subject} ML"
    market_label = market.replace('player_', '').replace('_', ' ').upper()
    if direction and line is not None:
        return f"{subject} {direction} {_line_to_text(line)} {market_label}".strip()
    if direction:
        return f"{subject} {direction} {market_label}".strip()
    if line is not None:
        return f"{subject} {_line_to_text(line)} {market_label}".strip()
    return leg.raw_text



def _find_milestone_target(leg: Leg) -> float | None:
    if leg.line is None:
        return None
    plus_value = leg.line + 0.5
    for milestone, safer in MILESTONE_DOWNGRADE_MAP.items():
        if abs(float(plus_value) - milestone) < 0.001:
            return safer - 0.5
    raw = (leg.display_line or leg.raw_text or '').lower()
    match = re.search(r'\b(10|8|6)\+\b', raw)
    if not match:
        return None
    target = MILESTONE_DOWNGRADE_MAP.get(float(match.group(1)))
    return (target - 0.5) if target is not None else None



def _standard_safer_line(leg: Leg) -> float | None:
    if leg.line is None:
        return None
    step = LINE_DOWNGRADE_BY_MARKET.get(leg.market_type)
    if step is None:
        return None
    if leg.direction == 'over':
        return max(0.0, round(leg.line - step, 1))
    if leg.direction == 'under':
        return round(leg.line + step, 1)
    return None


def _baseline_for_leg(leg: Leg) -> float | None:
    if leg.market_type in PLAYER_BASELINES:
        return PLAYER_BASELINES[leg.market_type]
    return TEAM_BASELINES.get(leg.market_type)


def _estimate_leg_probability(leg: Leg) -> float:
    baseline = _baseline_for_leg(leg)
    if baseline is None or leg.line is None:
        return 0.52
    diff = leg.line - baseline
    scale = {
        'player_points': 8.0,
        'player_rebounds': 5.0,
        'player_assists': 5.0,
        'player_threes': 3.0,
        'spread': 8.0,
        'game_total': 12.0,
    }.get(leg.market_type, 8.0)
    if leg.direction == 'under':
        diff = -diff
    probability = 0.55 - (diff / scale) * 0.12
    return max(0.05, min(0.95, round(probability, 4)))


def _probability_to_american_odds(probability: float) -> int:
    p = max(0.0001, min(0.9999, probability))
    if p >= 0.5:
        return int(round(-(p / (1.0 - p)) * 100.0))
    return int(round(((1.0 - p) / p) * 100.0))



def suggest_safer_leg(leg: Leg, advisory_context: dict[str, Any]) -> dict[str, Any]:
    risk_by_text = advisory_context.get('risk_by_text', {})
    leg_risk: AnalyzeLegRisk | None = risk_by_text.get(leg.raw_text)
    risk_score = float(leg_risk.risk_score) if leg_risk else 0.0

    unsupported = leg.market_type not in SUPPORTED_MARKETS
    special_market = any(token in leg.raw_text.lower() for token in ('first ', 'race to', 'first half', 'first quarter'))
    if unsupported or special_market:
        reason = 'Unsupported/special market kept unchanged for advisory safety rewrite.'
        return {
            'changed': False,
            'rewriteable': False,
            'suggested_leg': leg,
            'suggested_leg_text': leg.raw_text,
            'reason': reason,
            'note': f'Unchanged: {leg.raw_text}',
        }

    milestone_target = _find_milestone_target(leg)
    if milestone_target is not None and leg.direction == 'over':
        rewritten = leg.model_copy(update={'line': milestone_target, 'raw_text': _format_leg_text(leg, override_line=milestone_target)})
        return {
            'changed': True,
            'rewriteable': True,
            'suggested_leg': rewritten,
            'suggested_leg_text': rewritten.raw_text,
            'reason': 'Milestone ladder applied (10+→8+, 8+→6+, 6+→4+) to reduce volatility.',
            'note': f"{leg.raw_text} → {rewritten.raw_text}",
        }

    if leg.market_type in COMBO_MARKETS and risk_score >= 7.0:
        mapped_market = LOWER_RISK_SINGLE_MARKET.get(leg.market_type)
        if mapped_market:
            safer_line = _standard_safer_line(leg)
            rewritten = leg.model_copy(update={
                'market_type': mapped_market,
                'line': safer_line,
                'raw_text': _format_leg_text(leg, override_market=mapped_market, override_line=safer_line),
            })
            return {
                'changed': True,
                'rewriteable': True,
                'suggested_leg': rewritten,
                'suggested_leg_text': rewritten.raw_text,
                'reason': 'High-risk combo prop converted to a lower-variance single-stat market.',
                'note': f"{leg.raw_text} → {rewritten.raw_text}",
            }

    safer_line = _standard_safer_line(leg)
    if safer_line is not None and leg.line is not None and abs(safer_line - leg.line) > 0.001:
        rewritten = leg.model_copy(update={'line': safer_line, 'raw_text': _format_leg_text(leg, override_line=safer_line)})
        return {
            'changed': True,
            'rewriteable': True,
            'suggested_leg': rewritten,
            'suggested_leg_text': rewritten.raw_text,
            'reason': 'Line moved down one realistic sportsbook ladder tier by market.',
            'note': f"{leg.raw_text} → {rewritten.raw_text}",
        }

    return {
        'changed': False,
        'rewriteable': True,
        'suggested_leg': leg,
        'suggested_leg_text': leg.raw_text,
        'reason': 'No deterministic safer tier available; kept unchanged.',
        'note': f'Unchanged: {leg.raw_text}',
    }



def rewrite_slip_safer(parsed_legs: list[Leg], analysis_result: AnalyzeSlipResponse) -> dict[str, Any]:
    risk_by_text = {item.raw_leg_text: item for item in (analysis_result.leg_risk_scores or [])}
    context = {'risk_by_text': risk_by_text}

    rewritten_legs: list[Leg] = []
    rewritten_leg_rows: list[RewrittenLegSuggestion] = []
    notes: list[str] = [
        'Safer rewrite advisory only — not a guarantee.',
        'Lower-risk lines usually reduce expected payout.',
    ]

    changed_count = 0
    for leg in parsed_legs:
        suggestion = suggest_safer_leg(leg, context)
        rewritten_leg = suggestion['suggested_leg']
        rewritten_legs.append(rewritten_leg)
        if suggestion['changed']:
            changed_count += 1
        rewritten_leg_rows.append(
            RewrittenLegSuggestion(
                original_leg=leg.raw_text,
                suggested_leg=suggestion['suggested_leg_text'],
                reason_for_change=suggestion['reason'],
                changed=bool(suggestion['changed']),
                rewriteable=bool(suggestion['rewriteable']),
            )
        )
        notes.append(suggestion['note'])

    rewritten_analysis = analyze_slip_risk(rewritten_legs)
    rewritten_text = '\n'.join(item.raw_text for item in rewritten_legs)

    original_leg_probs = [_estimate_leg_probability(leg) for leg in parsed_legs] or [0.5]
    rewritten_leg_probs = [_estimate_leg_probability(leg) for leg in rewritten_legs] or [0.5]
    original_parlay_prob = prod(original_leg_probs)
    rewritten_parlay_prob = prod(rewritten_leg_probs)

    odds_original = _probability_to_american_odds(original_parlay_prob)
    odds_rewritten = _probability_to_american_odds(rewritten_parlay_prob)
    base_prob = max(original_parlay_prob, 1e-6)
    risk_reduction = max(0.0, round(((rewritten_parlay_prob - original_parlay_prob) / base_prob) * 100.0, 2))

    summary = (
        f"Original risk {analysis_result.slip_risk_score:.2f} ({analysis_result.slip_risk_label}) → "
        f"Rewritten risk {rewritten_analysis.slip_risk_score:.2f} ({rewritten_analysis.slip_risk_label}); "
        f"changed {changed_count}/{len(parsed_legs)} leg(s)."
    )

    return {
        'rewritten_slip_text': rewritten_text,
        'rewritten_legs': rewritten_leg_rows,
        'rewritten_risk_score': rewritten_analysis.slip_risk_score,
        'rewritten_risk_label': rewritten_analysis.slip_risk_label,
        'changed_legs_count': changed_count,
        'rewrite_notes': notes,
        'original_vs_rewritten_summary': summary,
        'original_estimated_odds': odds_original,
        'rewritten_estimated_odds': odds_rewritten,
        'risk_reduction_percent': risk_reduction,
    }

from __future__ import annotations

from ..models import GradedLeg, Leg, SettlementExplanation


def _selection_label(direction: str | None, line: float | None) -> str | None:
    if direction is None or line is None:
        return None
    return f'{direction} {line}'


def _default_grading_confidence(leg: Leg, warnings: list[str]) -> float:
    parse_conf = float(leg.parse_confidence if leg.parse_confidence is not None else leg.confidence)
    resolution_conf = float(leg.resolution_confidence if leg.resolution_confidence is not None else 1.0)
    penalty = 0.15 * len(warnings)
    return max(0.0, min(1.0, round((parse_conf + resolution_conf) / 2 - penalty, 2)))


def build_settlement_explanation(
    leg: Leg,
    *,
    settlement: str,
    reason_code: str,
    reason_message: str,
    actual_stat_value: float | None = None,
    warnings: list[str] | None = None,
    grading_confidence: float | None = None,
) -> SettlementExplanation:
    resolved_warnings = list(warnings or [])
    return SettlementExplanation(
        raw_leg_text=leg.raw_text,
        raw_player_text=leg.parsed_player_name or leg.player,
        matched_canonical_player=leg.resolved_player_name or leg.player,
        matched_team=leg.resolved_team or leg.team,
        identity_match_method=leg.identity_match_method,
        identity_confidence=leg.resolution_confidence,
        matched_event=leg.event_label,
        matched_market=leg.normalized_stat_type or leg.market_type,
        normalized_selection=_selection_label(leg.direction, leg.line),
        line=leg.line,
        actual_stat_value=actual_stat_value,
        result=settlement,  # type: ignore[arg-type]
        settlement_reason_code=reason_code,
        settlement_reason=reason_message,
        warnings=resolved_warnings,
        grading_confidence=grading_confidence if grading_confidence is not None else _default_grading_confidence(leg, resolved_warnings),
    )


def with_explanation(graded_leg: GradedLeg, explanation: SettlementExplanation) -> GradedLeg:
    payload = graded_leg.model_dump()
    payload['settlement_explanation'] = explanation
    return GradedLeg(**payload)

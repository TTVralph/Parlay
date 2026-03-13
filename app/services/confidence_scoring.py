from __future__ import annotations

from dataclasses import dataclass

from ..models import Leg


@dataclass(frozen=True)
class LegConfidenceBreakdown:
    confidence_score: float
    player_match_score: float
    event_match_score: float
    stat_parse_score: float
    ocr_quality_score: float

    def as_dict(self) -> dict[str, float]:
        return {
            'player_match_score': self.player_match_score,
            'event_match_score': self.event_match_score,
            'stat_parse_score': self.stat_parse_score,
            'ocr_quality_score': self.ocr_quality_score,
            'confidence_score': self.confidence_score,
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _player_match_score(leg: Leg) -> float:
    if leg.selection_source == 'user_selected' and leg.selection_applied:
        return 1.0
    tier = leg.identity_match_confidence
    if tier == 'HIGH':
        return 1.0
    if tier == 'MEDIUM':
        return 0.75
    if tier == 'LOW':
        return 0.25
    if leg.resolution_confidence is not None:
        return _clamp(float(leg.resolution_confidence))
    return 0.5


def _event_match_score(leg: Leg) -> float:
    if leg.event_selection_source == 'user_selected' and leg.event_selection_applied:
        return 1.0
    tier = leg.event_resolution_confidence
    if tier == 'high':
        base = 1.0
    elif tier == 'medium':
        base = 0.75
    elif tier == 'low':
        base = 0.4
    elif leg.event_id:
        base = 0.7
    else:
        base = 0.2

    if len(leg.event_candidates or []) > 1:
        base -= 0.15
    if leg.event_review_reason_code:
        base -= 0.25
    return _clamp(base)


def _stat_parse_score(leg: Leg) -> float:
    if leg.parse_confidence is not None:
        return _clamp(float(leg.parse_confidence))
    return _clamp(float(leg.confidence or 0.0))


def _ocr_quality_score(leg: Leg, *, input_source_path: str) -> float:
    if input_source_path == 'manual_text':
        return 1.0
    parse_signal = leg.parse_confidence if leg.parse_confidence is not None else leg.confidence
    if parse_signal is not None:
        return _clamp(float(parse_signal))
    return 0.7


def score_leg_confidence(leg: Leg, *, input_source_path: str) -> LegConfidenceBreakdown:
    player_match = _player_match_score(leg)
    event_match = _event_match_score(leg)
    stat_parse = _stat_parse_score(leg)
    ocr_quality = _ocr_quality_score(leg, input_source_path=input_source_path)

    confidence = (
        0.40 * player_match
        + 0.30 * event_match
        + 0.20 * stat_parse
        + 0.10 * ocr_quality
    )

    if leg.player_team_mismatch_detected:
        confidence *= 0.35
    return LegConfidenceBreakdown(
        confidence_score=round(_clamp(confidence), 4),
        player_match_score=round(player_match, 4),
        event_match_score=round(event_match, 4),
        stat_parse_score=round(stat_parse, 4),
        ocr_quality_score=round(ocr_quality, 4),
    )


def score_slip_confidence(leg_scores: list[float]) -> float | None:
    if not leg_scores:
        return None
    return round(sum(leg_scores) / len(leg_scores), 4)


def confidence_recommendation(slip_confidence: float | None) -> tuple[str | None, str | None]:
    if slip_confidence is None:
        return None, None
    if slip_confidence >= 0.85:
        return 'high', 'auto_grade'
    if slip_confidence >= 0.60:
        return 'medium', 'verify_recommended'
    return 'low', 'needs_review'

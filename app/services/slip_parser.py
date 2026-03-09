from __future__ import annotations

from .ocr_fallback import OCRFallbackParser
from .slip_confidence import apply_confidence_and_warnings, should_fallback_to_ocr
from .slip_normalizer import normalize_market, normalize_selection
from .slip_types import ParsedSlip
from .vision_parser import OpenAIVisionSlipParser, VisionSlipParser, classify_failure


class SlipParserService:
    def __init__(self, vision_parser: VisionSlipParser | None = None, ocr_fallback: OCRFallbackParser | None = None) -> None:
        self._vision = vision_parser or OpenAIVisionSlipParser()
        self._ocr_fallback = ocr_fallback or OCRFallbackParser()

    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        fallback_reason: str | None = None
        primary_result: ParsedSlip | None = None
        primary_failure_category: str | None = None
        primary_provider_error: str | None = None
        try:
            parsed = self._vision.parse(image_bytes=image_bytes, filename=filename)
            model_confidence = parsed.confidence
            for leg in parsed.parsed_legs:
                leg.market = normalize_market(leg.market)
                leg.selection = normalize_selection(leg.selection)
            apply_confidence_and_warnings(parsed)
            parsed.primary_parser_status = 'success'
            parsed.primary_confidence = model_confidence
            parsed.primary_warnings = list(parsed.warnings)
            parsed.primary_detected_sportsbook = parsed.primary_detected_sportsbook or parsed.sportsbook
            parsed.primary_screenshot_state = parsed.screenshot_state
            parsed.primary_parsed_leg_count = len(parsed.parsed_legs)

            if model_confidence != 'low' and not should_fallback_to_ocr(parsed):
                parsed.fallback_parser_status = 'not_attempted'
                return parsed

            primary_result = parsed
            if len(parsed.parsed_legs) == 0:
                fallback_reason = 'vision_empty_parse'
            elif model_confidence == 'low' or parsed.confidence in {'low', 'NEEDS_REVIEW'}:
                fallback_reason = 'vision_low_confidence'
            else:
                fallback_reason = 'vision_low_confidence'
            parsed.primary_parser_status = 'success_fallback_triggered'
        except Exception as exc:
            fallback_reason = classify_failure(exc)
            primary_failure_category = fallback_reason
            primary_provider_error = str(exc)

        fallback = self._ocr_fallback.parse(image_bytes=image_bytes, filename=filename)
        fallback.primary_parser_status = 'failed' if primary_result is None else 'success_fallback_triggered'
        fallback.primary_failure_category = primary_failure_category or fallback_reason
        fallback.primary_provider_error = primary_provider_error
        fallback.primary_result = primary_result
        fallback.primary_confidence = primary_result.confidence if primary_result else None
        fallback.primary_warnings = list(primary_result.warnings) if primary_result else []
        fallback.primary_detected_sportsbook = primary_result.primary_detected_sportsbook if primary_result else None
        fallback.primary_parser_strategy_used = primary_result.primary_parser_strategy_used if primary_result else None
        fallback.primary_screenshot_state = primary_result.screenshot_state if primary_result else None
        fallback.primary_parsed_leg_count = len(primary_result.parsed_legs) if primary_result else 0
        fallback.fallback_parser_status = 'success'
        fallback.fallback_reason = fallback_reason
        if primary_result and primary_result.preprocessing_metadata:
            fallback.preprocessing_metadata = primary_result.preprocessing_metadata
        if primary_result and primary_result.debug_artifacts:
            fallback.debug_artifacts = dict(primary_result.debug_artifacts)
        if fallback_reason:
            fallback.warnings.insert(0, f'fallback_reason={fallback_reason}')
        return fallback

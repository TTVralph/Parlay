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
        try:
            parsed = self._vision.parse(image_bytes=image_bytes, filename=filename)
            for leg in parsed.parsed_legs:
                leg.market = normalize_market(leg.market)
                leg.selection = normalize_selection(leg.selection)
            apply_confidence_and_warnings(parsed)
            if not should_fallback_to_ocr(parsed):
                parsed.primary_parser_status = 'success'
                parsed.fallback_parser_status = 'not_attempted'
                return parsed
            fallback_reason = 'low_confidence'
            parsed.primary_parser_status = 'success_low_confidence'
        except Exception as exc:
            fallback_reason = classify_failure(exc)

        fallback = self._ocr_fallback.parse(image_bytes=image_bytes, filename=filename)
        fallback.primary_parser_status = 'failed'
        fallback.fallback_parser_status = 'success'
        fallback.fallback_reason = fallback_reason
        if fallback_reason:
            fallback.warnings.insert(0, f'fallback_reason={fallback_reason}')
        return fallback

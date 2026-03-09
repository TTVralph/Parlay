from __future__ import annotations

from .ocr_fallback import OCRFallbackParser
from .slip_confidence import apply_confidence_and_warnings, should_fallback_to_ocr
from .slip_normalizer import normalize_market, normalize_selection
from .slip_types import ParsedSlip
from .vision_parser import OpenAIVisionSlipParser, VisionSlipParser


class SlipParserService:
    def __init__(self, vision_parser: VisionSlipParser | None = None, ocr_fallback: OCRFallbackParser | None = None) -> None:
        self._vision = vision_parser or OpenAIVisionSlipParser()
        self._ocr_fallback = ocr_fallback or OCRFallbackParser()

    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        vision_error: str | None = None
        try:
            parsed = self._vision.parse(image_bytes=image_bytes, filename=filename)
            for leg in parsed.parsed_legs:
                leg.market = normalize_market(leg.market)
                leg.selection = normalize_selection(leg.selection)
            apply_confidence_and_warnings(parsed)
            if not should_fallback_to_ocr(parsed):
                return parsed
            vision_error = 'Vision parse quality was too low, using OCR fallback.'
        except Exception as exc:
            vision_error = f'Vision parser failed ({exc}); using OCR fallback.'

        fallback = self._ocr_fallback.parse(image_bytes=image_bytes, filename=filename)
        if vision_error:
            fallback.warnings.insert(0, vision_error)
        return fallback

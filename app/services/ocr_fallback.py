from __future__ import annotations

from ..ocr import get_ocr_provider
from ..screenshot_parser import parse_screenshot_text
from .slip_types import ParsedSlip, ParsedSlipLeg


class OCRFallbackParser:
    def parse(self, image_bytes: bytes, filename: str | None = None) -> ParsedSlip:
        ocr = get_ocr_provider()
        ocr_result = ocr.extract_text(filename or 'upload', image_bytes)
        parsed = parse_screenshot_text(ocr_result.raw_text, ocr_result.cleaned_text)
        legs = [ParsedSlipLeg(
            sport='NBA' if leg.stat_type else None,
            player_name=leg.player_name,
            market=leg.stat_type,
            line=leg.line,
            selection=leg.direction,
            raw_text=leg.raw_leg_text,
        ) for leg in parsed.parsed_legs]
        confidence = 'high' if ocr_result.confidence >= 0.85 else 'medium' if ocr_result.confidence >= 0.6 else 'low'
        return ParsedSlip(raw_text=ocr_result.raw_text, parsed_legs=legs, confidence=confidence, warnings=[*ocr_result.notes, *parsed.parse_warnings], detected_bet_date=parsed.detected_bet_date)

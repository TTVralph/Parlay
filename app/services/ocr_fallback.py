from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ..ocr import get_ocr_provider
from ..screenshot_parser import parse_screenshot_text
from .slip_types import ParsedSlip, ParsedSlipLeg


class OCRFallbackParser:
    def __init__(self) -> None:
        self._debug_mode = os.getenv('SCREENSHOT_DEBUG_MODE', '').lower() in {'1', 'true', 'yes', 'on'}
        self._debug_dir = Path(os.getenv('SCREENSHOT_DEBUG_DIR', 'tmp/screenshot_debug'))

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
        debug_artifacts = self._save_ocr_artifact(ocr_result.raw_text, filename) if self._debug_mode else None
        return ParsedSlip(
            raw_text=ocr_result.raw_text,
            parsed_legs=legs,
            confidence=confidence,
            warnings=[*ocr_result.notes, *parsed.parse_warnings],
            detected_bet_date=parsed.detected_bet_date,
            debug_artifacts=debug_artifacts,
        )

    def _save_ocr_artifact(self, ocr_text: str, filename: str | None) -> dict[str, str]:
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        base = (Path(filename or 'upload').stem or 'upload') + '_' + uuid4().hex[:8]
        ocr_path = self._debug_dir / f'{base}_fallback_ocr.txt'
        ocr_path.write_text(ocr_text)
        return {'debug_fallback_ocr_text_path': str(ocr_path)}

from __future__ import annotations

import base64
import os

import httpx

from .base import OCRProvider, OCRResult
from ..ingestion import strip_social_noise


class MockOCRProvider:
    provider_name = 'mock'

    def extract_text(self, filename: str, content: bytes) -> OCRResult:
        text = content.decode('utf-8', errors='ignore')
        cleaned = strip_social_noise(text)
        return OCRResult(
            raw_text=text,
            cleaned_text=cleaned,
            provider=self.provider_name,
            confidence=0.99 if cleaned else 0.0,
            notes=['Mock OCR decoded uploaded bytes as UTF-8 text for local testing'],
        )


class TesseractOCRProvider:
    provider_name = 'tesseract'

    def __init__(self) -> None:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                'Tesseract OCR dependencies are not installed. Add pillow + pytesseract and install the system tesseract binary.'
            ) from exc
        self._pytesseract = pytesseract
        self._image_mod = Image

    def extract_text(self, filename: str, content: bytes) -> OCRResult:
        from io import BytesIO

        image = self._image_mod.open(BytesIO(content))
        raw_text = self._pytesseract.image_to_string(image)
        cleaned = strip_social_noise(raw_text)
        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned,
            provider=self.provider_name,
            confidence=0.75 if cleaned else 0.0,
            notes=['Parsed with pytesseract; confidence is heuristic'],
        )


class OCRSpaceProvider:
    provider_name = 'ocr_space'

    def __init__(self) -> None:
        self._api_key = os.getenv('OCR_SPACE_API_KEY')
        if not self._api_key:
            raise RuntimeError('OCR_SPACE_API_KEY is required for OCR_PROVIDER=ocr_space')
        self._url = os.getenv('OCR_SPACE_URL', 'https://api.ocr.space/parse/image')

    def extract_text(self, filename: str, content: bytes) -> OCRResult:
        payload = {
            'apikey': self._api_key,
            'base64Image': 'data:application/octet-stream;base64,' + base64.b64encode(content).decode('ascii'),
            'language': 'eng',
            'isOverlayRequired': False,
            'OCREngine': 2,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self._url, data=payload)
            response.raise_for_status()
            data = response.json()
        parsed = data.get('ParsedResults') or []
        raw_text = '\n'.join((item.get('ParsedText') or '').strip() for item in parsed).strip()
        cleaned = strip_social_noise(raw_text)
        confidence = 0.0
        notes = []
        for item in parsed:
            text_overlay = item.get('TextOverlay') or {}
            lines = text_overlay.get('Lines') or []
            words = [word for line in lines for word in line.get('Words', [])]
            confs = [float(word.get('Confidence', 0.0)) for word in words if word.get('Confidence') is not None]
            if confs:
                confidence = max(confidence, sum(confs) / len(confs) / 100.0)
        if data.get('IsErroredOnProcessing'):
            notes.append('OCR.space reported a processing error')
        notes.append('Parsed with OCR.space HTTP API')
        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned,
            provider=self.provider_name,
            confidence=confidence if cleaned else 0.0,
            notes=notes,
        )


def get_ocr_provider() -> OCRProvider:
    provider_name = os.getenv('OCR_PROVIDER', 'mock').lower()
    if provider_name == 'tesseract':
        return TesseractOCRProvider()
    if provider_name in {'ocr_space', 'ocrspace'}:
        return OCRSpaceProvider()
    return MockOCRProvider()

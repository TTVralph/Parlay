from __future__ import annotations

import base64
import os
import re
from io import BytesIO

import httpx

try:
    from PIL import Image, UnidentifiedImageError
except ModuleNotFoundError:  # pragma: no cover
    Image = None
    UnidentifiedImageError = OSError

from .base import OCRProvider, OCRResult
from ..ingestion import strip_social_noise


_OCR_JUNK_LINE_RE = re.compile(
    r'^(?:'
    r'bet\s*slip|open\s*bets?|my\s*bets?|cash\s*out|place\s*bet|same\s*game\s*parlay\+?|'
    r'sgpx?|popular|featured|live|promos?|search|edit|done|share|home|settings|login|signup|'
    r'continue|add\s+more\s+legs?|all\s+bets?'
    r')\b',
    re.I,
)
_LEG_SIGNAL_RE = re.compile(
    r'(?:\b(?:ml|moneyline|over|under|o\s*\d+(?:\.\d+)?|u\s*\d+(?:\.\d+)?)\b|'
    r'\b\d+(?:\.\d+)?\+\s*(?:pts?|points|reb(?:ounds)?|ast|assists|threes?|3pm|3s)\b|'
    r'\b[+\-]\d+(?:\.\d+)?\b)',
    re.I,
)


def _normalize_sportsbook_ocr_text(text: str) -> tuple[str, bool]:
    normalized = text.replace('\r', '\n')
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip(' \t|•-')
        if not line:
            continue
        if _OCR_JUNK_LINE_RE.match(line):
            continue
        lines.append(line)

    cleaned = strip_social_noise('\n'.join(lines))
    usable = any(_LEG_SIGNAL_RE.search(line) for line in cleaned.splitlines())
    return (cleaned if usable else '', not usable)


class MockOCRProvider:
    provider_name = 'mock'

    def extract_text(self, filename: str, content: bytes) -> OCRResult:
        raise RuntimeError(
            'Screenshot OCR is unavailable in this environment. Configure OCR_PROVIDER=tesseract with dependencies, or OCR_PROVIDER=ocr_space with OCR_SPACE_API_KEY.'
        )


def validate_image_upload(filename: str, content: bytes) -> None:
    if not content:
        raise RuntimeError('Uploaded file is empty.')

    kind = None
    if Image is not None:
        try:
            with Image.open(BytesIO(content)) as image:
                detected = image.format
                kind = detected.lower() if detected else None
        except (UnidentifiedImageError, OSError):
            pass

    if kind is None:
        extension = os.path.splitext((filename or '').lower())[1]
        extension_map = {
            '.jpg': 'jpeg',
            '.jpeg': 'jpeg',
            '.png': 'png',
            '.gif': 'gif',
            '.bmp': 'bmp',
            '.webp': 'webp',
            '.tif': 'tiff',
            '.tiff': 'tiff',
        }
        kind = extension_map.get(extension)

    if kind is None:
        signatures: tuple[tuple[bytes, str], ...] = (
            (b'\x89PNG\r\n\x1a\n', 'png'),
            (b'\xff\xd8\xff', 'jpeg'),
            (b'GIF87a', 'gif'),
            (b'GIF89a', 'gif'),
            (b'BM', 'bmp'),
            (b'RIFF', 'webp'),
            (b'II*\x00', 'tiff'),
            (b'MM\x00*', 'tiff'),
        )
        for prefix, detected_kind in signatures:
            if content.startswith(prefix):
                kind = detected_kind
                break

        if kind == 'webp' and content[8:12] != b'WEBP':
            kind = None

    if kind not in {'png', 'jpeg', 'gif', 'bmp', 'webp', 'tiff'}:
        raise RuntimeError(f'Unsupported screenshot format for {filename or "upload"}. Please upload a valid image file.')


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
        image = self._image_mod.open(BytesIO(content))
        raw_text = self._pytesseract.image_to_string(image)
        cleaned, unusable = _normalize_sportsbook_ocr_text(raw_text)
        notes = ['Parsed with pytesseract; confidence is heuristic']
        if unusable:
            notes.append('OCR text did not contain parseable sportsbook legs. Try a clearer screenshot.')
        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned,
            provider=self.provider_name,
            confidence=0.75 if cleaned else 0.0,
            notes=notes,
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
        line_texts: list[str] = []
        for item in parsed:
            text_overlay = item.get('TextOverlay') or {}
            for line in text_overlay.get('Lines') or []:
                line_text = (line.get('LineText') or '').strip()
                if not line_text:
                    words = [str(word.get('WordText') or '').strip() for word in line.get('Words', [])]
                    line_text = ' '.join(word for word in words if word)
                if line_text:
                    line_texts.append(line_text)
        raw_text = '\n'.join(line_texts).strip() or '\n'.join((item.get('ParsedText') or '').strip() for item in parsed).strip()
        cleaned, unusable = _normalize_sportsbook_ocr_text(raw_text)
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
        if unusable:
            notes.append('OCR text did not contain parseable sportsbook legs. Try a clearer screenshot.')
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

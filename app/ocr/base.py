from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OCRResult:
    raw_text: str
    cleaned_text: str
    provider: str
    confidence: float
    notes: list[str]


class OCRProvider(Protocol):
    provider_name: str

    def extract_text(self, filename: str, content: bytes) -> OCRResult: ...

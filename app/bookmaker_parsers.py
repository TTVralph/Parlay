from __future__ import annotations

import re
from dataclasses import dataclass

from .ingestion import strip_social_noise


@dataclass
class ParsedSlipText:
    bookmaker: str
    raw_text: str
    cleaned_text: str
    notes: list[str]


DRAFTKINGS_MARKERS = ('draftkings', 'dk ', 'placed bet', 'bet id', 'sgpx')
FANDUEL_MARKERS = ('fanduel', 'fd ', 'same game parlay+', 'bet placed', 'cash out')
BET365_MARKERS = ('bet365', 'my bets', 'return', 'selections')


def detect_bookmaker(text: str) -> str:
    lower = text.lower()
    if any(marker in lower for marker in DRAFTKINGS_MARKERS):
        return 'draftkings'
    if any(marker in lower for marker in FANDUEL_MARKERS):
        return 'fanduel'
    if any(marker in lower for marker in BET365_MARKERS):
        return 'bet365'
    return 'generic'


def _drop_metadata_lines(lines: list[str], patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in patterns):
            continue
        kept.append(stripped)
    return kept


def parse_slip_text(text: str, bookmaker_hint: str | None = None) -> ParsedSlipText:
    bookmaker = (bookmaker_hint or detect_bookmaker(text)).lower()
    normalized = text.replace('\r', '\n')
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    notes: list[str] = []

    patterns: dict[str, tuple[re.Pattern[str], ...]] = {
        'draftkings': (
            re.compile(r'^draftkings$', re.I),
            re.compile(r'^bet id', re.I),
            re.compile(r'^wager', re.I),
            re.compile(r'^to win', re.I),
            re.compile(r'^placed bet', re.I),
            re.compile(r'^sgpx?$', re.I),
            re.compile(r'^odds', re.I),
        ),
        'fanduel': (
            re.compile(r'^fanduel$', re.I),
            re.compile(r'^same game parlay\+?$', re.I),
            re.compile(r'^bet placed', re.I),
            re.compile(r'^cash out', re.I),
            re.compile(r'^stake', re.I),
            re.compile(r'^payout', re.I),
            re.compile(r'^live$', re.I),
        ),
        'bet365': (
            re.compile(r'^bet365$', re.I),
            re.compile(r'^my bets$', re.I),
            re.compile(r'^return', re.I),
            re.compile(r'^stake', re.I),
            re.compile(r'^potential returns?', re.I),
            re.compile(r'^selections?$', re.I),
        ),
    }

    if bookmaker in patterns:
        before = list(lines)
        lines = _drop_metadata_lines(lines, patterns[bookmaker])
        if len(lines) != len(before):
            notes.append(f'Applied {bookmaker} slip cleaner')
    else:
        notes.append('Using generic slip cleaner')

    # Split common one-line OCR runs like "Denver Nuggets Moneyline Nikola Jokic 25+ Points"
    recomposed = '\n'.join(lines)
    recomposed = re.sub(r'\s{2,}', '\n', recomposed)
    recomposed = re.sub(r'(?i)\b(moneyline)\b', 'ML', recomposed)
    recomposed = re.sub(r'(?i)\bpoints\b', 'pts', recomposed)
    recomposed = re.sub(r'(?i)\bthree pointers made\b', 'threes', recomposed)

    cleaned = strip_social_noise(recomposed)
    return ParsedSlipText(
        bookmaker=bookmaker,
        raw_text=text,
        cleaned_text=cleaned,
        notes=notes,
    )

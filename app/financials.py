from __future__ import annotations

import re
from dataclasses import dataclass


BOOKMAKER_KEYWORDS = {
    'draftkings': ['draftkings', 'dk'],
    'fanduel': ['fanduel', 'fd'],
    'bet365': ['bet365'],
    'caesars': ['caesars'],
}

AMERICAN_RE = re.compile(r'(?<!\d)([+-]\d{3,4})(?!\d)')
DECIMAL_RE = re.compile(r'\b(\d{1,2}\.\d{2})\b')
STAKE_RE = re.compile(r'(?<![a-z])(?:stake|risk|bet)\b\s*[:\-]?\s*\$?(\d+(?:\.\d+)?)\b', re.I)
TO_WIN_RE = re.compile(r'\b(?:to\s*win|payout|profit)\s*[:\-]?\s*\$?(\d+(?:\.\d+)?)\b', re.I)


@dataclass
class ExtractedFinancials:
    bookmaker: str | None = None
    stake_amount: float | None = None
    to_win_amount: float | None = None
    american_odds: int | None = None
    decimal_odds: float | None = None
    notes: list[str] | None = None


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1.0) * 100))
    return int(round(-100 / (decimal_odds - 1.0)))


def detect_bookmaker(text: str, bookmaker_hint: str | None = None) -> str | None:
    if bookmaker_hint:
        return bookmaker_hint.lower().strip()
    lower = text.lower()
    for canonical, keys in BOOKMAKER_KEYWORDS.items():
        if any(key in lower for key in keys):
            return canonical
    return None


def extract_financials(text: str, bookmaker_hint: str | None = None) -> ExtractedFinancials:
    notes: list[str] = []
    bookmaker = detect_bookmaker(text, bookmaker_hint=bookmaker_hint)

    stake_amount = None
    stake_match = STAKE_RE.search(text)
    if stake_match:
        stake_amount = float(stake_match.group(1))

    to_win_amount = None
    to_win_match = TO_WIN_RE.search(text)
    if to_win_match:
        to_win_amount = float(to_win_match.group(1))

    american_odds = None
    american_match = AMERICAN_RE.search(text)
    if american_match:
        american_odds = int(american_match.group(1))
        notes.append('Extracted exact American odds from text')

    decimal_odds = None
    if american_odds is None:
        for match in DECIMAL_RE.finditer(text):
            value = float(match.group(1))
            if 1.01 <= value <= 100.0:
                decimal_odds = value
                american_odds = decimal_to_american(value)
                notes.append('Converted decimal odds to American odds')
                break

    return ExtractedFinancials(
        bookmaker=bookmaker,
        stake_amount=stake_amount,
        to_win_amount=to_win_amount,
        american_odds=american_odds,
        decimal_odds=decimal_odds,
        notes=notes,
    )

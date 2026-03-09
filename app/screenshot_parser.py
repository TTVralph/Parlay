from __future__ import annotations

import re
from datetime import datetime

from .models import Leg, ParsedScreenshotLeg, ParsedScreenshotResponse
from .parser import parse_text

_DATE_PATTERNS = (
    re.compile(r'\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>20\d{2})\b'),
    re.compile(r'\b(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b'),
    re.compile(r'\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(?P<d>\d{1,2}),\s*(?P<y>20\d{2})\b', re.I),
)
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_STAT_LABELS = {
    'player_points': 'points',
    'player_assists': 'assists',
    'player_rebounds': 'rebounds',
    'player_threes': 'threes',
    'player_pa': 'points + assists',
    'player_pr': 'points + rebounds',
    'player_ra': 'rebounds + assists',
    'player_pra': 'points + rebounds + assists',
}


def _normalize_ocr_text_for_parsing(text: str) -> str:
    compact = re.sub(r'[ \t]+', ' ', text.replace('\r', '\n'))
    # break apart common line-run noise around over/under patterns
    compact = re.sub(r'(?i)\s+(?=[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:o|u|over|under)\s*\d)', '\n', compact)
    compact = re.sub(r'\n{2,}', '\n', compact)
    return compact.strip()


def _detect_bet_date(text: str) -> str | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        try:
            if 'mon' in groups and groups.get('mon'):
                month = _MONTHS[groups['mon'][:3].lower()]
                parsed = datetime(int(groups['y']), month, int(groups['d']))
            else:
                parsed = datetime(int(groups['y']), int(groups['m']), int(groups['d']))
            return parsed.date().isoformat()
        except Exception:
            continue
    return None


def _leg_to_parsed(leg: Leg) -> ParsedScreenshotLeg:
    player_name = leg.player
    stat_type = _STAT_LABELS.get(leg.market_type)
    direction = leg.direction
    line = leg.line
    normalized_label = leg.raw_text
    if player_name and stat_type and direction and line is not None:
        normalized_label = f"{player_name} {direction.title()} {line:g} {stat_type.title()}"
    return ParsedScreenshotLeg(
        raw_leg_text=leg.raw_text,
        player_name=player_name,
        stat_type=stat_type,
        line=line,
        direction=direction,
        normalized_label=normalized_label,
        confidence=leg.confidence,
    )


def parse_screenshot_text(raw_text: str, cleaned_text: str) -> ParsedScreenshotResponse:
    parse_warnings: list[str] = []
    parse_input = _normalize_ocr_text_for_parsing(cleaned_text or raw_text)
    legs = parse_text(parse_input)

    parsed_legs: list[ParsedScreenshotLeg] = []
    seen: set[str] = set()
    for leg in legs:
        parsed = _leg_to_parsed(leg)
        key = parsed.normalized_label.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        missing_core = (
            leg.market_type.startswith('player_')
            and leg.market_type not in {'player_hits'}
            and (not leg.player or leg.line is None or not leg.direction)
        )
        likely_fragment_total = leg.market_type == 'game_total' and len(leg.raw_text.split()) <= 3
        if missing_core or likely_fragment_total or leg.confidence <= 0.0:
            parse_warnings.append(f"Low-confidence leg skipped: {leg.raw_text}")
            continue
        if leg.confidence < 0.75:
            parse_warnings.append(f"Review suggested for leg: {leg.raw_text}")
        parsed_legs.append(parsed)

    if not parsed_legs:
        parse_warnings.append('No complete prop legs were confidently extracted from the screenshot.')

    return ParsedScreenshotResponse(
        raw_text=raw_text,
        parsed_legs=parsed_legs,
        detected_bet_date=_detect_bet_date(raw_text),
        parse_warnings=parse_warnings,
    )

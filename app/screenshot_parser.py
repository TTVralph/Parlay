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
    'player_triple_double': 'triple double',
    'player_double_double': 'double double',
}

_NOISE_KEYWORDS = ('cash out', 'share', 'track', 'wager', 'to pay', 'boost', 'parlay')
_MARKET_ALIASES = {
    'pts': 'points',
    'pt': 'points',
    'points': 'points',
    'reb': 'rebounds',
    'rebs': 'rebounds',
    'rebounds': 'rebounds',
    'ast': 'assists',
    'asts': 'assists',
    'assists': 'assists',
    '3pm': 'threes',
    '3s': 'threes',
    'threes': 'threes',
    'pts + ast': 'points + assists',
    'points + assists': 'points + assists',
    'pts + reb': 'points + rebounds',
    'points + rebounds': 'points + rebounds',
    'pra': 'points + rebounds + assists',
    'points + rebounds + assists': 'points + rebounds + assists',
}
_PLAYER_ONLY_LINE = re.compile(r"^[A-Z][A-Za-z\-'’]+(?:\s+[A-Z][A-Za-z\-'’]+){1,3}$")
_OU_MARKET_LINE = re.compile(
    r'^(?P<dir>O|U|Over|Under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?P<market>[A-Za-z0-9+ ]+)$',
    re.I,
)
_YES_NO_LINE = re.compile(r'^(?P<market>Triple\s*Double|Double\s*Double)\s*(?P<sel>Yes|No)$', re.I)
_INLINE_YES_NO_LINE = re.compile(
    r"^(?P<name>[A-Za-z\-'’\. ]+?)\s+(?P<market>Triple\s*Double|Double\s*Double)\s*(?P<sel>Yes|No)$",
    re.I,
)
_INLINE_OU_SHORTHAND = re.compile(
    r"^(?P<name>[A-Za-z\-'’\. ]+?)\s+(?P<dir>O|U|Over|Under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?P<market>[A-Za-z0-9+ ]+)$",
    re.I,
)


def _normalize_ocr_text_for_parsing(text: str) -> str:
    compact = re.sub(r'[ \t]+', ' ', text.replace('\r', '\n'))
    # break apart common line-run noise around over/under patterns
    compact = re.sub(r'(?i)\s+(?=[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:o|u|over|under)\s*\d)', '\n', compact)
    compact = re.sub(r'\n{2,}', '\n', compact)
    return compact.strip()


def _normalize_market_label(raw_market: str) -> str:
    lowered = re.sub(r'\s+', ' ', raw_market.lower()).strip()
    lowered = lowered.replace('pts+ast', 'pts + ast').replace('pts+reb', 'pts + reb')
    lowered = lowered.replace('p+r+a', 'pra').replace('p+r', 'pts + reb').replace('p+a', 'pts + ast')
    lowered = lowered.replace('three pointers made', 'threes').replace('3 ptm', '3pm')
    return _MARKET_ALIASES.get(lowered, lowered)


def _title_name(raw_name: str) -> str:
    return re.sub(r'\s+', ' ', raw_name).strip()


def normalize_sportsbook_ocr_text(text: str) -> str:
    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in text.replace('\r', '\n').split('\n')]
    cleaned_lines = [ln for ln in lines if ln and not any(noise in ln.lower() for noise in _NOISE_KEYWORDS)]

    normalized: list[str] = []
    current_player: str | None = None
    for line in cleaned_lines:
        inline_yes_no = _INLINE_YES_NO_LINE.match(line)
        if inline_yes_no:
            name = _title_name(inline_yes_no.group('name'))
            market = re.sub(r'\s+', ' ', inline_yes_no.group('market')).title()
            selection = inline_yes_no.group('sel').title()
            normalized.append(f'{name} {market} {selection}')
            current_player = name
            continue

        inline_ou = _INLINE_OU_SHORTHAND.match(line)
        if inline_ou:
            name = _title_name(inline_ou.group('name'))
            direction = 'Over' if inline_ou.group('dir').lower() in {'o', 'over'} else 'Under'
            market = _normalize_market_label(inline_ou.group('market')).title()
            normalized.append(f"{name} {direction} {inline_ou.group('line')} {market}")
            current_player = name
            continue

        yes_no = _YES_NO_LINE.match(line)
        if yes_no and current_player:
            market = re.sub(r'\s+', ' ', yes_no.group('market')).title()
            selection = yes_no.group('sel').title()
            normalized.append(f'{current_player} {market} {selection}')
            continue

        if _PLAYER_ONLY_LINE.match(line):
            current_player = _title_name(line)
            continue

        ou_market = _OU_MARKET_LINE.match(line)
        if ou_market and current_player:
            direction = 'Over' if ou_market.group('dir').lower() in {'o', 'over'} else 'Under'
            market = _normalize_market_label(ou_market.group('market')).title()
            normalized.append(f"{current_player} {direction} {ou_market.group('line')} {market}")
            continue

        normalized.append(line)

    return '\n'.join(normalized).strip()


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
    if player_name and stat_type and direction in {'yes', 'no'}:
        normalized_label = f"{player_name} {stat_type.title()} {direction.title()}"
    elif player_name and stat_type and direction and line is not None:
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
    sportsbook_normalized = normalize_sportsbook_ocr_text(cleaned_text or raw_text)
    parse_input = _normalize_ocr_text_for_parsing(sportsbook_normalized)
    legs = parse_text(parse_input)

    parsed_legs: list[ParsedScreenshotLeg] = []
    seen: set[str] = set()
    for leg in legs:
        parsed = _leg_to_parsed(leg)
        key = parsed.normalized_label.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        derived_market = leg.market_type in {'player_triple_double', 'player_double_double'}
        missing_core = (
            leg.market_type.startswith('player_')
            and leg.market_type not in {'player_hits'}
            and not derived_market
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
        confidence='medium' if parsed_legs else 'low',
    )

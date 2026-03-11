from __future__ import annotations

import re
from datetime import datetime

from .models import Leg, ParsedScreenshotLeg, ParsedScreenshotResponse
from .parser import parse_text
from .services.player_name_suggester import suggest_player_name

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

_NOISE_KEYWORDS = (
    'cash out',
    'share',
    'track',
    'wager',
    'to pay',
    'boost',
    'parlay',
    'open',
    'hide legs',
    'same game parlay',
    'edit bet',
)
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
    '3pt': 'threes',
    '3ptm': 'threes',
    '3 pointers': 'threes',
    'three pointers': 'threes',
    '3s': 'threes',
    'threes': 'threes',
    'pts + ast': 'points + assists',
    'points + assists': 'points + assists',
    'pts + reb': 'points + rebounds',
    'points + rebounds': 'points + rebounds',
    'reb + ast': 'rebounds + assists',
    'rebs + ast': 'rebounds + assists',
    'rebounds + assists': 'rebounds + assists',
    'pra': 'points + rebounds + assists',
    'points + rebounds + assists': 'points + rebounds + assists',
}
_PLAYER_ONLY_LINE = re.compile(r"^[A-Z][A-Za-z\-'’\.]+(?:\s+[A-Z][A-Za-z\-'’\.]+){1,3}$")
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
_ODDS_ONLY_LINE = re.compile(r'^[+-]\s*\d{3,}$')
_BUTTON_OR_UI_LINE = re.compile(r'^(open|close|show more|show less|edit|remove|add|continue|submit)$', re.I)
_MATCHUP_TIME_LINE = re.compile(
    r'^(?:[A-Z]{2,4}\s+){1,3}(?:today|tomorrow|\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}/\d{1,2}).*$',
    re.I,
)
_LEG_WITH_DIRECTION = re.compile(
    r"^(?P<name>[A-Za-z\-'’\. ]+?)\s+(?P<dir>Over|Under)\s+(?P<line>\d+(?:\.\d+)?)\s+(?P<market>[A-Za-z0-9+ ]+)$",
    re.I,
)
_MARKET_FOLLOWUP_LINE = re.compile(r'^(?P<market>Triple\s*-?\s*Double|Double\s*-?\s*Double)$', re.I)
_YES_NO_ONLY = re.compile(r'^(Yes|No)$', re.I)
_DIRECTION_LINE_ONLY = re.compile(r'^(?P<dir>O|U|Over|Under)\s*(?P<line>\d+(?:\.\d+)?)$', re.I)
_MARKET_ONLY_LINE = re.compile(r'^(?P<market>Pts|Points|Reb|Rebs|Rebounds|Ast|Asts|Assists|PRA|Pts\s*\+\s*Ast|Pts\s*\+\s*Reb|Reb\s*\+\s*Ast|3PM|3PT|Threes|Three\s+Pointers)$', re.I)
_ALT_MARKET_PHRASE = re.compile(
    r'^(?:TO\s+(?:SCORE|RECORD)\s+)?(?P<line>\d+(?:\.\d+)?)\s*\+\s*(?P<market>POINTS|REBOUNDS|ASSISTS|PRA)\b',
    re.I,
)
_INLINE_ALT_MARKET = re.compile(
    r"^(?!TO\b)(?P<name>[A-Za-z\-'’\. ]+?)\s+(?:TO\s+(?:SCORE|RECORD)\s+)?(?P<line>\d+(?:\.\d+)?)\s*\+\s*(?P<market>POINTS|REBOUNDS|ASSISTS|PRA)\b",
    re.I,
)


def _is_noise_line(line: str) -> bool:
    lowered = line.lower()
    if any(noise in lowered for noise in _NOISE_KEYWORDS):
        return True
    if _ODDS_ONLY_LINE.match(line):
        return True
    if _BUTTON_OR_UI_LINE.match(line):
        return True
    if 'bet slip' in lowered:
        return True
    if lowered in {'draftkings', 'fanduel', 'bet365', 'betmgm', 'bet slip'}:
        return True
    return bool(_MATCHUP_TIME_LINE.match(line))


def _normalize_line_text(line: str) -> str:
    normalized = re.sub(r'\s+', ' ', line).strip(' -–|')
    normalized = normalized.replace('—', '-').replace('–', '-')
    normalized = re.sub(r'(?i)\btriple\s*[- ]\s*double\b', 'Triple Double', normalized)
    normalized = re.sub(r'(?i)\bdouble\s*[- ]\s*double\b', 'Double Double', normalized)
    normalized = re.sub(r'(?i)\bmore\b', 'Over', normalized)
    normalized = re.sub(r'(?i)\bless\b', 'Under', normalized)
    normalized = re.sub(r'\s*\+\s*', ' + ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def _format_ou_leg(name: str, direction: str, line: str, market: str) -> str:
    clean_name = _title_name(name)
    clean_market = _normalize_market_label(market).title()
    clean_direction = 'Over' if direction.lower() in {'o', 'over'} else 'Under'
    return f'{clean_name} {clean_direction} {line} {clean_market}'


def _build_leg_candidates(cleaned_lines: list[str]) -> list[str]:
    normalized: list[str] = []
    current_player: str | None = None
    pending_yes_no_name: str | None = None
    pending_yes_no_market: str | None = None
    pending_yes_no_selection: str | None = None
    pending_direction: str | None = None
    pending_line: str | None = None

    for line in cleaned_lines:
        inline_yes_no = _INLINE_YES_NO_LINE.match(line)
        if inline_yes_no:
            name = _title_name(inline_yes_no.group('name'))
            market = re.sub(r'\s+', ' ', inline_yes_no.group('market')).replace('-', ' ').title()
            selection = inline_yes_no.group('sel').title()
            normalized.append(f'{name} {market} {selection}')
            current_player = name
            continue

        inline_ou = _INLINE_OU_SHORTHAND.match(line)
        if inline_ou:
            normalized.append(_format_ou_leg(
                inline_ou.group('name'),
                inline_ou.group('dir'),
                inline_ou.group('line'),
                inline_ou.group('market'),
            ))
            current_player = _title_name(inline_ou.group('name'))
            continue

        inline_alt = _INLINE_ALT_MARKET.match(line)
        if inline_alt:
            normalized.append(_format_ou_leg(
                inline_alt.group('name'),
                'over',
                f"{float(inline_alt.group('line')) - 0.5:g}",
                inline_alt.group('market'),
            ))
            current_player = _title_name(inline_alt.group('name'))
            continue

        direction_only = _DIRECTION_LINE_ONLY.match(line)
        if direction_only and current_player:
            pending_direction = direction_only.group('dir')
            pending_line = direction_only.group('line')
            continue

        if pending_direction and pending_line and current_player:
            market_only = _MARKET_ONLY_LINE.match(line)
            if market_only:
                normalized.append(_format_ou_leg(current_player, pending_direction, pending_line, market_only.group('market')))
                pending_direction = None
                pending_line = None
                continue

        if pending_yes_no_name and _YES_NO_ONLY.match(line):
            pending_yes_no_selection = line.title()
            continue

        if pending_yes_no_name and _MARKET_FOLLOWUP_LINE.match(line):
            pending_yes_no_market = re.sub(r'\s+', ' ', line.replace('-', ' ')).title()
            if pending_yes_no_selection:
                normalized.append(f"{pending_yes_no_name} {pending_yes_no_market} {pending_yes_no_selection}")
                current_player = pending_yes_no_name
                pending_yes_no_name = None
                pending_yes_no_market = None
                pending_yes_no_selection = None
            continue

        if pending_yes_no_name and pending_yes_no_market and _YES_NO_ONLY.match(line):
            normalized.append(f"{pending_yes_no_name} {pending_yes_no_market} {line.title()}")
            current_player = pending_yes_no_name
            pending_yes_no_name = None
            pending_yes_no_market = None
            pending_yes_no_selection = None
            continue

        yes_no = _YES_NO_LINE.match(line)
        if yes_no and current_player:
            market = re.sub(r'\s+', ' ', yes_no.group('market')).replace('-', ' ').title()
            selection = yes_no.group('sel').title()
            normalized.append(f'{current_player} {market} {selection}')
            continue

        if _PLAYER_ONLY_LINE.match(line) and not _MARKET_FOLLOWUP_LINE.match(line):
            current_player = _title_name(line)
            pending_yes_no_name = current_player
            pending_yes_no_market = None
            pending_yes_no_selection = None
            continue

        alt_market = _ALT_MARKET_PHRASE.match(line)
        if alt_market and current_player:
            normalized.append(_format_ou_leg(
                current_player,
                'over',
                f"{float(alt_market.group('line')) - 0.5:g}",
                alt_market.group('market'),
            ))
            continue

        if current_player and re.match(r'^TO\s+(?:SCORE|RECORD)\b', line, re.I):
            trailing_alt = _ALT_MARKET_PHRASE.search(line)
            if trailing_alt:
                normalized.append(_format_ou_leg(
                    current_player,
                    'over',
                    f"{float(trailing_alt.group('line')) - 0.5:g}",
                    trailing_alt.group('market'),
                ))
            continue

        ou_market = _OU_MARKET_LINE.match(line)
        if ou_market and current_player:
            normalized.append(_format_ou_leg(
                current_player,
                ou_market.group('dir'),
                ou_market.group('line'),
                ou_market.group('market'),
            ))
            continue

        leg_with_direction = _LEG_WITH_DIRECTION.match(line)
        if leg_with_direction:
            normalized.append(_format_ou_leg(
                leg_with_direction.group('name'),
                leg_with_direction.group('dir'),
                leg_with_direction.group('line'),
                leg_with_direction.group('market'),
            ))
            continue

        normalized.append(line)

    return normalized


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
    raw_lines = text.replace('\r', '\n').split('\n')
    normalized_lines = [_normalize_line_text(line) for line in raw_lines]
    cleaned_lines = [line for line in normalized_lines if line and not _is_noise_line(line)]
    leg_candidates = _build_leg_candidates(cleaned_lines)
    return '\n'.join(line for line in leg_candidates if line).strip()


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


def _apply_player_name_suggestion(parsed: ParsedScreenshotLeg) -> ParsedScreenshotLeg:
    raw_player = parsed.raw_player_text or parsed.player_name
    suggestion = suggest_player_name(raw_player, sport='NBA') if raw_player else None
    if not suggestion:
        return parsed

    normalized_label = parsed.normalized_label
    if suggestion.auto_applied:
        replacement_target = parsed.raw_player_text or parsed.player_name or ''
        if replacement_target and replacement_target in normalized_label:
            normalized_label = normalized_label.replace(replacement_target, suggestion.suggested_name, 1)
        elif parsed.player_name and parsed.player_name in normalized_label:
            normalized_label = normalized_label.replace(parsed.player_name, suggestion.suggested_name, 1)
        else:
            stat_fragment = parsed.stat_type.title() if parsed.stat_type else ''
            if parsed.direction and parsed.line is not None and stat_fragment:
                normalized_label = f"{suggestion.suggested_name} {parsed.direction.title()} {parsed.line:g} {stat_fragment}"
        parsed.player_name = suggestion.suggested_name

    parsed.suggested_player_name = suggestion.suggested_name
    parsed.suggestion_confidence = suggestion.confidence_score
    parsed.suggestion_confidence_level = suggestion.confidence_level
    parsed.suggestion_auto_applied = suggestion.auto_applied
    return parsed


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
        raw_player_text=leg.parsed_player_name or leg.player,
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
        parsed = _apply_player_name_suggestion(_leg_to_parsed(leg))
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
        if parsed.suggested_player_name and parsed.suggestion_auto_applied:
            parse_warnings.append(
                f"Auto-corrected player name: {parsed.raw_player_text} → {parsed.suggested_player_name}"
            )
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

from __future__ import annotations

import re
from datetime import datetime

from .models import Leg, ParsedScreenshotLeg, ParsedScreenshotResponse, ScreenshotParseDebug
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
    'fanatics sportsbook',
    'bet placed',
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
    'sgp stack',
    'sgp',
    'includes:',
    'edit bet',
    'bet id',
    'total wager',
    'total payout',
    'responsible gaming',
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
    'pr': 'points + rebounds',
    'pa': 'points + assists',
    'ra': 'rebounds + assists',
    'points + rebounds + assists': 'points + rebounds + assists',
    'steals': 'steals',
    'stl': 'steals',
    'blocks': 'blocks',
    'blk': 'blocks',
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
_MATCHUP_CONTEXT_LINE = re.compile(r"^(?P<away>[A-Za-z][A-Za-z .\-'’]+?)\s*(?:@|vs\.?|versus|at)\s*(?P<home>[A-Za-z][A-Za-z .\-'’]+?)$", re.I)
_LEG_WITH_DIRECTION = re.compile(
    r"^(?P<name>[A-Za-z\-'’\. ]+?)\s+(?P<dir>Over|Under)\s+(?P<line>\d+(?:\.\d+)?)\s+(?P<market>[A-Za-z0-9+ ]+)$",
    re.I,
)
_MARKET_FOLLOWUP_LINE = re.compile(r'^(?P<market>Triple\s*-?\s*Double|Double\s*-?\s*Double)$', re.I)
_YES_NO_ONLY = re.compile(r'^(Yes|No)$', re.I)
_DIRECTION_LINE_ONLY = re.compile(r'^(?P<dir>O|U|Over|Under)\s*(?P<line>\d+(?:\.\d+)?)$', re.I)
_MARKET_ONLY_LINE = re.compile(r'^(?P<market>Pts|Points|Reb|Rebs|Rebounds|Ast|Asts|Assists|Stl|Steals|Blk|Blocks|PRA|PR|PA|RA|Pts\s*\+\s*Ast|Pts\s*\+\s*Reb|Reb\s*\+\s*Ast|Rebounds\s*\+\s*Assists|Points\s*\+\s*Assists|Points\s*\+\s*Rebounds|Points\s*\+\s*Rebounds\s*\+\s*Assists|3PM|3PT|Threes|Three\s+Pointers(?:\s+Made)?|Three\s*[- ]\s*Point\s+Field\s+Goals\s+Made)$', re.I)
_ALT_MARKET_PHRASE = re.compile(
    r'^(?:TO\s+(?:SCORE|RECORD)\s+)?(?P<line>\d+(?:\.\d+)?)\s*\+\s*(?P<market>POINTS|REBOUNDS|ASSISTS|STEALS|BLOCKS|PRA|PR|PA|RA)\b',
    re.I,
)
_INLINE_ALT_MARKET = re.compile(
    r"^(?!TO\b)(?P<name>[A-Za-z\-'’\. ]+?)\s+(?:TO\s+(?:SCORE|RECORD)\s+)?(?P<line>\d+(?:\.\d+)?)\s*\+\s*(?P<market>POINTS|REBOUNDS|ASSISTS|STEALS|BLOCKS|PRA|PR|PA|RA)\b",
    re.I,
)
_ALT_THRESHOLD_ONLY = re.compile(r'^TO\s+(?:SCORE|RECORD)\s+(?P<line>\d+(?:\.\d+)?)\s*\+$', re.I)
_THRESHOLD_FIRST_SLASH = re.compile(
    r'^(?P<line>\d+(?:\.\d+)?)\s*\+\s*/\s*(?P<name>[A-Za-z\-\'’\. ]+?)\s+(?P<market>[A-Za-z0-9+\- ]+)$',
    re.I,
)
_PLAYER_NAME_LINE = re.compile(r"^[A-Za-z][A-Za-z\-'’\.]+(?:\s+[A-Za-z][A-Za-z\-'’\.]+){1,3}$")


def _looks_like_player_name_line(line: str) -> bool:
    if not _PLAYER_NAME_LINE.match(line):
        return False
    lowered = line.lower()
    blocked = {'over', 'under', 'yes', 'no', 'points', 'assists', 'rebounds', 'threes', 'parlay', 'to', 'record', 'score'}
    return not any(token in lowered.split() for token in blocked)


def _is_market_fragment_line(line: str) -> bool:
    return bool(
        _OU_MARKET_LINE.match(line)
        or _DIRECTION_LINE_ONLY.match(line)
        or _MARKET_ONLY_LINE.match(line)
        or _YES_NO_LINE.match(line)
        or _YES_NO_ONLY.match(line)
        or _MARKET_FOLLOWUP_LINE.match(line)
        or _ALT_MARKET_PHRASE.match(line)
    )


def _reconstruct_grouped_sgp_lines(lines: list[str]) -> tuple[list[str], bool]:
    reconstructed: list[str] = []
    grouped_triggered = False
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        reconstructed.append(line)
        if _looks_like_player_name_line(line):
            fragments: list[str] = []
            for look_ahead in range(1, 4):
                next_idx = idx + look_ahead
                if next_idx >= len(lines):
                    break
                candidate = lines[next_idx]
                if _is_noise_line(candidate):
                    continue
                if _is_market_fragment_line(candidate):
                    fragments.append(candidate)
                    continue
                break
            if fragments:
                grouped_triggered = True
                reconstructed.extend(fragments)
                idx += len(fragments)
        idx += 1
    return reconstructed, grouped_triggered




def _is_noise_line(line: str) -> bool:
    lowered = line.lower()
    if any(noise in lowered for noise in _NOISE_KEYWORDS):
        if 'same game parlay' in lowered and any(token in lowered for token in ('over', 'under', 'yes', 'no')):
            return False
        return True
    if _ODDS_ONLY_LINE.match(line):
        return True
    if _BUTTON_OR_UI_LINE.match(line):
        return True
    if 'bet slip' in lowered:
        return True
    if lowered in {'draftkings', 'fanduel', 'bet365', 'betmgm', 'bet slip'}:
        return True

    if re.match(r'^\d{1,2}:\d{2}\s*(?:am|pm)\s*(?:et|ct|mt|pt)?$', lowered, re.I):
        return True
    if _MATCHUP_CONTEXT_LINE.match(line):
        return False
    return bool(_MATCHUP_TIME_LINE.match(line))


def _normalize_line_text(line: str) -> str:
    normalized = re.sub(r'\s+', ' ', line).strip(' -–|')
    normalized = normalized.replace('—', '-').replace('–', '-')
    normalized = re.sub(r'(?i)\btriple\s*[- ]\s*double\b', 'Triple Double', normalized)
    normalized = re.sub(r'(?i)\bdouble\s*[- ]\s*double\b', 'Double Double', normalized)
    normalized = re.sub(r'(?i)\bmore\b', 'Over', normalized)
    normalized = re.sub(r'(?i)\bless\b', 'Under', normalized)
    normalized = re.sub(r'\s*\+\s*', ' + ', normalized)
    if '/' in normalized:
        left, right = [part.strip() for part in normalized.split('/', 1)]
        m = re.match(r'^(?P<line>\d+(?:\.\d+)?)\s*\+$', left)
        if m:
            market_options = ['Points + Rebounds + Assists', 'Points + Assists', 'Points + Rebounds', 'Rebounds + Assists', 'Three Pointers Made', 'Rebounds', 'Assists', 'Points', '3PM', 'Threes']
            for market in market_options:
                if right.lower().endswith(market.lower()):
                    name = right[: -len(market)].strip()
                    if name:
                        return _format_plus_leg(name, m.group('line'), market)
    slash_threshold = _THRESHOLD_FIRST_SLASH.match(normalized)
    if slash_threshold:
        return _format_plus_leg(slash_threshold.group('name'), slash_threshold.group('line'), slash_threshold.group('market'))
    return re.sub(r'\s+', ' ', normalized).strip()


def _format_ou_leg(name: str, direction: str, line: str, market: str) -> str:
    clean_name = _title_name(name)
    clean_market = _normalize_market_label(market).title()
    clean_direction = 'Over' if direction.lower() in {'o', 'over'} else 'Under'
    return f'{clean_name} {clean_direction} {line} {clean_market}'


def _format_plus_leg(name: str, line: str, market: str) -> str:
    clean_name = _title_name(name)
    clean_market = _normalize_market_label(market).title()
    threshold = float(line)
    return f'{clean_name} Over {threshold - 0.5:g} {clean_market}'


def _build_leg_candidates(cleaned_lines: list[str]) -> list[str]:
    normalized: list[str] = []
    current_player: str | None = None
    pending_yes_no_name: str | None = None
    pending_yes_no_market: str | None = None
    pending_yes_no_selection: str | None = None
    pending_market_only: str | None = None
    pending_direction: str | None = None
    pending_line: str | None = None
    pending_alt_threshold: str | None = None

    for line in cleaned_lines:
        matchup = _MATCHUP_CONTEXT_LINE.match(line)
        if matchup:
            normalized.append(f"{_title_name(matchup.group('away'))} @ {_title_name(matchup.group('home'))}")
            current_player = None
            pending_market_only = None
            pending_direction = None
            pending_line = None
            pending_alt_threshold = None
            continue
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
        if inline_alt and not re.match(r'^TO\s+(?:SCORE|RECORD)\b', line, re.I):
            normalized.append(_format_plus_leg(
                inline_alt.group('name'),
                f"{float(inline_alt.group('line')):g}",
                inline_alt.group('market'),
            ))
            current_player = _title_name(inline_alt.group('name'))
            continue

        direction_only = _DIRECTION_LINE_ONLY.match(line)
        if direction_only and current_player:
            if pending_market_only:
                normalized.append(_format_ou_leg(current_player, direction_only.group('dir'), direction_only.group('line'), pending_market_only))
                pending_market_only = None
                continue
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

        market_only = _MARKET_ONLY_LINE.match(line)
        if market_only and current_player:
            if pending_alt_threshold:
                normalized.append(_format_plus_leg(current_player, pending_alt_threshold, market_only.group('market')))
                pending_alt_threshold = None
                continue
            if pending_direction and pending_line:
                normalized.append(_format_ou_leg(current_player, pending_direction, pending_line, market_only.group('market')))
                pending_direction = None
                pending_line = None
            else:
                pending_market_only = market_only.group('market')
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

        plus_only = re.match(r'^(?P<line>\d+(?:\.\d+)?)\s*\+$', line)
        if plus_only and current_player and pending_market_only:
            normalized.append(_format_plus_leg(current_player, plus_only.group('line'), pending_market_only))
            pending_market_only = None
            continue

        alt_threshold_only = _ALT_THRESHOLD_ONLY.match(line)
        if alt_threshold_only and current_player:
            pending_alt_threshold = f"{float(alt_threshold_only.group('line')):g}"
            continue

        if _looks_like_player_name_line(line) and not _MARKET_FOLLOWUP_LINE.match(line):
            current_player = _title_name(line)
            pending_yes_no_name = current_player
            pending_yes_no_market = None
            pending_yes_no_selection = None
            pending_market_only = None
            pending_direction = None
            pending_line = None
            pending_alt_threshold = None
            continue

        alt_market = _ALT_MARKET_PHRASE.match(line)
        if alt_market and current_player:
            normalized.append(_format_plus_leg(
                current_player,
                f"{float(alt_market.group('line')):g}",
                alt_market.group('market'),
            ))
            continue

        if current_player and re.match(r'^TO\s+(?:SCORE|RECORD)\b$', line, re.I):
            continue

        if current_player and re.match(r'^TO\s+(?:SCORE|RECORD)\b', line, re.I):
            trailing_alt = _ALT_MARKET_PHRASE.search(line)
            if trailing_alt:
                normalized.append(_format_plus_leg(
                    current_player,
                    f"{float(trailing_alt.group('line')):g}",
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
    lowered = lowered.replace('three pointers made', 'threes').replace('three-pointers made', 'threes').replace('3 ptm', '3pm')
    lowered = lowered.replace('three point field goals made', 'threes')
    lowered = lowered.replace('three-point field goals made', 'threes')
    return _MARKET_ALIASES.get(lowered, lowered)


def _humanize_public_label(label: str) -> str:
    clean = re.sub(r'[_]+', ' ', str(label or '').strip())
    clean = re.sub(r'\bpts\b', 'Points', clean, flags=re.I)
    clean = re.sub(r'\breb\b', 'Rebounds', clean, flags=re.I)
    clean = re.sub(r'\bast\b', 'Assists', clean, flags=re.I)
    clean = re.sub(r'\bpra\b', 'Points + Rebounds + Assists', clean, flags=re.I)
    clean = re.sub(r'\bpa\b', 'Points + Assists', clean, flags=re.I)
    clean = re.sub(r'\bpr\b', 'Points + Rebounds', clean, flags=re.I)
    clean = re.sub(r'\bra\b', 'Rebounds + Assists', clean, flags=re.I)
    return re.sub(r'\s+', ' ', clean).strip()


def _title_name(raw_name: str) -> str:
    return re.sub(r'\s+', ' ', raw_name).strip()


def _build_screenshot_parse_stages(text: str) -> tuple[str, ScreenshotParseDebug]:
    raw_lines = text.replace('\r', '\n').split('\n')
    normalized_lines = [_normalize_line_text(line) for line in raw_lines]
    cleaned_lines = [line for line in normalized_lines if line]
    reconstructed_lines, grouped_triggered = _reconstruct_grouped_sgp_lines(cleaned_lines)
    filtered_lines = [line for line in reconstructed_lines if line and not _is_noise_line(line)]
    leg_candidates = _build_leg_candidates(filtered_lines)
    deduped_candidates: list[str] = []
    seen_candidates: set[str] = set()
    for candidate in leg_candidates:
        key = candidate.lower().strip()
        if not key or key in seen_candidates:
            continue
        seen_candidates.add(key)
        deduped_candidates.append(candidate)
    normalized_text = '\n'.join(deduped_candidates).strip()
    non_empty_raw_lines = [line for line in raw_lines if line.strip()]
    return normalized_text, ScreenshotParseDebug(
        raw_ocr_text=text,
        raw_lines=non_empty_raw_lines,
        normalized_lines=cleaned_lines,
        reconstructed_lines=reconstructed_lines,
        filtered_lines=filtered_lines,
        leg_candidates=deduped_candidates,
        grouped_sgp_reconstruction_triggered=grouped_triggered,
        summary={
            'raw_line_count': len(non_empty_raw_lines),
            'normalized_line_count': len(cleaned_lines),
            'reconstructed_line_count': len(reconstructed_lines),
            'filtered_line_count': len(filtered_lines),
            'leg_candidate_count': len(deduped_candidates),
            'grouped_sgp_reconstruction_triggered': grouped_triggered,
        },
    )


def normalize_sportsbook_ocr_text(text: str) -> str:
    normalized, _ = _build_screenshot_parse_stages(text)
    return normalized


def normalize_sportsbook_slip_text(raw_text: str) -> list[str]:
    normalized, _ = _build_screenshot_parse_stages(raw_text)
    return [line for line in normalized.splitlines() if line.strip()]


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
    normalized_label = _humanize_public_label(leg.raw_text)
    if player_name and stat_type and direction in {'yes', 'no'}:
        normalized_label = f"{player_name} {stat_type.title()} {direction.title()}"
    elif player_name and stat_type and direction and line is not None:
        display_line = leg.display_line or f'{line:g}'
        if isinstance(display_line, str) and display_line.endswith('+') and direction == 'over':
            normalized_label = f"{player_name} Over {display_line} {stat_type.title()}"
        else:
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


def parse_screenshot_text(raw_text: str, cleaned_text: str, *, include_debug: bool = False) -> ParsedScreenshotResponse:
    parse_warnings: list[str] = []
    sportsbook_normalized, parse_debug = _build_screenshot_parse_stages(cleaned_text or raw_text)
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
            parse_warnings.append(f"Low-confidence leg kept for review: {leg.raw_text}")
            raw_lower = (leg.raw_text or '').lower()
            looks_like_prop = bool(leg.player) or any(token in raw_lower for token in ('over', 'under', '+', 'yes', 'no', 'points', 'rebounds', 'assists', 'threes'))
            if not looks_like_prop:
                continue
        if leg.confidence < 0.75:
            parse_warnings.append(f"Review suggested for leg: {leg.raw_text}")
        if parsed.suggested_player_name and parsed.suggestion_auto_applied:
            parse_warnings.append(
                f"Auto-corrected player name: {parsed.raw_player_text} → {parsed.suggested_player_name}"
            )
        parsed.normalized_label = _humanize_public_label(parsed.normalized_label)
        parsed_legs.append(parsed)

    if not parsed_legs:
        parse_warnings.append('No complete prop legs were confidently extracted from the screenshot.')

    if include_debug:
        summary = parse_debug.summary
        parse_warnings.append(
            'debug_summary: raw_lines={raw} reconstructed={reconstructed} filtered={filtered} candidates={candidates} grouped_reconstruction={grouped}'.format(
                raw=summary.get('raw_line_count', 0),
                reconstructed=summary.get('reconstructed_line_count', 0),
                filtered=summary.get('filtered_line_count', 0),
                candidates=summary.get('leg_candidate_count', 0),
                grouped=summary.get('grouped_sgp_reconstruction_triggered', False),
            )
        )

    return ParsedScreenshotResponse(
        raw_text=raw_text,
        parsed_legs=parsed_legs,
        detected_bet_date=_detect_bet_date(raw_text),
        parse_warnings=parse_warnings,
        confidence='medium' if parsed_legs else 'low',
        parse_debug=parse_debug if include_debug else None,
    )

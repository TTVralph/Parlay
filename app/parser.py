from __future__ import annotations

import re

from .alias_runtime import get_alias_map
from .dictionaries import PLAYER_SPORTS, TEAM_SPORTS
from .models import Leg, Sport
from .services.market_registry import canonical_to_player_market, normalize_market
from .player_identity import resolve_player_resolution

ALT_PATTERN = re.compile(r"^(?P<name>[\w .\-'’]+?)\s+(?P<line>\d+(?:\.\d+)?)\+$", re.I)
MARKET_PATTERN = (
    r"p\s*\+\s*r\s*\+\s*a|pts\s*\+\s*reb\s*\+\s*ast|points\s*\+\s*rebounds\s*\+\s*assists|"
    r"p\s*\+\s*r|pts\s*\+\s*reb|points\s*\+\s*rebounds|"
    r"p\s*\+\s*a|pts\s*\+\s*ast|points\s*\+\s*assists|"
    r"r\s*\+\s*a|reb\s*\+\s*ast|rebs\s*\+\s*asts|rebounds\s*\+\s*assists|"
    r"pra|pr|pa|ra|"
    r"pts|points|reb|rebs|rebounds|ast|asts|assists|stl|steals|blk|blocks|tov|turnovers|"
    r"points rebounds assists|pts reb ast|points rebounds|points assists|rebounds assists|"
    r"3s|3pm|3 ptm|3pt made|3ptm|threes|three pointers|three-pointers|threes made|"
    r"3 pointers made|3-pointers made|three pointers made|three-point field goals made|three point field goals made|"
    r"pass yds|passing yards|rush yds|rushing yards|rec yds|receiving yards|hits|hit|strikeouts|strikeout|ks|k|total\s*bases|tb|runs|rbi|rbis|home\s*runs|home\s*run|hr|triple\s*double|double\s*double|first basket|first bucket|first scorer|to score first|first rebound|to get first rebound|first assist|to record first assist|first three|first 3 pointer|first 3pt made|first three-pointer made|last basket|last bucket|to score last|first steal|first block"
)

NUMBER_FIRST_PATTERN = re.compile(
    rf"^(?P<line>\d+(?:\.\d+)?)\+?\s*(?P<market>{MARKET_PATTERN})\s+(?P<name>[\w .\-'’]+?)$",
    re.I,
)
OVER_UNDER_PATTERN = re.compile(
    rf"^(?P<name>[\w .\-'’]+?)\s+(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?P<market>{MARKET_PATTERN})?$",
    re.I,
)
OVER_UNDER_MARKET_FIRST_PATTERN = re.compile(
    rf"^(?P<name>[\w .\-'’]+?)\s+(?P<dir>o|u|over|under)\s*(?P<market>{MARKET_PATTERN})\s*(?P<line>\d+(?:\.\d+)?)$",
    re.I,
)
YES_NO_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+(?P<market>triple\s*double|double\s*double)\s+(?P<dir>yes|no)$",
    re.I,
)
NAMED_MARKET_PATTERN = re.compile(
    rf"^(?P<name>[\w .\-'’]+?)\s+(?P<line>\d+(?:\.\d+)?)\+?\s*(?P<market>{MARKET_PATTERN})$",
    re.I,
)
EVENT_SEQUENCE_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+(?P<market>first basket|first bucket|first scorer|to score first|first rebound|to get first rebound|first assist|to record first assist|first three|first 3 pointer|first 3pt made|first three-pointer made|last basket|last bucket|to score last|first steal|first block)$",
    re.I,
)
MILESTONE_PROP_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+to\s+(?P<action>record|score)\s+(?P<line>\d+(?:\.\d+)?)\+\s*(?P<market>points|rebounds|assists)$",
    re.I,
)

TIME_WINDOW_MARKET_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+(?P<line>\d+(?:\.\d+)?)\+?\s*(?P<market>points|rebounds|assists|threes|three pointers made|3pm).*(?P<window>first\s+\d+\s+minutes|first\s+quarter|first\s+half|first\s+basket|race\s+to|first\s+to)",
    re.I,
)
TIME_WINDOW_PHRASE = re.compile(r"(first\s+\d+\s+minutes|first\s+quarter|first\s+half|first\s+basket|race\s+to|first\s+to)", re.I)
ML_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+ml$', re.I)
MONEYLINE_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+moneyline$', re.I)
SPREAD_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+(?P<line>[+\-]\d+(?:\.\d+)?)$', re.I)
TOTAL_ONLY_PATTERN = re.compile(r'^(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)$', re.I)
GAME_TOTAL_PATTERN = re.compile(r'^(?:game\s+total\s+)?(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?:total\s*points|points)?$', re.I)
SPORT_PREFIX_PATTERN = re.compile(r'^(nba|nfl|mlb|wnba)\s*[:\-]?\s*', re.I)
OPPONENT_SUFFIX_PATTERN = re.compile(r"\s+v(?:s|\.|ersus)\s+(?P<opponent>[\w .\-'’]+)$", re.I)
AT_OPPONENT_SUFFIX_PATTERN = re.compile(r"\s+@\s*(?P<opponent>[\w .\-'’]+)$", re.I)
MATCHUP_SUFFIX_PATTERN = re.compile(r"\s*\(?(?P<home>[a-z0-9 .\-]+)\s+v(?:s|\.)\s+(?P<away>[a-z0-9 .\-]+)\)?$", re.I)
MATCHUP_LINE_PATTERN = re.compile(r"^(?P<away>[\w .\-'’]+?)\s+(?:@|at|vs\.?|versus)\s+(?P<home>[\w .\-'’]+?)$", re.I)
AMERICAN_ODDS_TOKEN_PATTERN = re.compile(r'(?<!\w)(?P<odds>[+\-]\d{3,4})(?!\w)')
NOISE_PUNCTUATION_PATTERN = re.compile(r'[!?.;,]+$')
REPEATED_PLUS_THRESHOLD_PATTERN = re.compile(r'(?P<value>\d+(?:\.\d+)?)\+{2,}(?!\d)')

_NORMALIZED_STAT_TYPES = {
    'player_pra': 'PRA',
    'player_pr': 'PR',
    'player_pa': 'PA',
    'player_ra': 'RA',
}


def _normalized_stat_type_for_market(market_type: str) -> str:
    return _NORMALIZED_STAT_TYPES.get(market_type, market_type)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


def _american_to_decimal(american_odds: int) -> float:
    if american_odds > 0:
        return round((american_odds / 100.0) + 1.0, 4)
    return round((100.0 / abs(american_odds)) + 1.0, 4)


def _extract_line_odds(line: str) -> tuple[str, int | None]:
    odds_tokens = [int(match.group('odds')) for match in AMERICAN_ODDS_TOKEN_PATTERN.finditer(line)]
    clean_line = AMERICAN_ODDS_TOKEN_PATTERN.sub('', line)
    clean_line = re.sub(r'\(\s*\)', ' ', clean_line)
    clean_line = _normalize_whitespace(clean_line)
    return clean_line, (odds_tokens[-1] if odds_tokens else None)


def normalize_input_lines(text: str) -> list[str]:
    fragments: list[str] = []
    for source_line in text.splitlines():
        if not source_line.strip():
            continue
        normalized = source_line.replace('|', '\n')
        normalized = re.sub(r'\s*,\s*', '\n', normalized)
        for piece in normalized.splitlines():
            candidate = piece.strip()
            if not candidate:
                continue
            candidate = re.sub(r'\s*:\s*', ' ', candidate)
            candidate = NOISE_PUNCTUATION_PATTERN.sub('', candidate)
            candidate = REPEATED_PLUS_THRESHOLD_PATTERN.sub(lambda m: f"{m.group('value')}+", candidate)
            candidate = _normalize_whitespace(candidate)
            if candidate:
                fragments.append(candidate)
    return fragments


def _is_initial_shorthand(token: str) -> bool:
    parts = [part for part in re.sub(r"[.'’]", '', token).split() if part]
    return len(parts) == 2 and len(parts[0]) <= 2


def _is_odds_only_line(line: str) -> bool:
    without_odds = AMERICAN_ODDS_TOKEN_PATTERN.sub('', line)
    normalized = re.sub(r'[^a-z]', '', without_odds.lower())
    return normalized in {'', 'odds', 'americanodds', 'price'}


def _team_lookup(token: str) -> str | None:
    normalized = token.lower().strip()
    aliases = get_alias_map('team')
    if normalized in aliases:
        return aliases[normalized]
    for team in TEAM_SPORTS:
        if normalized == team.lower():
            return team
    return None


def _player_lookup(token: str) -> tuple[str | None, float]:
    if _is_initial_shorthand(token):
        return None, 0.0

    resolution = resolve_player_resolution(token)
    if resolution:
        return resolution.resolved_player_name, resolution.resolution_confidence

    token = token.lower().strip()
    players = get_alias_map('player')
    if token in players:
        return players[token], 0.94
    for _, full_name in players.items():
        if token == full_name.lower():
            return full_name, 0.9

    starts_with = sorted({full_name for full_name in players.values() if full_name.lower().startswith(f'{token} ')})
    if len(starts_with) == 1:
        return starts_with[0], 0.85
    return None, 0.0


def _market_lookup(token: str) -> str | None:
    canonical = normalize_market(token)
    if canonical:
        return canonical_to_player_market(canonical)

    normalized = token.lower().strip().replace('-', ' ')
    normalized = re.sub(r'\s*\+\s*', ' + ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    compact = normalized.replace(' ', '')
    alias_map = get_alias_map('market')
    return alias_map.get(normalized) or alias_map.get(compact)


def _extract_opponent_context(line: str) -> tuple[str, str | None]:
    for pattern in (OPPONENT_SUFFIX_PATTERN, AT_OPPONENT_SUFFIX_PATTERN):
        match = pattern.search(line)
        if match:
            opponent_raw = _normalize_whitespace(match.group('opponent'))
            opponent_team = _team_lookup(opponent_raw)
            clean_line = _normalize_whitespace(line[:match.start()])
            return clean_line, opponent_team

    matchup = MATCHUP_SUFFIX_PATTERN.search(line)
    if matchup:
        home_team = _team_lookup(_normalize_whitespace(matchup.group('home')))
        away_team = _team_lookup(_normalize_whitespace(matchup.group('away')))
        clean_line = _normalize_whitespace(line[:matchup.start()])
        return clean_line, away_team or home_team
    return line, None




def _parse_matchup_line(line: str) -> tuple[str | None, str | None]:
    match = MATCHUP_LINE_PATTERN.match(line.strip())
    if not match:
        return None, None
    away_team = _team_lookup(_normalize_whitespace(match.group('away')))
    home_team = _team_lookup(_normalize_whitespace(match.group('home')))
    if not away_team or not home_team:
        return None, None
    return away_team, home_team


def _attach_matchup_context(
    leg: Leg,
    *,
    away_team: str | None,
    home_team: str | None,
) -> Leg:
    if not away_team or not home_team:
        return leg
    possible = [away_team, home_team]
    matchup = f'{away_team} @ {home_team}'
    notes = list(leg.notes)
    if not any(note.startswith('Game matchup context: ') for note in notes):
        notes.append(f'Game matchup context: {matchup}')
    return leg.model_copy(update={
        'possible_teams': possible,
        'game_matchup': matchup,
        'notes': notes,
    })

def _infer_sport(team: str | None = None, player: str | None = None, sport_hint: Sport | None = None) -> Sport:
    if team and team in TEAM_SPORTS:
        return TEAM_SPORTS[team]  # type: ignore[return-value]
    if player and player in PLAYER_SPORTS:
        return PLAYER_SPORTS[player]  # type: ignore[return-value]
    return sport_hint or 'NBA'


def parse_text(text: str, sport_hint: Sport | None = None) -> list[Leg]:
    lines = normalize_input_lines(text)
    normalized_lines: list[tuple[str, int | None]] = []
    for line in lines:
        clean_line, line_odds = _extract_line_odds(line)
        if line_odds is not None and _is_odds_only_line(line) and normalized_lines:
            previous_line, previous_odds = normalized_lines[-1]
            normalized_lines[-1] = (previous_line, previous_odds if previous_odds is not None else line_odds)
            continue
        if clean_line:
            normalized_lines.append((clean_line, line_odds))

    legs: list[Leg] = []
    current_hint = sport_hint
    pending_matchup: tuple[str | None, str | None] = (None, None)

    def _append_leg(leg: Leg) -> None:
        legs.append(_attach_matchup_context(leg, away_team=pending_matchup[0], home_team=pending_matchup[1]))

    for line, line_odds in normalized_lines:
        lower = line.lower()
        prefix_match = SPORT_PREFIX_PATTERN.match(lower)
        clean_line = line
        clean_lower = lower
        line_sport_hint = current_hint
        if prefix_match:
            current_hint = prefix_match.group(1).upper()  # type: ignore[assignment]
            line_sport_hint = current_hint
            clean_line = _normalize_whitespace(SPORT_PREFIX_PATTERN.sub('', line))
            clean_lower = clean_line.lower()
            if not clean_line:
                continue

        matchup_away, matchup_home = _parse_matchup_line(clean_line)
        if matchup_away and matchup_home:
            pending_matchup = (matchup_away, matchup_home)
            if legs and not legs[-1].game_matchup:
                legs[-1] = _attach_matchup_context(legs[-1], away_team=matchup_away, home_team=matchup_home)
            continue

        if re.match(r'^(odds|american odds|stake|risk|to\s*win|payout|profit|draftkings|fanduel|bet365|caesars)\b', clean_lower):
            continue

        line_without_opponent, opponent_team = _extract_opponent_context(clean_line)
        normalized_line = (
            line_without_opponent
            .replace('three-point field goals made', 'threes')
            .replace('Three-point field goals made', 'threes')
            .replace('three point field goals made', 'threes')
            .replace('Three point field goals made', 'threes')
            .replace('three pointers made', 'threes')
            .replace('Three pointers made', 'threes')
            .replace('3 pointers made', 'threes')
            .replace('3pt made', 'threes')
            .replace('Threes made', 'threes')
            .replace('threes made', 'threes')
        )
        normalized_lower = normalized_line.lower()
        opponent_note = [f'Opponent context: {opponent_team}'] if opponent_team else []

        ml_match = ML_PATTERN.match(normalized_lower) or MONEYLINE_PATTERN.match(normalized_lower)
        if ml_match:
            team = _team_lookup(ml_match.group('team'))
            sport = _infer_sport(team=team, sport_hint=line_sport_hint)
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type='moneyline', team=team, confidence=0.95 if team else 0.3, notes=[] if team else ['Unrecognized team alias'], american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        spread_match = SPREAD_PATTERN.match(normalized_lower)
        if spread_match:
            team = _team_lookup(spread_match.group('team'))
            line_value = float(spread_match.group('line'))
            sport = _infer_sport(team=team, sport_hint=line_sport_hint)
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type='spread', team=team, line=line_value, display_line=spread_match.group('line'), confidence=0.93 if team else 0.35, notes=[] if team else ['Unrecognized team alias'], american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        total_match = GAME_TOTAL_PATTERN.match(normalized_lower) or TOTAL_ONLY_PATTERN.match(normalized_lower)
        if total_match:
            direction_token = total_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(total_match.group('line'))
            _append_leg(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='game_total', direction=direction, line=line_value, display_line=str(line_value), confidence=0.82, notes=['Will infer event from other legs in same ticket when possible'], american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        time_window_match = TIME_WINDOW_MARKET_PATTERN.match(normalized_line)
        if time_window_match or TIME_WINDOW_PHRASE.search(normalized_line):
            parsed_name = _normalize_whitespace((time_window_match.group('name') if time_window_match else normalized_line.split()[0:2] and ' '.join(normalized_line.split()[0:2])) or '')
            resolved_player, resolution_conf = _player_lookup(parsed_name) if parsed_name else (None, 0.0)
            player = resolved_player or parsed_name or None
            market_token = (time_window_match.group('market') if time_window_match else 'points').lower()
            market_type = _market_lookup(market_token) or 'player_points'
            line_value = float(time_window_match.group('line')) - 0.5 if time_window_match else None
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            notes = ['Unsupported time-window market', *opponent_note]
            _append_leg(Leg(
                raw_text=clean_line,
                sport=sport,
                market_type=market_type,
                player=player,
                direction='over' if line_value is not None else None,
                line=line_value,
                display_line=(f"{time_window_match.group('line')}+" if time_window_match else None),
                confidence=0.7,
                notes=notes,
                parse_confidence=0.7,
                parsed_player_name=parsed_name or None,
                normalized_stat_type=_normalized_stat_type_for_market(market_type),
                resolution_confidence=resolution_conf if resolved_player else None,
                resolved_player_name=resolved_player,
                american_odds=line_odds,
                decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None,
            ))
            continue

        yes_no_match = YES_NO_PATTERN.match(normalized_line)
        if yes_no_match:
            parsed_name = _normalize_whitespace(yes_no_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_raw = yes_no_match.group('market').lower()
            market_type = _market_lookup(market_raw)
            direction = yes_no_match.group('dir').lower()
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            parse_confidence = (1.0 + (1.0 if market_type else 0.0) + (1.0 if resolved_player else 0.7)) / 3.0
            confidence = max(parse_confidence, resolution_conf if resolved_player else parse_confidence)
            notes = list(opponent_note)
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            if confidence < 0.9:
                notes.append('Parsed player name from raw text; alias not found')
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction=direction, line=1.0, display_line=direction.title(), confidence=confidence, notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        ou_match = OVER_UNDER_PATTERN.match(normalized_line)
        if ou_match is None:
            ou_match = OVER_UNDER_MARKET_FIRST_PATTERN.match(normalized_line)
        if ou_match:
            parsed_name = _normalize_whitespace(ou_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup((ou_match.group('market') or 'points').lower())
            direction_token = ou_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(ou_match.group('line'))
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            parse_confidence = (1.0 + 1.0 + (1.0 if market_type else 0.0) + (1.0 if resolved_player else 0.7)) / 4.0
            confidence = max(parse_confidence, resolution_conf if resolved_player else parse_confidence)
            notes = list(opponent_note)
            if _is_initial_shorthand(parsed_name):
                notes.append('player identity ambiguous: Ambiguous player shorthand; include full first name')
                confidence = min(confidence, 0.62)
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            if confidence < 0.9:
                notes.append('Parsed player name from raw text; alias not found')
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction=direction, line=line_value, display_line=str(line_value), confidence=confidence, notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        event_sequence_match = EVENT_SEQUENCE_PATTERN.match(normalized_line)
        if event_sequence_match:
            parsed_name = _normalize_whitespace(event_sequence_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup(event_sequence_match.group('market').lower())
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            notes = list(opponent_note)
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            parse_confidence = (1.0 + (1.0 if market_type else 0.0) + (1.0 if resolved_player else 0.7)) / 3.0
            confidence = max(parse_confidence, resolution_conf if resolved_player else parse_confidence)
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='yes', line=1.0, display_line='Yes', confidence=confidence, notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        milestone_match = MILESTONE_PROP_PATTERN.match(normalized_line)
        if milestone_match:
            parsed_name = _normalize_whitespace(milestone_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup(milestone_match.group('market').lower())
            line_value = float(milestone_match.group('line')) - 0.5
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            alias_hit = resolved_player is not None
            notes = ['Mapped milestone prop to equivalent over line for odds matching', *opponent_note]
            if not alias_hit:
                notes.append('Parsed player name from raw text; alias not found')
            parse_confidence = (1.0 + 1.0 + (1.0 if market_type else 0.0) + (1.0 if alias_hit else 0.7)) / 4.0
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            milestone_display_line = milestone_match.group('line')
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='over', line=line_value, display_line=f'{milestone_display_line}+', confidence=max(parse_confidence, resolution_conf if alias_hit else parse_confidence), notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if alias_hit else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        named_market_match = NAMED_MARKET_PATTERN.match(normalized_line)
        if named_market_match:
            parsed_name = _normalize_whitespace(named_market_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup(named_market_match.group('market').lower())
            line_value = float(named_market_match.group('line'))
            standardized = line_value - 0.5
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            alias_hit = resolved_player is not None
            notes = ['Mapped plus-threshold to over line for MVP settlement', *opponent_note]
            if not alias_hit:
                notes.append('Parsed player name from raw text; alias not found')
            parse_confidence = (1.0 + 1.0 + (1.0 if market_type else 0.0) + (1.0 if alias_hit else 0.7)) / 4.0
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='over', line=standardized, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=max(parse_confidence, resolution_conf if alias_hit else parse_confidence), notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if alias_hit else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        alt_match = ALT_PATTERN.match(normalized_line)
        if alt_match:
            parsed_name = _normalize_whitespace(alt_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            line_value = float(alt_match.group('line'))
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            default_market = 'player_hits' if sport == 'MLB' else ('player_points' if sport == 'NBA' else 'player_receiving_yards')
            notes = ['Assumed hits market because no market label was given'] if sport == 'MLB' else ['Assumed points market because no market label was given'] if sport == 'NBA' else ['Assumed receiving yards market because no market label was given']
            notes.extend(opponent_note)
            if resolved_player is None:
                notes.append('Parsed player name from raw text; alias not found')
            alt_confidence = 0.78 if resolved_player else 0.66
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=default_market, player=player, direction='over', line=line_value - 0.5, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=alt_confidence, notes=notes, parse_confidence=alt_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(default_market), resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        number_first_match = NUMBER_FIRST_PATTERN.match(normalized_line)
        if number_first_match:
            parsed_name = _normalize_whitespace(number_first_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup(number_first_match.group('market').lower())
            line_value = float(number_first_match.group('line')) - 0.5
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            notes = ['Mapped plus-threshold to over line for MVP settlement', *opponent_note]
            if _is_initial_shorthand(parsed_name):
                notes.append('player identity ambiguous: Ambiguous player shorthand; include full first name')
            parse_confidence = 0.8 if resolved_player else 0.68
            confidence = max(parse_confidence, resolution_conf if resolved_player else parse_confidence)
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
                confidence = min(confidence, 0.7)
            _append_leg(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='over', line=line_value, display_line=f"{number_first_match.group('line')}+", confidence=confidence, notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=_normalized_stat_type_for_market(market_type), resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player, american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))
            continue

        _append_leg(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='player_points', confidence=0.0, notes=['Unmatched leg'], american_odds=line_odds, decimal_odds=_american_to_decimal(line_odds) if line_odds is not None else None))

    for idx, leg in enumerate(legs):
        if leg.original_leg_text is None:
            legs[idx] = leg.model_copy(update={
                'original_leg_text': leg.raw_text,
                'normalized_line_value': leg.line,
            })

    return legs


def is_valid_leg(leg: Leg) -> bool:
    if leg.confidence <= 0:
        return False
    invalid_notes = {'Unmatched leg', 'Could not parse stat type'}
    if any(note in invalid_notes for note in leg.notes):
        return False
    if leg.market_type in {'moneyline', 'spread'}:
        return bool(leg.team) and (leg.market_type != 'spread' or leg.line is not None)
    if leg.market_type == 'game_total':
        return leg.direction is not None and leg.line is not None
    if leg.market_type in {'player_triple_double', 'player_double_double', 'player_first_basket', 'player_first_rebound', 'player_first_assist', 'player_first_three', 'player_last_basket', 'player_first_steal', 'player_first_block'}:
        return bool(leg.player and leg.direction in {'yes', 'no'})
    return bool(leg.player and leg.direction and leg.line is not None)


def filter_valid_legs(legs: list[Leg]) -> list[Leg]:
    return [leg for leg in legs if is_valid_leg(leg)]

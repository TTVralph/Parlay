from __future__ import annotations

import re

from .alias_runtime import get_alias_map
from .dictionaries import PLAYER_SPORTS, TEAM_SPORTS
from .models import Leg, Sport
from .services.market_registry import canonical_to_player_market, normalize_market
from .player_identity import resolve_player_resolution

ALT_PATTERN = re.compile(r"^(?P<name>[\w .\-'’]+?)\s+(?P<line>\d+(?:\.\d+)?)\+$", re.I)
OVER_UNDER_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?P<market>pts\s*\+\s*ast|points\s*\+\s*assists|pts\s*\+\s*reb|points\s*\+\s*rebounds|reb\s*\+\s*ast|rebounds\s*\+\s*assists|pra|points\s*\+\s*rebounds\s*\+\s*assists|pr|points\s*\+\s*rebounds|pa|points\s*\+\s*assists|ra|rebounds\s*\+\s*assists|pts|points|reb|rebounds|ast|assists|stl|steals|blk|blocks|tov|turnovers|p\+r\+a|pts\+reb\+ast|points rebounds assists|pts reb ast|p\+r|pts\+reb|points rebounds|p\+a|pts\+ast|points assists|r\+a|reb\+ast|rebounds assists|3s|3pm|threes|threes made|3pt made|three pointers made|3 pointers made|3-pointers made|three-point field goals made|three point field goals made|pass yds|passing yards|rush yds|rushing yards|rec yds|receiving yards|hits)?$",
    re.I,
)
NAMED_MARKET_PATTERN = re.compile(
    r"^(?P<name>[\w .\-'’]+?)\s+(?P<line>\d+(?:\.\d+)?)\+?\s*(?P<market>pts\s*\+\s*ast|points\s*\+\s*assists|pts\s*\+\s*reb|points\s*\+\s*rebounds|reb\s*\+\s*ast|rebounds\s*\+\s*assists|pra|points\s*\+\s*rebounds\s*\+\s*assists|pr|points\s*\+\s*rebounds|pa|points\s*\+\s*assists|ra|rebounds\s*\+\s*assists|pts|points|reb|rebounds|ast|assists|stl|steals|blk|blocks|tov|turnovers|p\+r\+a|pts\+reb\+ast|points rebounds assists|pts reb ast|p\+r|pts\+reb|points rebounds|p\+a|pts\+ast|points assists|r\+a|reb\+ast|rebounds assists|3s|3pm|threes|threes made|3pt made|three pointers made|3 pointers made|3-pointers made|three-point field goals made|three point field goals made|pass yds|passing yards|rush yds|rushing yards|rec yds|receiving yards|hits)$",
    re.I,
)
ML_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+ml$', re.I)
MONEYLINE_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+moneyline$', re.I)
SPREAD_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+(?P<line>[+\-]\d+(?:\.\d+)?)$', re.I)
TOTAL_ONLY_PATTERN = re.compile(r'^(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)$', re.I)
GAME_TOTAL_PATTERN = re.compile(r'^(?:game\s+total\s+)?(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?:total\s*points|points)?$', re.I)
SPORT_PREFIX_PATTERN = re.compile(r'^(nba|nfl|mlb)\s*[:\-]?\s*', re.I)
OPPONENT_SUFFIX_PATTERN = re.compile(r"\s+v(?:s|\.|ersus)\s+(?P<opponent>[\w .\-'’]+)$", re.I)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


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
    match = OPPONENT_SUFFIX_PATTERN.search(line)
    if not match:
        return line, None
    opponent_raw = _normalize_whitespace(match.group('opponent'))
    opponent_team = _team_lookup(opponent_raw)
    clean_line = _normalize_whitespace(line[:match.start()])
    return clean_line, opponent_team


def _infer_sport(team: str | None = None, player: str | None = None, sport_hint: Sport | None = None) -> Sport:
    if team and team in TEAM_SPORTS:
        return TEAM_SPORTS[team]  # type: ignore[return-value]
    if player and player in PLAYER_SPORTS:
        return PLAYER_SPORTS[player]  # type: ignore[return-value]
    return sport_hint or 'NBA'


def parse_text(text: str, sport_hint: Sport | None = None) -> list[Leg]:
    lines = [_normalize_whitespace(line) for line in text.splitlines() if line.strip()]
    legs: list[Leg] = []
    current_hint = sport_hint

    for line in lines:
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
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type='moneyline', team=team, confidence=0.95 if team else 0.3, notes=[] if team else ['Unrecognized team alias']))
            continue

        spread_match = SPREAD_PATTERN.match(normalized_lower)
        if spread_match:
            team = _team_lookup(spread_match.group('team'))
            line_value = float(spread_match.group('line'))
            sport = _infer_sport(team=team, sport_hint=line_sport_hint)
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type='spread', team=team, line=line_value, display_line=spread_match.group('line'), confidence=0.93 if team else 0.35, notes=[] if team else ['Unrecognized team alias']))
            continue

        total_match = GAME_TOTAL_PATTERN.match(normalized_lower) or TOTAL_ONLY_PATTERN.match(normalized_lower)
        if total_match:
            direction_token = total_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(total_match.group('line'))
            legs.append(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='game_total', direction=direction, line=line_value, display_line=str(line_value), confidence=0.82, notes=['Will infer event from other legs in same ticket when possible']))
            continue

        ou_match = OVER_UNDER_PATTERN.match(normalized_line)
        if ou_match:
            parsed_name = _normalize_whitespace(ou_match.group('name'))
            resolved_player, resolution_conf = _player_lookup(parsed_name)
            player = resolved_player or parsed_name
            market_type = _market_lookup((ou_match.group('market') or 'points').lower())
            direction_token = ou_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(ou_match.group('line'))
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            parse_confidence = 0.92 if market_type else 0.55
            confidence = max(parse_confidence, resolution_conf if resolved_player else 0.82)
            notes = list(opponent_note)
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            if confidence < 0.9:
                notes.append('Parsed player name from raw text; alias not found')
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction=direction, line=line_value, display_line=str(line_value), confidence=confidence, notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=market_type, resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player))
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
            parse_confidence = 0.9 if market_type else 0.55
            if not market_type:
                notes.append('Could not parse stat type')
                market_type = 'player_points'
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='over', line=standardized, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=max(parse_confidence, resolution_conf if alias_hit else 0.82), notes=notes, parse_confidence=parse_confidence, parsed_player_name=parsed_name, normalized_stat_type=market_type, resolution_confidence=resolution_conf if alias_hit else None, resolved_player_name=resolved_player))
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
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=default_market, player=player, direction='over', line=line_value - 0.5, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=0.7 if resolved_player else 0.6, notes=notes, parse_confidence=0.7 if resolved_player else 0.6, parsed_player_name=parsed_name, normalized_stat_type=default_market, resolution_confidence=resolution_conf if resolved_player else None, resolved_player_name=resolved_player))
            continue

        legs.append(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='player_points', confidence=0.0, notes=['Unmatched leg']))

    return legs

from __future__ import annotations

import re

from .alias_runtime import get_alias_map
from .dictionaries import PLAYER_SPORTS, TEAM_SPORTS
from .models import Leg, Sport

ALT_PATTERN = re.compile(r'^(?P<name>[a-z0-9 .\-]+?)\s+(?P<line>\d+(?:\.\d+)?)\+$', re.I)
OVER_UNDER_PATTERN = re.compile(
    r'^(?P<name>[a-z0-9 .\-]+?)\s+(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?P<market>pts|points|reb|rebounds|ast|assists|3s|3pm|threes|threes made|three pointers made|pra|pass yds|passing yards|rush yds|rushing yards|rec yds|receiving yards|hits)?$',
    re.I,
)
NAMED_MARKET_PATTERN = re.compile(
    r'^(?P<name>[a-z0-9 .\-]+?)\s+(?P<line>\d+(?:\.\d+)?)\+?\s*(?P<market>pts|points|reb|rebounds|ast|assists|3s|3pm|threes|threes made|three pointers made|pra|pass yds|passing yards|rush yds|rushing yards|rec yds|receiving yards|hits)$',
    re.I,
)
ML_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+ml$', re.I)
SPREAD_PATTERN = re.compile(r'^(?P<team>[a-z0-9 .\-]+?)\s+(?P<line>[+\-]\d+(?:\.\d+)?)$', re.I)
TOTAL_ONLY_PATTERN = re.compile(r'^(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)$', re.I)
GAME_TOTAL_PATTERN = re.compile(r'^(?:game\s+total\s+)?(?P<dir>o|u|over|under)\s*(?P<line>\d+(?:\.\d+)?)\s*(?:total\s*points|points)?$', re.I)
SPORT_PREFIX_PATTERN = re.compile(r'^(nba|nfl|mlb)\s*[:\-]?\s*', re.I)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


def _team_lookup(token: str) -> str | None:
    return get_alias_map('team').get(token.lower().strip())


def _player_lookup(token: str) -> str | None:
    token = token.lower().strip()
    players = get_alias_map('player')
    if token in players:
        return players[token]
    for _, full_name in players.items():
        if token == full_name.lower():
            return full_name
    return None


def _market_lookup(token: str) -> str:
    return get_alias_map('market').get(token.lower().strip(), 'player_points')


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

        ml_match = ML_PATTERN.match(clean_lower)
        if ml_match:
            team = _team_lookup(ml_match.group('team'))
            sport = _infer_sport(team=team, sport_hint=line_sport_hint)
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type='moneyline', team=team, confidence=0.95 if team else 0.3, notes=[] if team else ['Unrecognized team alias']))
            continue

        spread_match = SPREAD_PATTERN.match(clean_lower)
        if spread_match:
            team = _team_lookup(spread_match.group('team'))
            line_value = float(spread_match.group('line'))
            sport = _infer_sport(team=team, sport_hint=line_sport_hint)
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type='spread', team=team, line=line_value, display_line=spread_match.group('line'), confidence=0.93 if team else 0.35, notes=[] if team else ['Unrecognized team alias']))
            continue

        total_match = GAME_TOTAL_PATTERN.match(clean_lower) or TOTAL_ONLY_PATTERN.match(clean_lower)
        if total_match:
            direction_token = total_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(total_match.group('line'))
            legs.append(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='game_total', direction=direction, line=line_value, display_line=str(line_value), confidence=0.82, notes=['Will infer event from other legs in same ticket when possible']))
            continue

        ou_match = OVER_UNDER_PATTERN.match(clean_lower)
        if ou_match:
            player = _player_lookup(ou_match.group('name'))
            market_type = _market_lookup((ou_match.group('market') or 'points').lower())
            direction_token = ou_match.group('dir').lower()
            direction = 'over' if direction_token in {'o', 'over'} else 'under'
            line_value = float(ou_match.group('line'))
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction=direction, line=line_value, display_line=str(line_value), confidence=0.92 if player else 0.35, notes=[] if player else ['Unrecognized player alias']))
            continue

        named_market_match = NAMED_MARKET_PATTERN.match(clean_lower)
        if named_market_match:
            player = _player_lookup(named_market_match.group('name'))
            market_type = _market_lookup(named_market_match.group('market').lower())
            line_value = float(named_market_match.group('line'))
            standardized = line_value - 0.5
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=market_type, player=player, direction='over', line=standardized, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=0.9 if (player and market_type) else 0.35, notes=['Mapped plus-threshold to over line for MVP settlement'] if player and market_type else ['Unable to confidently identify player or market']))
            continue

        alt_match = ALT_PATTERN.match(clean_lower)
        if alt_match:
            player = _player_lookup(alt_match.group('name'))
            line_value = float(alt_match.group('line'))
            sport = _infer_sport(player=player, sport_hint=line_sport_hint)
            default_market = 'player_hits' if sport == 'MLB' else ('player_points' if sport == 'NBA' else 'player_receiving_yards')
            notes = ['Assumed hits market because no market label was given'] if sport == 'MLB' else ['Assumed points market because no market label was given'] if sport == 'NBA' else ['Assumed receiving yards market because no market label was given']
            legs.append(Leg(raw_text=clean_line, sport=sport, market_type=default_market, player=player, direction='over', line=line_value - 0.5, display_line=f'{int(line_value) if line_value.is_integer() else line_value}+', confidence=0.7 if player else 0.25, notes=notes))
            continue

        legs.append(Leg(raw_text=clean_line, sport=line_sport_hint or 'NBA', market_type='player_points', confidence=0.0, notes=['Unmatched leg']))

    return legs

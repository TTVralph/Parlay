from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import re


@dataclass(frozen=True)
class PlayerRecord:
    id: str
    canonical_name: str
    normalized_name: str
    team_id: str
    league: str
    espn_player_id: str
    sportsapipro_player_id: str | None = None


@dataclass(frozen=True)
class PlayerAliasRecord:
    player_id: str
    alias: str
    normalized_alias: str


@dataclass(frozen=True)
class PlayerResolution:
    resolved_player_name: str
    resolved_player_id: str
    resolved_team: str | None
    resolution_confidence: float


TEAM_ID_TO_NAME = {
    'nba-den': 'Denver Nuggets',
    'nba-mem': 'Memphis Grizzlies',
    'nba-gsw': 'Golden State Warriors',
    'nba-bos': 'Boston Celtics',
    'nba-lal': 'Los Angeles Lakers',
    'nba-okc': 'Oklahoma City Thunder',
    'nba-dal': 'Dallas Mavericks',
    'nba-uta': 'Utah Jazz',
    'nba-hou': 'Houston Rockets',
    'nba-mia': 'Miami Heat',
    'nba-det': 'Detroit Pistons',
}


def normalize_player_name(name: str) -> str:
    lowered = name.lower()
    stripped = re.sub(r'[^a-z0-9\s]', ' ', lowered)
    return re.sub(r'\s+', ' ', stripped).strip()


def _without_suffix(normalized_name: str) -> str:
    parts = normalized_name.split()
    if parts and parts[-1] in {'jr', 'sr', 'ii', 'iii', 'iv'}:
        return ' '.join(parts[:-1]).strip()
    return normalized_name


_PLAYERS: tuple[PlayerRecord, ...] = (
    PlayerRecord('nba-nikola-jokic', 'Nikola Jokic', normalize_player_name('Nikola Jokic'), 'nba-den', 'NBA', '3112335'),
    PlayerRecord('nba-jamal-murray', 'Jamal Murray', normalize_player_name('Jamal Murray'), 'nba-den', 'NBA', '3936299'),
    PlayerRecord('nba-jayson-tatum', 'Jayson Tatum', normalize_player_name('Jayson Tatum'), 'nba-bos', 'NBA', '4065648'),
    PlayerRecord('nba-stephen-curry', 'Stephen Curry', normalize_player_name('Stephen Curry'), 'nba-gsw', 'NBA', '3975'),
    PlayerRecord('nba-scotty-pippen-jr', 'Scotty Pippen Jr.', normalize_player_name('Scotty Pippen Jr.'), 'nba-mem', 'NBA', '4432819'),
    PlayerRecord('nba-cam-spencer', 'Cam Spencer', normalize_player_name('Cam Spencer'), 'nba-mem', 'NBA', '4683778'),
    PlayerRecord('nba-jaylen-brown', 'Jaylen Brown', normalize_player_name('Jaylen Brown'), 'nba-bos', 'NBA', '3917376'),
    PlayerRecord('nba-cooper-flagg', 'Cooper Flagg', normalize_player_name('Cooper Flagg'), 'nba-dal', 'NBA', '5307443'),
    PlayerRecord('nba-keyonte-george', 'Keyonte George', normalize_player_name('Keyonte George'), 'nba-uta', 'NBA', '5105848'),
    PlayerRecord('nba-draymond-green', 'Draymond Green', normalize_player_name('Draymond Green'), 'nba-gsw', 'NBA', '6589'),
    PlayerRecord('nba-amen-thompson', 'Amen Thompson', normalize_player_name('Amen Thompson'), 'nba-hou', 'NBA', '5105716'),
    PlayerRecord('nba-bam-adebayo', 'Bam Adebayo', normalize_player_name('Bam Adebayo'), 'nba-mia', 'NBA', '4066261'),
    PlayerRecord('nba-cade-cunningham', 'Cade Cunningham', normalize_player_name('Cade Cunningham'), 'nba-det', 'NBA', '4432166'),
    PlayerRecord('nba-desmond-bane', 'Desmond Bane', normalize_player_name('Desmond Bane'), 'nba-mem', 'NBA', '4397136'),
)


_PLAYER_ALIASES: tuple[PlayerAliasRecord, ...] = (
    PlayerAliasRecord('nba-nikola-jokic', 'Jokic', normalize_player_name('Jokic')),
    PlayerAliasRecord('nba-jamal-murray', 'Murray', normalize_player_name('Murray')),
    PlayerAliasRecord('nba-stephen-curry', 'Curry', normalize_player_name('Curry')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scotty Pippen', normalize_player_name('Scotty Pippen')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scotty Pippen Jr', normalize_player_name('Scotty Pippen Jr')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scotty Pippen Jr.', normalize_player_name('Scotty Pippen Jr.')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scottie Pippen Jr', normalize_player_name('Scottie Pippen Jr')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scottie Pippen Jr.', normalize_player_name('Scottie Pippen Jr.')),
    PlayerAliasRecord('nba-cam-spencer', 'Cameron Spencer', normalize_player_name('Cameron Spencer')),
    PlayerAliasRecord('nba-draymond-green', 'Draymond', normalize_player_name('Draymond')),
    PlayerAliasRecord('nba-amen-thompson', 'Amen', normalize_player_name('Amen')),
    PlayerAliasRecord('nba-bam-adebayo', 'Bam', normalize_player_name('Bam')),
    PlayerAliasRecord('nba-desmond-bane', 'Bane', normalize_player_name('Bane')),
)


@lru_cache(maxsize=1)
def _player_directory() -> dict[str, dict[str, PlayerRecord]]:
    by_id = {row.id: row for row in _PLAYERS}
    by_normalized_name = {row.normalized_name: row for row in _PLAYERS}
    alias_by_normalized = {row.normalized_alias: by_id[row.player_id] for row in _PLAYER_ALIASES if row.player_id in by_id}
    return {
        'by_id': by_id,
        'by_normalized_name': by_normalized_name,
        'alias_by_normalized': alias_by_normalized,
    }


PLAYERS_BY_ID = _player_directory()['by_id']
PLAYERS_BY_NORMALIZED_NAME = _player_directory()['by_normalized_name']
ALIASES_BY_NORMALIZED = _player_directory()['alias_by_normalized']


def resolve_player_resolution(player_name: str | None) -> PlayerResolution | None:
    if not player_name:
        return None
    normalized = normalize_player_name(player_name)
    if not normalized:
        return None
    candidates = [normalized]
    without_suffix = _without_suffix(normalized)
    if without_suffix and without_suffix != normalized:
        candidates.append(without_suffix)

    for candidate in candidates:
        direct = PLAYERS_BY_NORMALIZED_NAME.get(candidate)
        if direct:
            return PlayerResolution(direct.canonical_name, direct.id, team_name_from_id(direct.team_id), 1.0)
        alias = ALIASES_BY_NORMALIZED.get(candidate)
        if alias:
            return PlayerResolution(alias.canonical_name, alias.id, team_name_from_id(alias.team_id), 0.97)

    best: PlayerRecord | None = None
    score = 0.0
    for record in PLAYERS_BY_ID.values():
        ratio = SequenceMatcher(None, normalized, record.normalized_name).ratio()
        if ratio > score:
            best = record
            score = ratio
    if best and score >= 0.86:
        return PlayerResolution(best.canonical_name, best.id, team_name_from_id(best.team_id), round(score, 2))
    return None


def resolve_player_identity(player_name: str | None) -> PlayerRecord | None:
    resolution = resolve_player_resolution(player_name)
    if not resolution:
        return None
    return PLAYERS_BY_ID.get(resolution.resolved_player_id)


def team_name_from_id(team_id: str | None) -> str | None:
    if not team_id:
        return None
    return TEAM_ID_TO_NAME.get(team_id)

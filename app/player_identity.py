from __future__ import annotations

from dataclasses import dataclass
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


TEAM_ID_TO_NAME = {
    'nba-den': 'Denver Nuggets',
    'nba-mem': 'Memphis Grizzlies',
    'nba-gsw': 'Golden State Warriors',
    'nba-bos': 'Boston Celtics',
    'nba-lal': 'Los Angeles Lakers',
    'nba-okc': 'Oklahoma City Thunder',
}


def normalize_player_name(name: str) -> str:
    lowered = name.lower()
    stripped = re.sub(r'[^a-z0-9\s]', ' ', lowered)
    return re.sub(r'\s+', ' ', stripped).strip()


_PLAYERS: tuple[PlayerRecord, ...] = (
    PlayerRecord('nba-nikola-jokic', 'Nikola Jokic', normalize_player_name('Nikola Jokic'), 'nba-den', 'NBA', '3112335'),
    PlayerRecord('nba-jamal-murray', 'Jamal Murray', normalize_player_name('Jamal Murray'), 'nba-den', 'NBA', '3936299'),
    PlayerRecord('nba-jayson-tatum', 'Jayson Tatum', normalize_player_name('Jayson Tatum'), 'nba-bos', 'NBA', '4065648'),
    PlayerRecord('nba-stephen-curry', 'Stephen Curry', normalize_player_name('Stephen Curry'), 'nba-gsw', 'NBA', '3975'),
    PlayerRecord('nba-scotty-pippen-jr', 'Scotty Pippen Jr.', normalize_player_name('Scotty Pippen Jr.'), 'nba-mem', 'NBA', '4432819'),
    PlayerRecord('nba-cam-spencer', 'Cam Spencer', normalize_player_name('Cam Spencer'), 'nba-mem', 'NBA', '4683778'),
)


_PLAYER_ALIASES: tuple[PlayerAliasRecord, ...] = (
    PlayerAliasRecord('nba-nikola-jokic', 'Jokic', normalize_player_name('Jokic')),
    PlayerAliasRecord('nba-jamal-murray', 'Murray', normalize_player_name('Murray')),
    PlayerAliasRecord('nba-stephen-curry', 'Curry', normalize_player_name('Curry')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scotty Pippen', normalize_player_name('Scotty Pippen')),
    PlayerAliasRecord('nba-scotty-pippen-jr', 'Scotty Pippen Jr', normalize_player_name('Scotty Pippen Jr')),
)


PLAYERS_BY_ID = {row.id: row for row in _PLAYERS}
PLAYERS_BY_NORMALIZED_NAME = {row.normalized_name: row for row in _PLAYERS}
ALIASES_BY_NORMALIZED = {row.normalized_alias: row for row in _PLAYER_ALIASES}


def resolve_player_identity(player_name: str | None) -> PlayerRecord | None:
    if not player_name:
        return None
    normalized = normalize_player_name(player_name)
    if not normalized:
        return None
    direct = PLAYERS_BY_NORMALIZED_NAME.get(normalized)
    if direct:
        return direct
    alias = ALIASES_BY_NORMALIZED.get(normalized)
    if alias:
        return PLAYERS_BY_ID.get(alias.player_id)
    return None


def team_name_from_id(team_id: str | None) -> str | None:
    if not team_id:
        return None
    return TEAM_ID_TO_NAME.get(team_id)


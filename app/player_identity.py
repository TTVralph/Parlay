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
    'nba-dal': 'Dallas Mavericks',
    'nba-uta': 'Utah Jazz',
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
    candidates = [normalized]
    without_suffix = _without_suffix(normalized)
    if without_suffix and without_suffix != normalized:
        candidates.append(without_suffix)

    for candidate in candidates:
        direct = PLAYERS_BY_NORMALIZED_NAME.get(candidate)
        if direct:
            return direct
        alias = ALIASES_BY_NORMALIZED.get(candidate)
        if alias:
            return PLAYERS_BY_ID.get(alias.player_id)
    return None


def team_name_from_id(team_id: str | None) -> str | None:
    if not team_id:
        return None
    return TEAM_ID_TO_NAME.get(team_id)

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
import re
from typing import Protocol

SportCode = str


@dataclass(frozen=True)
class CanonicalPlayerIdentity:
    sport: SportCode
    canonical_player_id: str
    source_player_ids: dict[str, str] = field(default_factory=dict)
    full_name: str = ''
    normalized_name: str = ''
    alternate_names: tuple[str, ...] = ()
    team_id: str | None = None
    team_name: str | None = None
    active_status: str = 'active'


@dataclass(frozen=True)
class CanonicalTeamIdentity:
    sport: SportCode
    canonical_team_id: str
    source_team_ids: dict[str, str] = field(default_factory=dict)
    full_team_name: str = ''
    normalized_team_name: str = ''
    abbreviations: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerResolutionResult:
    sport: SportCode
    resolved_player_name: str | None
    resolved_player_id: str | None
    resolved_team: str | None
    confidence: float
    ambiguity_reason: str | None = None
    candidate_players: tuple[str, ...] = ()


class SportIdentityAdapter(Protocol):
    sport: SportCode

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]: ...
    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]: ...
    def normalize_stat_label(self, stat_label: str | None) -> str | None: ...


def normalize_entity_name(name: str) -> str:
    lowered = name.lower().strip()
    lowered = re.sub(r"[.'’]", '', lowered)
    lowered = re.sub(r'[^a-z0-9\s]', ' ', lowered)
    lowered = re.sub(r'\b(jr|sr|ii|iii|iv)\b', ' ', lowered)
    return re.sub(r'\s+', ' ', lowered).strip()


class NBAIdentityAdapter:
    sport = 'NBA'

    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]:
        return (
            CanonicalTeamIdentity('NBA', 'nba-den', {'espn': '7'}, 'Denver Nuggets', normalize_entity_name('Denver Nuggets'), ('DEN',), ('Nuggets', 'Denver')),
            CanonicalTeamIdentity('NBA', 'nba-mem', {'espn': '29'}, 'Memphis Grizzlies', normalize_entity_name('Memphis Grizzlies'), ('MEM',), ('Grizzlies', 'Memphis')),
            CanonicalTeamIdentity('NBA', 'nba-gsw', {'espn': '9'}, 'Golden State Warriors', normalize_entity_name('Golden State Warriors'), ('GSW',), ('Warriors',)),
            CanonicalTeamIdentity('NBA', 'nba-bos', {'espn': '2'}, 'Boston Celtics', normalize_entity_name('Boston Celtics'), ('BOS',), ('Celtics',)),
            CanonicalTeamIdentity('NBA', 'nba-lal', {'espn': '13'}, 'Los Angeles Lakers', normalize_entity_name('Los Angeles Lakers'), ('LAL',), ('Lakers',)),
            CanonicalTeamIdentity('NBA', 'nba-okc', {'espn': '25'}, 'Oklahoma City Thunder', normalize_entity_name('Oklahoma City Thunder'), ('OKC',), ('Thunder',)),
            CanonicalTeamIdentity('NBA', 'nba-dal', {'espn': '6'}, 'Dallas Mavericks', normalize_entity_name('Dallas Mavericks'), ('DAL',), ('Mavericks', 'Mavs')),
            CanonicalTeamIdentity('NBA', 'nba-uta', {'espn': '26'}, 'Utah Jazz', normalize_entity_name('Utah Jazz'), ('UTA',), ('Jazz',)),
            CanonicalTeamIdentity('NBA', 'nba-hou', {'espn': '10'}, 'Houston Rockets', normalize_entity_name('Houston Rockets'), ('HOU',), ('Rockets',)),
            CanonicalTeamIdentity('NBA', 'nba-mia', {'espn': '14'}, 'Miami Heat', normalize_entity_name('Miami Heat'), ('MIA',), ('Heat',)),
            CanonicalTeamIdentity('NBA', 'nba-det', {'espn': '8'}, 'Detroit Pistons', normalize_entity_name('Detroit Pistons'), ('DET',), ('Pistons',)),
        )

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]:
        return (
            CanonicalPlayerIdentity('NBA', 'nba-nikola-jokic', {'espn': '3112335'}, 'Nikola Jokic', normalize_entity_name('Nikola Jokic'), ('Jokic',), 'nba-den', 'Denver Nuggets'),
            CanonicalPlayerIdentity('NBA', 'nba-jamal-murray', {'espn': '3936299'}, 'Jamal Murray', normalize_entity_name('Jamal Murray'), ('Murray',), 'nba-den', 'Denver Nuggets'),
            CanonicalPlayerIdentity('NBA', 'nba-jayson-tatum', {'espn': '4065648'}, 'Jayson Tatum', normalize_entity_name('Jayson Tatum'), ('JT', 'Tatum'), 'nba-bos', 'Boston Celtics'),
            CanonicalPlayerIdentity('NBA', 'nba-stephen-curry', {'espn': '3975'}, 'Stephen Curry', normalize_entity_name('Stephen Curry'), ('Steph Curry', 'Curry'), 'nba-gsw', 'Golden State Warriors'),
            CanonicalPlayerIdentity('NBA', 'nba-scotty-pippen-jr', {'espn': '4432819'}, 'Scotty Pippen Jr.', normalize_entity_name('Scotty Pippen Jr.'), ('Scotty Pippen Jr', 'Scotty Pippen', 'Scottie Pippen Jr.', 'Scottie Pippen Jr'), 'nba-mem', 'Memphis Grizzlies'),
            CanonicalPlayerIdentity('NBA', 'nba-cam-spencer', {'espn': '4683778'}, 'Cam Spencer', normalize_entity_name('Cam Spencer'), ('Cameron Spencer',), 'nba-mem', 'Memphis Grizzlies'),
            CanonicalPlayerIdentity('NBA', 'nba-jaylen-brown', {'espn': '3917376'}, 'Jaylen Brown', normalize_entity_name('Jaylen Brown'), ('Brown',), 'nba-bos', 'Boston Celtics'),
            CanonicalPlayerIdentity('NBA', 'nba-cooper-flagg', {'espn': '5307443'}, 'Cooper Flagg', normalize_entity_name('Cooper Flagg'), ('Flagg',), 'nba-dal', 'Dallas Mavericks'),
            CanonicalPlayerIdentity('NBA', 'nba-keyonte-george', {'espn': '5105848'}, 'Keyonte George', normalize_entity_name('Keyonte George'), ('George',), 'nba-uta', 'Utah Jazz'),
            CanonicalPlayerIdentity('NBA', 'nba-draymond-green', {'espn': '6589'}, 'Draymond Green', normalize_entity_name('Draymond Green'), ('Draymond',), 'nba-gsw', 'Golden State Warriors'),
            CanonicalPlayerIdentity('NBA', 'nba-amen-thompson', {'espn': '5105716'}, 'Amen Thompson', normalize_entity_name('Amen Thompson'), ('Amen',), 'nba-hou', 'Houston Rockets'),
            CanonicalPlayerIdentity('NBA', 'nba-bam-adebayo', {'espn': '4066261'}, 'Bam Adebayo', normalize_entity_name('Bam Adebayo'), ('Bam',), 'nba-mia', 'Miami Heat'),
            CanonicalPlayerIdentity('NBA', 'nba-cade-cunningham', {'espn': '4432166'}, 'Cade Cunningham', normalize_entity_name('Cade Cunningham'), (), 'nba-det', 'Detroit Pistons'),
            CanonicalPlayerIdentity('NBA', 'nba-desmond-bane', {'espn': '4397136'}, 'Desmond Bane', normalize_entity_name('Desmond Bane'), ('Bane',), 'nba-mem', 'Memphis Grizzlies'),
            CanonicalPlayerIdentity('NBA', 'nba-og-anunoby', {'espn': '3934719'}, 'OG Anunoby', normalize_entity_name('OG Anunoby'), ('O.G. Anunoby',), None, None),
        )

    def normalize_stat_label(self, stat_label: str | None) -> str | None:
        if not stat_label:
            return stat_label
        key = normalize_entity_name(stat_label).replace(' ', '')
        mapping = {
            'pts': 'player_points', 'points': 'player_points',
            'threes': 'player_threes', '3pm': 'player_threes', '3pointersmade': 'player_threes', '3pmmade': 'player_threes',
        }
        return mapping.get(key, stat_label)


class NFLIdentityAdapter:
    sport = 'NFL'

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]:
        return ()

    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]:
        return ()

    def normalize_stat_label(self, stat_label: str | None) -> str | None:
        return stat_label


class MLBIdentityAdapter:
    sport = 'MLB'

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]:
        return ()

    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]:
        return ()

    def normalize_stat_label(self, stat_label: str | None) -> str | None:
        return stat_label


@lru_cache(maxsize=1)
def get_sport_adapters() -> dict[SportCode, SportIdentityAdapter]:
    return {'NBA': NBAIdentityAdapter(), 'NFL': NFLIdentityAdapter(), 'MLB': MLBIdentityAdapter()}


@lru_cache(maxsize=4)
def _player_directory(sport: SportCode) -> tuple[dict[str, CanonicalPlayerIdentity], dict[str, list[CanonicalPlayerIdentity]]]:
    adapter = get_sport_adapters().get(sport)
    if not adapter:
        return {}, {}
    players = adapter.load_players()
    by_id = {p.canonical_player_id: p for p in players}
    by_name: dict[str, list[CanonicalPlayerIdentity]] = {}
    for p in players:
        for alias in (p.full_name, *p.alternate_names):
            normalized = normalize_entity_name(alias)
            bucket = by_name.setdefault(normalized, [])
            if all(existing.canonical_player_id != p.canonical_player_id for existing in bucket):
                bucket.append(p)
    return by_id, by_name


def resolve_player_identity(player_name: str | None, sport: SportCode = 'NBA') -> PlayerResolutionResult:
    if not player_name:
        return PlayerResolutionResult(sport=sport, resolved_player_name=None, resolved_player_id=None, resolved_team=None, confidence=0.0, ambiguity_reason='player not found in sport directory')
    normalized = normalize_entity_name(player_name)
    by_id, by_name = _player_directory(sport)
    direct = by_name.get(normalized, [])
    if len(direct) == 1:
        p = direct[0]
        return PlayerResolutionResult(sport, p.full_name, p.canonical_player_id, p.team_name, 1.0)
    if len(direct) > 1:
        names = tuple(sorted(item.full_name for item in direct))
        return PlayerResolutionResult(sport, None, None, None, 0.5, ambiguity_reason='player identity ambiguous', candidate_players=names)

    ranked: list[tuple[float, CanonicalPlayerIdentity]] = []
    for p in by_id.values():
        score = SequenceMatcher(None, normalized, p.normalized_name).ratio()
        if score >= 0.86:
            ranked.append((score, p))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return PlayerResolutionResult(sport, None, None, None, 0.0, ambiguity_reason='player not found in sport directory')
    if len(ranked) > 1 and (ranked[0][0] - ranked[1][0]) < 0.05:
        names = tuple(item[1].full_name for item in ranked[:3])
        return PlayerResolutionResult(sport, None, None, None, round(ranked[0][0], 2), ambiguity_reason='player identity ambiguous', candidate_players=names)
    pick = ranked[0][1]
    return PlayerResolutionResult(sport, pick.full_name, pick.canonical_player_id, pick.team_name, round(ranked[0][0], 2))


def resolve_team_name(team_id: str | None, sport: SportCode = 'NBA') -> str | None:
    if not team_id:
        return None
    adapter = get_sport_adapters().get(sport)
    if not adapter:
        return None
    return next((team.full_team_name for team in adapter.load_teams() if team.canonical_team_id == team_id), None)

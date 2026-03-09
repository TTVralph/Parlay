from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
from time import monotonic
from typing import Protocol
from urllib import error, request

SportCode = str
logger = logging.getLogger(__name__)

_NBA_DIRECTORY_PATH = Path(__file__).resolve().parent / 'data' / 'nba_players_directory.json'
_NBA_REFRESH_INTERVAL_SECONDS = 60 * 60 * 12
_NBA_REFRESH_TIMEOUT_SECONDS = 4


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
    lowered = lowered.replace('&', ' and ')
    lowered = re.sub(r"[.'’`´]", '', lowered)
    lowered = re.sub(r'[^a-z0-9\s]', ' ', lowered)
    lowered = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', ' ', lowered)
    return re.sub(r'\s+', ' ', lowered).strip()


def _lookup_keys(name: str) -> set[str]:
    cleaned = name.strip()
    keys = {normalize_entity_name(cleaned)}
    dotted = re.sub(r'\b([a-zA-Z])\s+([a-zA-Z])\b', r'\1.\2.', cleaned)
    keys.add(normalize_entity_name(dotted))
    without_suffix = re.sub(r'\b(Jr\.?|Sr\.?|II|III|IV|V)\b', '', cleaned, flags=re.IGNORECASE)
    keys.add(normalize_entity_name(without_suffix))
    parts = re.sub(r"[.'’]", '', cleaned).split()
    if len(parts) >= 2:
        keys.add(normalize_entity_name(' '.join(parts[-2:])))
        keys.add(normalize_entity_name(parts[-1]))
    return {item for item in keys if item}


def _slugify_player_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize_entity_name(name)).strip('-')


def _maybe_refresh_nba_directory() -> None:
    # best effort online refresh; never blocks primary identity resolution path
    now = monotonic()
    if now - _maybe_refresh_nba_directory._last_checked < _NBA_REFRESH_INTERVAL_SECONDS:  # type: ignore[attr-defined]
        return
    _maybe_refresh_nba_directory._last_checked = now  # type: ignore[attr-defined]

    feed_url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
    try:
        with request.urlopen(feed_url, timeout=_NBA_REFRESH_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        teams = payload.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
        if not teams:
            return
        directory = json.loads(_NBA_DIRECTORY_PATH.read_text()) if _NBA_DIRECTORY_PATH.exists() else {'players': []}
        if not isinstance(directory.get('players'), list):
            return
        directory['last_refresh_attempt'] = 'success'
        directory['last_refresh_team_count'] = len(teams)
        _NBA_DIRECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _NBA_DIRECTORY_PATH.write_text(json.dumps(directory, indent=2, sort_keys=True) + '\n')
        _player_directory.cache_clear()
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.debug('Skipping NBA directory refresh; feed unavailable: %s', exc)


_maybe_refresh_nba_directory._last_checked = 0.0  # type: ignore[attr-defined]


class NBAIdentityAdapter:
    sport = 'NBA'

    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]:
        teams = (
            ('nba-atl', '1', 'Atlanta Hawks', 'ATL', ('Hawks', 'Atlanta')),
            ('nba-bos', '2', 'Boston Celtics', 'BOS', ('Celtics', 'Boston')),
            ('nba-bkn', '17', 'Brooklyn Nets', 'BKN', ('Nets', 'Brooklyn')),
            ('nba-cha', '30', 'Charlotte Hornets', 'CHA', ('Hornets', 'Charlotte')),
            ('nba-chi', '4', 'Chicago Bulls', 'CHI', ('Bulls', 'Chicago')),
            ('nba-cle', '5', 'Cleveland Cavaliers', 'CLE', ('Cavaliers', 'Cavs', 'Cleveland')),
            ('nba-dal', '6', 'Dallas Mavericks', 'DAL', ('Mavericks', 'Mavs', 'Dallas')),
            ('nba-den', '7', 'Denver Nuggets', 'DEN', ('Nuggets', 'Denver')),
            ('nba-det', '8', 'Detroit Pistons', 'DET', ('Pistons', 'Detroit')),
            ('nba-gsw', '9', 'Golden State Warriors', 'GSW', ('Warriors', 'Golden State')),
            ('nba-hou', '10', 'Houston Rockets', 'HOU', ('Rockets', 'Houston')),
            ('nba-ind', '11', 'Indiana Pacers', 'IND', ('Pacers', 'Indiana')),
            ('nba-lac', '12', 'LA Clippers', 'LAC', ('Clippers', 'Los Angeles Clippers')),
            ('nba-lal', '13', 'Los Angeles Lakers', 'LAL', ('Lakers', 'LA Lakers')),
            ('nba-mem', '29', 'Memphis Grizzlies', 'MEM', ('Grizzlies', 'Memphis')),
            ('nba-mia', '14', 'Miami Heat', 'MIA', ('Heat', 'Miami')),
            ('nba-mil', '15', 'Milwaukee Bucks', 'MIL', ('Bucks', 'Milwaukee')),
            ('nba-min', '16', 'Minnesota Timberwolves', 'MIN', ('Timberwolves', 'Wolves', 'Minnesota')),
            ('nba-nop', '3', 'New Orleans Pelicans', 'NOP', ('Pelicans', 'New Orleans')),
            ('nba-nyk', '18', 'New York Knicks', 'NYK', ('Knicks', 'New York')),
            ('nba-okc', '25', 'Oklahoma City Thunder', 'OKC', ('Thunder', 'Oklahoma City')),
            ('nba-orl', '19', 'Orlando Magic', 'ORL', ('Magic', 'Orlando')),
            ('nba-phi', '20', 'Philadelphia 76ers', 'PHI', ('76ers', 'Sixers', 'Philadelphia')),
            ('nba-phx', '21', 'Phoenix Suns', 'PHX', ('Suns', 'Phoenix')),
            ('nba-por', '22', 'Portland Trail Blazers', 'POR', ('Trail Blazers', 'Blazers', 'Portland')),
            ('nba-sac', '23', 'Sacramento Kings', 'SAC', ('Kings', 'Sacramento')),
            ('nba-sas', '24', 'San Antonio Spurs', 'SAS', ('Spurs', 'San Antonio')),
            ('nba-tor', '28', 'Toronto Raptors', 'TOR', ('Raptors', 'Toronto')),
            ('nba-uta', '26', 'Utah Jazz', 'UTA', ('Jazz', 'Utah')),
            ('nba-was', '27', 'Washington Wizards', 'WAS', ('Wizards', 'Washington')),
        )
        return tuple(
            CanonicalTeamIdentity('NBA', team_id, {'espn': espn_id}, team_name, normalize_entity_name(team_name), (abbr,), aliases)
            for team_id, espn_id, team_name, abbr, aliases in teams
        )

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]:
        _maybe_refresh_nba_directory()
        if not _NBA_DIRECTORY_PATH.exists():
            return ()
        payload = json.loads(_NBA_DIRECTORY_PATH.read_text())
        players = payload.get('players') if isinstance(payload, dict) else []
        if not isinstance(players, list):
            return ()

        parsed: list[CanonicalPlayerIdentity] = []
        for row in players:
            if not isinstance(row, dict):
                continue
            full_name = str(row.get('full_name') or '').strip()
            if not full_name:
                continue
            aliases = tuple(str(alias).strip() for alias in row.get('aliases', []) if str(alias).strip())
            canonical_player_id = str(row.get('canonical_player_id') or f"nba-{_slugify_player_id(full_name)}")
            source_ids = row.get('source_player_ids')
            parsed.append(
                CanonicalPlayerIdentity(
                    sport='NBA',
                    canonical_player_id=canonical_player_id,
                    source_player_ids=source_ids if isinstance(source_ids, dict) else {},
                    full_name=full_name,
                    normalized_name=normalize_entity_name(str(row.get('normalized_name') or full_name)),
                    alternate_names=aliases,
                    team_id=str(row.get('team_id')) if row.get('team_id') else None,
                    team_name=str(row.get('team_name')) if row.get('team_name') else None,
                )
            )
        return tuple(parsed)

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
            for normalized in _lookup_keys(alias):
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
        score = max(
            SequenceMatcher(None, normalized, p.normalized_name).ratio(),
            *(SequenceMatcher(None, normalized, normalize_entity_name(alias)).ratio() for alias in p.alternate_names),
        )
        if score >= 0.75:
            ranked.append((score, p))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return PlayerResolutionResult(sport, None, None, None, 0.0, ambiguity_reason='player not found in sport directory')
    if ranked[0][0] < 0.86:
        suggestions = tuple(item[1].full_name for item in ranked[:3])
        return PlayerResolutionResult(sport, None, None, None, round(ranked[0][0], 2), ambiguity_reason='player not found in sport directory', candidate_players=suggestions)
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

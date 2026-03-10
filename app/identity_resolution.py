from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
from time import monotonic
from typing import Any, Protocol
from urllib import error, request

from .sports_reference_identity import NBA_PLAYERS_CACHE_PATH, NBA_TEAMS_CACHE_PATH
from .services.identity_normalizer import generate_player_aliases, normalize_person_name, normalize_team_name

SportCode = str
logger = logging.getLogger(__name__)

_NBA_DIRECTORY_PATH = Path(__file__).resolve().parent / 'data' / 'nba_players_directory.json'
_NBA_REFRESH_INTERVAL_SECONDS = 60 * 60 * 12
_NBA_REFRESH_TIMEOUT_SECONDS = 6
_NBA_STALE_AFTER = timedelta(hours=30)
_MIN_EXPECTED_NBA_PLAYERS = 350
_MAX_ROSTER_SIZE_WARNING_DELTA = 5

_NBA_LEAGUE_DIRECTORY_URL = 'https://cdn.nba.com/static/json/liveData/leagueRoster.json'
_ESPN_TEAMS_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
_ESPN_TEAM_ROSTER_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster'


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
    aliases: tuple[str, ...] = ()
    normalized_aliases: tuple[str, ...] = ()


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
    identity_source: str | None = None
    identity_last_refreshed_at: str | None = None
    match_method: str | None = None
    confidence_level: str = 'LOW'


class SportIdentityAdapter(Protocol):
    sport: SportCode

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]: ...
    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]: ...
    def normalize_stat_label(self, stat_label: str | None) -> str | None: ...


def normalize_entity_name(name: str) -> str:
    return normalize_person_name(name)


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




def _is_initials_or_surname_form(raw_name: str, canonical_name: str) -> bool:
    raw_parts = [p for p in normalize_person_name(raw_name).split() if p]
    canon_parts = [p for p in normalize_person_name(canonical_name).split() if p]
    if len(raw_parts) == 1 and len(canon_parts) >= 2 and raw_parts[0] == canon_parts[-1]:
        return True
    if len(raw_parts) == 2 and len(canon_parts) >= 2:
        return len(raw_parts[0]) <= 2 and raw_parts[-1] == canon_parts[-1]
    return False

def _slugify_player_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize_entity_name(name)).strip('-')


def _slugify_team_id(team: str) -> str:
    return f"nba-{re.sub(r'[^a-z0-9]+', '-', normalize_team_name(team)).strip('-')}"


def _fetch_json(url: str, *, timeout: int = _NBA_REFRESH_TIMEOUT_SECONDS, urlopen: Any = request.urlopen) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def _player_name(row: dict[str, Any]) -> str:
    return str(row.get('fullName') or row.get('longName') or row.get('displayName') or '').strip()


def _build_alias_keys(name: str) -> list[str]:
    if not name:
        return []
    parts = re.sub(r"[.'’]", '', name).split()
    aliases: set[str] = set()
    if len(parts) >= 2:
        aliases.add(parts[-1])
    return sorted(alias for alias in aliases if alias and alias.lower() != name.lower())


def _extract_nba_league_players(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team in payload.get('leagueRoster', {}).get('teams', []):
        if not isinstance(team, dict):
            continue
        team_name = str(team.get('teamName') or '').strip()
        team_abbr = str(team.get('teamTricode') or '').strip()
        team_id = str(team.get('teamId') or '').strip()
        canonical_team_id = _slugify_team_id(team_name or team_abbr or team_id)
        for player in team.get('players', []):
            if not isinstance(player, dict):
                continue
            name = _player_name(player)
            if not name:
                continue
            rows.append({
                'full_name': name,
                'normalized_name': normalize_entity_name(name),
                'source_player_ids': {'nba': str(player.get('personId') or '')},
                'team_id': canonical_team_id,
                'team_name': team_name or None,
                'active_status': 'active' if str(player.get('rosterStatus') or '').lower() != 'inactive' else 'inactive',
                'source_urls': [_NBA_LEAGUE_DIRECTORY_URL],
                'alias_keys': _build_alias_keys(name),
            })
    return rows


def _extract_espn_teams(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    teams: dict[str, dict[str, str]] = {}
    for team_wrapper in payload.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', []):
        team = team_wrapper.get('team', {}) if isinstance(team_wrapper, dict) else {}
        if not isinstance(team, dict):
            continue
        team_id = str(team.get('id') or '').strip()
        name = str(team.get('displayName') or '').strip()
        if not team_id or not name:
            continue
        teams[team_id] = {'team_name': name, 'team_id': _slugify_team_id(name), 'abbr': str(team.get('abbreviation') or '').strip()}
    return teams


def _extract_espn_roster_players(team_id: str, payload: dict[str, Any], team_info: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for athlete in payload.get('athletes', []):
        if not isinstance(athlete, dict):
            continue
        for player in athlete.get('items', []):
            if not isinstance(player, dict):
                continue
            name = str(player.get('fullName') or player.get('displayName') or '').strip()
            if not name:
                continue
            rows.append({
                'full_name': name,
                'normalized_name': normalize_entity_name(name),
                'source_player_ids': {'espn': str(player.get('id') or '')},
                'team_id': team_info['team_id'],
                'team_name': team_info['team_name'],
                'active_status': 'active',
                'source_urls': [_ESPN_TEAM_ROSTER_URL.format(team_id=team_id)],
                'alias_keys': _build_alias_keys(name),
            })
    return rows


def _merge_player_rows(main_rows: list[dict[str, Any]], roster_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    by_name = {normalize_entity_name(row['full_name']): row for row in main_rows}
    missing_from_main: list[str] = []
    for row in roster_rows:
        key = normalize_entity_name(row['full_name'])
        if key in by_name:
            existing = by_name[key]
            existing['source_player_ids'] = {**row.get('source_player_ids', {}), **existing.get('source_player_ids', {})}
            existing['source_urls'] = sorted(set(existing.get('source_urls', []) + row.get('source_urls', [])))
            if not existing.get('team_name'):
                existing['team_name'] = row.get('team_name')
                existing['team_id'] = row.get('team_id')
            existing['alias_keys'] = sorted(set(existing.get('alias_keys', []) + row.get('alias_keys', [])))
        else:
            by_name[key] = row
            missing_from_main.append(row['full_name'])
    return list(by_name.values()), sorted(set(missing_from_main))


def _validate_directory(players: list[dict[str, Any]], roster_rows: list[dict[str, Any]], missing_from_main: list[str]) -> dict[str, Any]:
    duplicate_names = sorted({p['full_name'] for p in players if sum(1 for x in players if x['normalized_name'] == p['normalized_name']) > 1})
    roster_by_team: dict[str, int] = {}
    dir_by_team: dict[str, int] = {}
    roster_names = {normalize_entity_name(p['full_name']) for p in roster_rows}
    for row in roster_rows:
        roster_by_team[row.get('team_name') or 'Unknown'] = roster_by_team.get(row.get('team_name') or 'Unknown', 0) + 1
    for row in players:
        dir_by_team[row.get('team_name') or 'Unknown'] = dir_by_team.get(row.get('team_name') or 'Unknown', 0) + 1
    suspicious = []
    for team_name, roster_count in roster_by_team.items():
        directory_count = dir_by_team.get(team_name, 0)
        if abs(directory_count - roster_count) >= _MAX_ROSTER_SIZE_WARNING_DELTA:
            suspicious.append({'team': team_name, 'roster_count': roster_count, 'directory_count': directory_count})

    missing_from_rosters = sorted([p['full_name'] for p in players if normalize_entity_name(p['full_name']) not in roster_names])
    missing_team = sorted([p['full_name'] for p in players if not p.get('team_id') or not p.get('team_name')])
    severe = len(players) < _MIN_EXPECTED_NBA_PLAYERS or len(suspicious) >= 8
    return {
        'total_players_loaded': len(players),
        'players_missing_team_assignments': missing_team,
        'duplicate_or_conflicting_names': duplicate_names,
        'suspicious_roster_count_mismatches': suspicious,
        'players_in_team_rosters_missing_from_main_directory': missing_from_main,
        'players_in_directory_missing_from_all_team_rosters': missing_from_rosters,
        'severe_failure': severe,
    }


def refresh_nba_player_directory(*, urlopen: Any = request.urlopen) -> bool:
    try:
        league_payload = _fetch_json(_NBA_LEAGUE_DIRECTORY_URL, urlopen=urlopen)
        league_rows = _extract_nba_league_players(league_payload)
        if not league_rows:
            logger.warning('NBA directory refresh failed: league directory source returned no players')
            return False

        roster_rows: list[dict[str, Any]] = []
        teams_payload = _fetch_json(_ESPN_TEAMS_URL, urlopen=urlopen)
        for team_id, team_info in _extract_espn_teams(teams_payload).items():
            try:
                roster_payload = _fetch_json(_ESPN_TEAM_ROSTER_URL.format(team_id=team_id), urlopen=urlopen)
            except (error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                continue
            roster_rows.extend(_extract_espn_roster_players(team_id, roster_payload, team_info))

        merged_rows, missing_from_main = _merge_player_rows(league_rows, roster_rows)
        now = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
        players: list[dict[str, Any]] = []
        for row in merged_rows:
            full_name = row['full_name']
            players.append({
                'canonical_player_id': f"nba-{_slugify_player_id(full_name)}",
                'full_name': full_name,
                'normalized_name': row.get('normalized_name') or normalize_entity_name(full_name),
                'alias_keys': sorted(set(row.get('alias_keys', []))),
                'aliases': sorted(set(row.get('alias_keys', []))),
                'current_team_id': row.get('team_id'),
                'current_team_name': row.get('team_name'),
                'team_id': row.get('team_id'),
                'team_name': row.get('team_name'),
                'active_status': row.get('active_status') or 'active',
                'source_player_ids': {k: v for k, v in row.get('source_player_ids', {}).items() if v},
                'source_urls': sorted(set(row.get('source_urls', []))),
                'last_refreshed_at': now,
                'sport': 'NBA',
            })
        players.sort(key=lambda item: item['full_name'])

        validation_report = _validate_directory(players, roster_rows, missing_from_main)
        payload = {
            'version': 2,
            'generated_at': now,
            'last_refreshed_at': now,
            'source_urls': [_NBA_LEAGUE_DIRECTORY_URL, _ESPN_TEAMS_URL],
            'validation_report': validation_report,
            'players': players,
        }
        _NBA_DIRECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _NBA_DIRECTORY_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
        _player_directory.cache_clear()
        logger.info('NBA directory refresh complete players=%s severe_failure=%s', len(players), validation_report['severe_failure'])
        return True
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning('NBA directory refresh failed: %s', exc)
        return False


def _is_directory_stale(payload: dict[str, Any]) -> bool:
    timestamp = payload.get('last_refreshed_at') or payload.get('generated_at')
    if not isinstance(timestamp, str):
        return True
    try:
        refreshed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        return True
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc) - refreshed > _NBA_STALE_AFTER


def _maybe_refresh_nba_directory() -> None:
    now = monotonic()
    if now - _maybe_refresh_nba_directory._last_checked < _NBA_REFRESH_INTERVAL_SECONDS:  # type: ignore[attr-defined]
        return
    _maybe_refresh_nba_directory._last_checked = now  # type: ignore[attr-defined]
    refresh_nba_player_directory()


_maybe_refresh_nba_directory._last_checked = 0.0  # type: ignore[attr-defined]


def nba_identity_metadata() -> dict[str, str | None]:
    if NBA_PLAYERS_CACHE_PATH.exists():
        try:
            payload = json.loads(NBA_PLAYERS_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list) and payload:
            first = payload[0] if isinstance(payload[0], dict) else {}
            return {
                'identity_source': str(first.get('source_site') or 'basketball-reference'),
                'identity_last_refreshed_at': str(first.get('last_refreshed_at') or '') or None,
            }
    if _NBA_DIRECTORY_PATH.exists():
        try:
            payload = json.loads(_NBA_DIRECTORY_PATH.read_text())
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            return {
                'identity_source': 'legacy-nba-directory',
                'identity_last_refreshed_at': str(payload.get('last_refreshed_at') or payload.get('generated_at') or '') or None,
            }
    return {'identity_source': None, 'identity_last_refreshed_at': None}


class NBAIdentityAdapter:
    sport = 'NBA'

    def load_teams(self) -> tuple[CanonicalTeamIdentity, ...]:
        if NBA_TEAMS_CACHE_PATH.exists():
            try:
                payload = json.loads(NBA_TEAMS_CACHE_PATH.read_text())
            except json.JSONDecodeError:
                payload = []
            parsed: list[CanonicalTeamIdentity] = []
            for row in payload if isinstance(payload, list) else []:
                if not isinstance(row, dict):
                    continue
                full_name = str(row.get('full_team_name') or '').strip()
                canonical_team_id = str(row.get('canonical_team_id') or '').strip()
                if not full_name or not canonical_team_id:
                    continue
                parsed.append(
                    CanonicalTeamIdentity(
                        sport='NBA',
                        canonical_team_id=canonical_team_id,
                        source_team_ids={},
                        full_team_name=full_name,
                        normalized_team_name=normalize_team_name(full_name),
                        abbreviations=tuple(str(item) for item in row.get('abbreviations', []) if str(item).strip()),
                        aliases=tuple(str(item) for item in row.get('aliases', []) if str(item).strip()),
                    )
                )
            return tuple(parsed)

        players = self.load_players()
        seen: dict[str, CanonicalTeamIdentity] = {}
        for p in players:
            if not p.team_id or not p.team_name:
                continue
            if p.team_id in seen:
                continue
            seen[p.team_id] = CanonicalTeamIdentity(
                sport='NBA',
                canonical_team_id=p.team_id,
                source_team_ids={},
                full_team_name=p.team_name,
                normalized_team_name=normalize_team_name(p.team_name),
                abbreviations=(),
                aliases=(),
            )
        return tuple(seen.values())

    def load_players(self) -> tuple[CanonicalPlayerIdentity, ...]:
        if NBA_PLAYERS_CACHE_PATH.exists():
            try:
                payload = json.loads(NBA_PLAYERS_CACHE_PATH.read_text())
            except json.JSONDecodeError:
                payload = []
            parsed: list[CanonicalPlayerIdentity] = []
            for row in payload if isinstance(payload, list) else []:
                if not isinstance(row, dict):
                    continue
                full_name = str(row.get('full_name') or '').strip()
                if not full_name:
                    continue
                current_team_name = str(row.get('current_team_name') or '').strip()
                current_team_abbr = str(row.get('current_team_abbr') or '').strip()
                parsed.append(
                    CanonicalPlayerIdentity(
                        sport='NBA',
                        canonical_player_id=str(row.get('canonical_player_id') or f"nba-{_slugify_player_id(full_name)}"),
                        source_player_ids={},
                        full_name=full_name,
                        normalized_name=normalize_entity_name(str(row.get('normalized_name') or full_name)),
                        alternate_names=tuple(str(alias).strip() for alias in row.get('alias_keys', []) if str(alias).strip()),
                        team_id=(f'nba-team-{current_team_abbr.lower()}' if current_team_abbr else None),
                        team_name=(current_team_name or None),
                        active_status=str(row.get('active_status') or 'unknown'),
                        aliases=tuple(sorted(generate_player_aliases(row))),
                        normalized_aliases=tuple(sorted({normalize_person_name(alias) for alias in generate_player_aliases(row)})),
                    )
                )
            return tuple(parsed)

        _maybe_refresh_nba_directory()
        if not _NBA_DIRECTORY_PATH.exists():
            logger.warning('NBA directory file missing; identity resolution will be incomplete')
            return ()
        payload = json.loads(_NBA_DIRECTORY_PATH.read_text())
        players = payload.get('players') if isinstance(payload, dict) else []
        if not isinstance(players, list):
            return ()

        validation = payload.get('validation_report', {}) if isinstance(payload, dict) else {}
        has_refresh_metadata = isinstance(payload, dict) and isinstance(payload.get('last_refreshed_at') or payload.get('generated_at'), str)
        stale = _is_directory_stale(payload) if has_refresh_metadata else False
        severe_failure = bool(validation.get('severe_failure')) if isinstance(validation, dict) else False
        total_players = validation.get('total_players_loaded') if isinstance(validation, dict) else None
        incomplete = isinstance(total_players, int) and total_players < _MIN_EXPECTED_NBA_PLAYERS
        unreliable = stale or severe_failure or incomplete
        if unreliable:
            logger.warning(
                'NBA directory is stale or incomplete; team assignments considered unsafe stale=%s severe=%s total=%s',
                stale,
                severe_failure,
                len(players),
            )

        parsed: list[CanonicalPlayerIdentity] = []
        for row in players:
            if not isinstance(row, dict):
                continue
            full_name = str(row.get('full_name') or '').strip()
            if not full_name:
                continue
            aliases = tuple(str(alias).strip() for alias in row.get('alias_keys', row.get('aliases', [])) if str(alias).strip())
            canonical_player_id = str(row.get('canonical_player_id') or f"nba-{_slugify_player_id(full_name)}")
            source_ids = row.get('source_player_ids')
            team_id = row.get('current_team_id', row.get('team_id'))
            team_name = row.get('current_team_name', row.get('team_name'))
            parsed.append(
                CanonicalPlayerIdentity(
                    sport='NBA',
                    canonical_player_id=canonical_player_id,
                    source_player_ids=source_ids if isinstance(source_ids, dict) else {},
                    full_name=full_name,
                    normalized_name=normalize_entity_name(str(row.get('normalized_name') or full_name)),
                    alternate_names=aliases,
                    team_id=(str(team_id) if team_id and not unreliable else None),
                    team_name=(str(team_name) if team_name and not unreliable else None),
                    active_status=str(row.get('active_status') or 'active'),
                    aliases=tuple(sorted(generate_player_aliases({'full_name': full_name, 'aliases': aliases}))),
                    normalized_aliases=tuple(sorted({normalize_person_name(alias) for alias in generate_player_aliases({'full_name': full_name, 'aliases': aliases})})),
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
        for alias in (p.full_name, *p.alternate_names, *p.aliases, *p.normalized_aliases):
            for normalized in _lookup_keys(alias):
                bucket = by_name.setdefault(normalized, [])
                if all(existing.canonical_player_id != p.canonical_player_id for existing in bucket):
                    bucket.append(p)
    return by_id, by_name


def resolve_player_identity(player_name: str | None, sport: SportCode = 'NBA') -> PlayerResolutionResult:
    metadata = nba_identity_metadata() if sport == 'NBA' else {'identity_source': None, 'identity_last_refreshed_at': None}
    if not player_name:
        return PlayerResolutionResult(
            sport=sport,
            resolved_player_name=None,
            resolved_player_id=None,
            resolved_team=None,
            confidence=0.0,
            ambiguity_reason='player not found in sport directory',
            identity_source=metadata['identity_source'],
            identity_last_refreshed_at=metadata['identity_last_refreshed_at'],
            confidence_level='LOW',
        )

    normalized = normalize_entity_name(player_name)
    by_id, by_name = _player_directory(sport)
    direct = by_name.get(normalized, [])
    if len(direct) == 1:
        p = direct[0]
        if normalized == p.normalized_name:
            return PlayerResolutionResult(sport, p.full_name, p.canonical_player_id, p.team_name, 1.0, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='canonical', confidence_level='HIGH')
        if player_name in p.aliases:
            return PlayerResolutionResult(sport, p.full_name, p.canonical_player_id, p.team_name, 0.98, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='alias', confidence_level='HIGH')
        if _is_initials_or_surname_form(player_name, p.full_name):
            return PlayerResolutionResult(sport, None, None, None, 0.65, ambiguity_reason='player identity ambiguous', candidate_players=(p.full_name,), identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='ambiguous', confidence_level='LOW')
        return PlayerResolutionResult(sport, p.full_name, p.canonical_player_id, p.team_name, 0.9, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='normalized', confidence_level='MEDIUM')
    if len(direct) > 1:
        names = tuple(sorted(item.full_name for item in direct))
        return PlayerResolutionResult(sport, None, None, None, 0.5, ambiguity_reason='player identity ambiguous', candidate_players=names, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='ambiguous', confidence_level='LOW')

    # Safe single-token fallback using directory names.
    # Phase 1: unique surname hit (preferred).
    # Phase 2: unique first-name hit; if there are multiple, choose deterministic top candidate
    # only for common sportsbook shorthand (e.g., "Luka") with reduced confidence.
    parts = [part for part in normalized.split() if part]
    if sport == 'NBA' and len(parts) == 1:
        token = parts[0]
        surname_matches: list[CanonicalPlayerIdentity] = []
        first_matches: list[CanonicalPlayerIdentity] = []
        for player in by_id.values():
            name_parts = [part for part in player.normalized_name.split() if part]
            if len(name_parts) < 2:
                continue
            if player.active_status.lower() not in {'active', 'a', '1', 'true'}:
                continue
            if token == name_parts[-1]:
                surname_matches.append(player)
            elif token == name_parts[0]:
                first_matches.append(player)

        if len(surname_matches) == 1:
            pick = surname_matches[0]
            return PlayerResolutionResult(
                sport,
                pick.full_name,
                pick.canonical_player_id,
                pick.team_name,
                0.9,
                identity_source=metadata['identity_source'],
                identity_last_refreshed_at=metadata['identity_last_refreshed_at'],
                match_method='single_token_shorthand',
                confidence_level='MEDIUM',
            )
        if len(surname_matches) > 1:
            names = tuple(sorted(player.full_name for player in surname_matches[:5]))
            return PlayerResolutionResult(
                sport,
                None,
                None,
                None,
                0.55,
                ambiguity_reason='player identity ambiguous',
                candidate_players=names,
                identity_source=metadata['identity_source'],
                identity_last_refreshed_at=metadata['identity_last_refreshed_at'],
                match_method='ambiguous',
                confidence_level='LOW',
            )

        if len(first_matches) == 1:
            pick = first_matches[0]
            return PlayerResolutionResult(
                sport,
                pick.full_name,
                pick.canonical_player_id,
                pick.team_name,
                0.82,
                identity_source=metadata['identity_source'],
                identity_last_refreshed_at=metadata['identity_last_refreshed_at'],
                match_method='single_token_first_name',
                confidence_level='MEDIUM',
            )
        if len(first_matches) > 1 and len(token) >= 4:
            pick = sorted(first_matches, key=lambda item: item.full_name)[0]
            return PlayerResolutionResult(
                sport,
                pick.full_name,
                pick.canonical_player_id,
                pick.team_name,
                0.76,
                identity_source=metadata['identity_source'],
                identity_last_refreshed_at=metadata['identity_last_refreshed_at'],
                match_method='single_token_first_name_heuristic',
                confidence_level='MEDIUM',
            )

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
        return PlayerResolutionResult(sport, None, None, None, 0.0, ambiguity_reason='player not found in sport directory', identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], confidence_level='LOW')
    if ranked[0][0] < 0.86:
        suggestions = tuple(item[1].full_name for item in ranked[:3])
        return PlayerResolutionResult(sport, None, None, None, round(ranked[0][0], 2), ambiguity_reason='player not found in sport directory', candidate_players=suggestions, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], confidence_level='LOW')
    if len(ranked) > 1 and (ranked[0][0] - ranked[1][0]) < 0.05:
        names = tuple(item[1].full_name for item in ranked[:3])
        return PlayerResolutionResult(sport, None, None, None, round(ranked[0][0], 2), ambiguity_reason='player identity ambiguous', candidate_players=names, identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='ambiguous', confidence_level='LOW')
    pick = ranked[0][1]
    return PlayerResolutionResult(sport, pick.full_name, pick.canonical_player_id, pick.team_name, round(ranked[0][0], 2), identity_source=metadata['identity_source'], identity_last_refreshed_at=metadata['identity_last_refreshed_at'], match_method='normalized', confidence_level='MEDIUM')


def resolve_team_name(team_id: str | None, sport: SportCode = 'NBA') -> str | None:
    if not team_id:
        return None
    adapter = get_sport_adapters().get(sport)
    if not adapter:
        return None
    return next((team.full_team_name for team in adapter.load_teams() if team.canonical_team_id == team_id), None)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path

from ..identity_resolution import normalize_entity_name
from ..providers.base import EventInfo, ResultsProvider
from ..providers.factory import get_results_provider

_PLAYERS_CACHE_PATH = Path(__file__).resolve().parents[2] / 'data' / 'nba_players.json'
_TEAMS_CACHE_PATH = Path(__file__).resolve().parents[2] / 'data' / 'nba_teams.json'


@dataclass(frozen=True)
class Game:
    event_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime

    @property
    def label(self) -> str:
        return f'{self.away_team} @ {self.home_team}'


@lru_cache(maxsize=1)
def _players_cache() -> tuple[dict[str, object], ...]:
    if not _PLAYERS_CACHE_PATH.exists():
        return ()
    try:
        payload = json.loads(_PLAYERS_CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(row for row in payload if isinstance(row, dict))


@lru_cache(maxsize=1)
def _team_tokens() -> dict[str, set[str]]:
    if not _TEAMS_CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(_TEAMS_CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return {}
    team_lookup: dict[str, set[str]] = {}
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict):
            continue
        canonical_team_id = str(row.get('canonical_team_id') or '').strip()
        if not canonical_team_id:
            continue
        tokens = {
            str(row.get('full_team_name') or '').strip(),
            *(str(item).strip() for item in row.get('abbreviations', []) or []),
            *(str(item).strip() for item in row.get('aliases', []) or []),
        }
        team_lookup[canonical_team_id] = {token for token in tokens if token}
    return team_lookup


def _event_matches_date(event: EventInfo, target_date: date_cls) -> bool:
    if event.start_time.date() == target_date:
        return True
    if event.start_time.tzinfo is not None:
        return (event.start_time - timedelta(hours=8)).date() == target_date
    return False


def _resolve_player_row(player_name: str) -> dict[str, object] | None:
    normalized = normalize_entity_name(player_name)
    if not normalized:
        return None
    matches: list[dict[str, object]] = []
    for row in _players_cache():
        row_keys = {
            normalize_entity_name(str(row.get('full_name') or '')),
            normalize_entity_name(str(row.get('normalized_name') or '')),
            *(normalize_entity_name(str(alias)) for alias in (row.get('alias_keys') or [])),
        }
        if normalized in row_keys:
            matches.append(row)
    if len(matches) == 1:
        return matches[0]
    return None


def _candidate_team_tokens(player_row: dict[str, object]) -> list[str]:
    tokens: set[str] = set()
    canonical_team_id = str(player_row.get('team_id') or '').strip()
    team_name = str(player_row.get('team_name') or player_row.get('current_team_name') or '').strip()
    team_abbr = str(player_row.get('current_team_abbr') or '').strip()
    if team_name:
        tokens.add(team_name)
    if team_abbr:
        tokens.add(team_abbr)
    tokens.update(_team_tokens().get(canonical_team_id, set()))
    return sorted(tokens)


def resolve_player_game(player_name: str, date: str, provider: ResultsProvider | None = None) -> Game | None:
    player_row = _resolve_player_row(player_name)
    if not player_row:
        return None
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return None

    candidate_tokens = _candidate_team_tokens(player_row)
    if not candidate_tokens:
        return None

    provider = provider or get_results_provider()
    anchor = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)

    seen: dict[str, EventInfo] = {}
    for token in candidate_tokens:
        resolver = getattr(provider, 'resolve_team_event_candidates', None)
        if not callable(resolver):
            continue
        try:
            events = resolver(token, anchor, include_historical=True)
        except TypeError:
            events = resolver(token, anchor)
        for event in events or []:
            if _event_matches_date(event, target_date):
                seen[event.event_id] = event

    if len(seen) != 1:
        return None

    event = next(iter(seen.values()))
    return Game(
        event_id=event.event_id,
        sport=event.sport,
        home_team=event.home_team,
        away_team=event.away_team,
        start_time=event.start_time,
    )

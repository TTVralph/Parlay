from __future__ import annotations

from typing import Any

from app.services.event_snapshot import EventSnapshot
from app.services.player_alias_index import resolve_snapshot_player


STAT_ALIASES: dict[str, set[str]] = {
    'PTS': {'PTS', 'points'},
    'REB': {'REB', 'rebounds'},
    'AST': {'AST', 'assists'},
    '3PM': {'3PM', '3PT', '3PTM', '3PT FG', '3PT made', '3PT Made', 'threes', 'threes made'},
    'STL': {'STL', 'steals'},
    'BLK': {'BLK', 'blocks'},
    'TOV': {'TOV', 'TO', 'turnovers'},
    'H': {'H', 'hits'},
    'SO': {'SO', 'K', 'strikeouts'},
    'TB': {'TB', 'total_bases'},
    '1B': {'1B', 'singles'},
    '2B': {'2B', 'doubles'},
    '3B': {'3B', 'triples'},
    'HR': {'HR', 'home_runs'},
    'PASS_YDS': {'PASS_YDS', 'pass_yds', 'passing_yards'},
    'RUSH_YDS': {'RUSH_YDS', 'rush_yds', 'rushing_yards'},
    'REC_YDS': {'REC_YDS', 'rec_yds', 'receiving_yards'},
    'SOG': {'SOG', 'shots_on_goal'},
    'NHL_PTS': {'PTS', 'points'},
    'SHOTS': {'SHOTS', 'shots'},
    'SOT': {'SOT', 'shots_on_target'},
}


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_snapshot_player_entry(snapshot: EventSnapshot, player_id: str | None, player_name: str | None) -> dict[str, Any] | None:
    return resolve_snapshot_player(
        player_entries=snapshot.normalized_player_stats.values(),
        player_id=player_id,
        player_name=player_name,
    ).entry


def get_player_stat(snapshot: EventSnapshot, player_id: str | None, stat_key: str, *, player_name: str | None = None) -> float | None:
    entry = get_snapshot_player_entry(snapshot, player_id=player_id, player_name=player_name)
    if not entry:
        return None
    stats = entry.get('stats') or {}
    for alias in STAT_ALIASES.get(stat_key, {stat_key}):
        value = _coerce_float(stats.get(alias))
        if value is not None:
            return value
    return None


def get_team_stat(snapshot: EventSnapshot, team_id: str | None, stat_key: str) -> float | None:
    if not team_id:
        return None
    team_entry = (snapshot.normalized_team_map or {}).get(team_id)
    if not team_entry:
        return None
    stats = team_entry.get('stats') or {}
    for alias in STAT_ALIASES.get(stat_key, {stat_key}):
        value = _coerce_float(stats.get(alias))
        if value is not None:
            return value
    return None


def compute_combo_stat(snapshot: EventSnapshot, player_id: str | None, components: tuple[str, ...], *, player_name: str | None = None) -> float | None:
    values: list[float] = []
    for component in components:
        value = get_player_stat(snapshot, player_id=player_id, stat_key=component, player_name=player_name)
        if value is None:
            return None
        values.append(value)
    return float(sum(values))

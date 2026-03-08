from __future__ import annotations

import json
from typing import Any


ALLSPORTS_PROVIDER_CAPABILITIES: dict[str, bool] = {
    'supports_game_results': True,
    'supports_team_stats': True,
    'supports_player_props': False,
    'supports_live_status': True,
}


class StatsPayloadShapeError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _team_name(team_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(team_payload, dict):
        return None
    return team_payload.get('name') or team_payload.get('shortName') or team_payload.get('slug')


def _non_empty_dict_count(items: list[Any]) -> int:
    return sum(1 for item in items if isinstance(item, dict) and item)


def _coerce_root_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
        raise StatsPayloadShapeError(
            code='stats_payload_list_without_object',
            message='Statistics payload list did not contain an object to normalize',
            details={'list_length': len(payload)},
        )
    raise StatsPayloadShapeError(
        code='stats_payload_invalid_type',
        message='Statistics payload must be a dict or list',
        details={'top_level_type': type(payload).__name__},
    )


def summarize_stats_payload_shape(payload: Any) -> dict[str, Any]:
    root = payload if isinstance(payload, dict) else None
    team_stats = root.get('statistics') if root else None
    players = root.get('players') if root else None

    team_stats_list = team_stats if isinstance(team_stats, list) else []
    players_list = players if isinstance(players, list) else []

    player_block_count = _non_empty_dict_count(players_list)
    nested_player_rows = 0
    for block in players_list:
        if not isinstance(block, dict):
            continue
        block_players = block.get('players')
        if isinstance(block_players, list):
            nested_player_rows += len([row for row in block_players if isinstance(row, dict) and row])

    return {
        'topLevelType': type(payload).__name__,
        'teamStatsCount': len(team_stats_list),
        'playerBlockCount': player_block_count,
        'playerRowCount': nested_player_rows,
        'hasPlayerStats': player_block_count > 0 and nested_player_rows > 0,
        'topLevelKeys': sorted(root.keys()) if root else [],
        'listLength': len(payload) if isinstance(payload, list) else None,
    }


def safe_payload_preview(payload: Any, max_chars: int = 600) -> str:
    def _sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, nested_value in value.items():
                if any(token in key.lower() for token in ('key', 'token', 'secret', 'authorization')):
                    out[key] = '[redacted]'
                else:
                    out[key] = _sanitize(nested_value)
            return out
        if isinstance(value, list):
            return [_sanitize(item) for item in value[:3]]
        if isinstance(value, str):
            return value[:200]
        return value

    text = json.dumps(_sanitize(payload), ensure_ascii=False, default=str)
    return f'{text[:max_chars]}…' if len(text) > max_chars else text


def normalize_game(event: dict[str, Any]) -> dict[str, Any]:
    home = event.get('homeTeam') if isinstance(event, dict) else None
    away = event.get('awayTeam') if isinstance(event, dict) else None
    status = event.get('status') if isinstance(event, dict) else None
    return {
        'id': str(event.get('id')) if isinstance(event, dict) and event.get('id') is not None else None,
        'homeTeam': _team_name(home),
        'awayTeam': _team_name(away),
        'status': status.get('type') if isinstance(status, dict) else status,
        'startTime': event.get('startTimestamp') if isinstance(event, dict) else None,
    }


def normalize_games(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [g for g in (normalize_game(event) for event in events) if g.get('id')]


def normalize_match_stats(match_id: str, payload: Any) -> dict[str, Any]:
    root_payload = _coerce_root_payload(payload)

    event = root_payload.get('event')
    if not isinstance(event, dict):
        raise StatsPayloadShapeError(
            code='stats_payload_missing_event',
            message='Statistics payload missing event object',
            details={'top_level_keys': sorted(root_payload.keys())},
        )

    team_stats = root_payload.get('statistics')
    if team_stats is None:
        team_stats = []
    if not isinstance(team_stats, list):
        raise StatsPayloadShapeError(
            code='stats_payload_invalid_statistics',
            message='Statistics payload field "statistics" must be a list when present',
            details={'statistics_type': type(team_stats).__name__},
        )

    player_stats = root_payload.get('players')
    if player_stats is None:
        player_stats = []
    if not isinstance(player_stats, list):
        raise StatsPayloadShapeError(
            code='stats_payload_invalid_players',
            message='Statistics payload field "players" must be a list when present',
            details={'players_type': type(player_stats).__name__},
        )

    home = event.get('homeTeam') if isinstance(event, dict) else None
    away = event.get('awayTeam') if isinstance(event, dict) else None

    payload_shape = summarize_stats_payload_shape(root_payload)

    return {
        'matchId': str(event.get('id') or match_id),
        'homeTeam': _team_name(home),
        'awayTeam': _team_name(away),
        'teamStats': [row for row in team_stats if isinstance(row, dict)],
        'playerStats': [row for row in player_stats if isinstance(row, dict)] if payload_shape['hasPlayerStats'] else None,
    }

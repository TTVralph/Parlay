from __future__ import annotations

from typing import Any


ALLSPORTS_PROVIDER_CAPABILITIES: dict[str, bool] = {
    'supports_game_results': True,
    'supports_team_stats': True,
    'supports_player_props': False,
    'supports_live_status': True,
}


def _team_name(team_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(team_payload, dict):
        return None
    return team_payload.get('name') or team_payload.get('shortName') or team_payload.get('slug')


def _non_empty_dict_count(items: list[Any]) -> int:
    return sum(1 for item in items if isinstance(item, dict) and item)


def summarize_stats_payload_shape(payload: dict[str, Any]) -> dict[str, Any]:
    team_stats = payload.get('statistics') if isinstance(payload, dict) else None
    players = payload.get('players') if isinstance(payload, dict) else None

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
        'teamStatsCount': len(team_stats_list),
        'playerBlockCount': player_block_count,
        'playerRowCount': nested_player_rows,
        'hasPlayerStats': player_block_count > 0 and nested_player_rows > 0,
        'topLevelKeys': sorted(payload.keys()) if isinstance(payload, dict) else [],
    }


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


def normalize_match_stats(match_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get('event') if isinstance(payload, dict) else {}
    home = event.get('homeTeam') if isinstance(event, dict) else None
    away = event.get('awayTeam') if isinstance(event, dict) else None

    team_stats = payload.get('statistics')
    if not isinstance(team_stats, list):
        team_stats = []

    player_stats = payload.get('players')
    if not isinstance(player_stats, list):
        player_stats = []

    payload_shape = summarize_stats_payload_shape(payload)

    return {
        'matchId': str(event.get('id') or match_id),
        'homeTeam': _team_name(home),
        'awayTeam': _team_name(away),
        'teamStats': team_stats,
        'playerStats': player_stats if payload_shape['hasPlayerStats'] else None,
    }

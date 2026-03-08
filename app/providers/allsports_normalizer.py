from __future__ import annotations

from typing import Any


def _team_name(team_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(team_payload, dict):
        return None
    return team_payload.get('name') or team_payload.get('shortName') or team_payload.get('slug')


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

    return {
        'matchId': str(event.get('id') or match_id),
        'homeTeam': _team_name(home),
        'awayTeam': _team_name(away),
        'teamStats': team_stats,
        'playerStats': player_stats,
    }

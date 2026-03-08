from __future__ import annotations

from typing import Any


SPORTSAPIPRO_PROVIDER_CAPABILITIES: dict[str, bool] = {
    'supports_game_results': True,
    'supports_team_stats': True,
    'supports_player_props': True,
    'supports_live_status': True,
}


SPORTSAPIPRO_STAT_TYPE_MAP: dict[int, str | tuple[str, str]] = {
    11: 'minutes',
    92: 'points',
    25: 'rebounds',
    26: 'assists',
    27: 'steals',
    29: 'blocks',
    88: ('fieldGoalsMade', 'fieldGoalsAttempted'),
    17: ('threePointersMade', 'threePointersAttempted'),
    21: ('freeThrowsMade', 'freeThrowsAttempted'),
    23: 'offensiveRebounds',
    24: 'defensiveRebounds',
    28: 'turnovers',
    30: 'personalFouls',
    31: 'plusMinus',
}


class SportsAPIProNormalizeError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _stat_defaults() -> dict[str, int]:
    return {
        'minutes': 0,
        'points': 0,
        'rebounds': 0,
        'assists': 0,
        'steals': 0,
        'blocks': 0,
        'fieldGoalsMade': 0,
        'fieldGoalsAttempted': 0,
        'threePointersMade': 0,
        'threePointersAttempted': 0,
        'freeThrowsMade': 0,
        'freeThrowsAttempted': 0,
        'offensiveRebounds': 0,
        'defensiveRebounds': 0,
        'turnovers': 0,
        'personalFouls': 0,
        'plusMinus': 0,
    }


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0
        try:
            return int(float(raw))
        except ValueError:
            return 0
    return 0


def _parse_ratio(value: Any) -> tuple[int, int]:
    if isinstance(value, str) and '/' in value:
        made_raw, attempted_raw = value.split('/', 1)
        return (_to_int(made_raw), _to_int(attempted_raw))
    if isinstance(value, (int, float)):
        made = int(value)
        return (made, made)
    return (0, 0)


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ('rows', 'games', 'results', 'events', 'data'):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def normalize_game(row: dict[str, Any]) -> dict[str, Any]:
    home_team = row.get('homeTeam') if isinstance(row.get('homeTeam'), dict) else row.get('home')
    away_team = row.get('awayTeam') if isinstance(row.get('awayTeam'), dict) else row.get('away')
    competition = row.get('competition') if isinstance(row.get('competition'), dict) else None

    status = row.get('status')
    if isinstance(status, dict):
        status = status.get('type') or status.get('description') or status.get('name')

    return {
        'id': str(row.get('id') or row.get('gameId') or row.get('eventId') or ''),
        'competitionId': str(competition.get('id')) if competition and competition.get('id') is not None else None,
        'competitionName': competition.get('name') if competition else None,
        'homeTeam': (home_team or {}).get('name') if isinstance(home_team, dict) else row.get('homeTeamName'),
        'awayTeam': (away_team or {}).get('name') if isinstance(away_team, dict) else row.get('awayTeamName'),
        'homeTeamId': str((home_team or {}).get('id')) if isinstance(home_team, dict) and (home_team or {}).get('id') is not None else None,
        'awayTeamId': str((away_team or {}).get('id')) if isinstance(away_team, dict) and (away_team or {}).get('id') is not None else None,
        'status': status,
        'startTime': row.get('startTime') or row.get('startDate') or row.get('date'),
    }


def normalize_games(payload: Any) -> list[dict[str, Any]]:
    normalized = [normalize_game(row) for row in _extract_rows(payload)]
    return [row for row in normalized if row.get('id')]


def _header_type(header: dict[str, Any]) -> int | None:
    return _to_int(header.get('type') if isinstance(header, dict) else None) or None


def _decode_stats(headers: list[dict[str, Any]], values: list[Any]) -> dict[str, int]:
    stats = _stat_defaults()
    for idx, header in enumerate(headers):
        stat_type = _header_type(header)
        if stat_type is None or stat_type not in SPORTSAPIPRO_STAT_TYPE_MAP:
            continue
        value = values[idx] if idx < len(values) else None
        mapped_field = SPORTSAPIPRO_STAT_TYPE_MAP[stat_type]
        if isinstance(mapped_field, tuple):
            made, attempted = _parse_ratio(value)
            stats[mapped_field[0]] = made
            stats[mapped_field[1]] = attempted
        else:
            stats[mapped_field] = _to_int(value)
    return stats


def normalize_athlete_game_logs(athlete_id: str, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise SportsAPIProNormalizeError(
            code='sportsapipro_logs_invalid_type',
            message='Athlete games payload must be an object',
            details={'top_level_type': type(payload).__name__},
        )

    headers = payload.get('headers')
    rows = payload.get('rows')
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise SportsAPIProNormalizeError(
            code='sportsapipro_logs_missing_headers_or_rows',
            message='Athlete games payload must include headers and rows arrays',
            details={'headers_type': type(headers).__name__, 'rows_type': type(rows).__name__},
        )

    clean_headers = [header for header in headers if isinstance(header, dict)]
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        opponent = row.get('opponent') if isinstance(row.get('opponent'), dict) else None
        competition = row.get('competition') if isinstance(row.get('competition'), dict) else None
        values = row.get('values') if isinstance(row.get('values'), list) else []
        output.append({
            'athleteId': str(athlete_id),
            'gameId': str(row.get('gameId')) if row.get('gameId') is not None else None,
            'date': row.get('date') or row.get('gameDate') or row.get('startTime'),
            'opponentId': str(opponent.get('id')) if opponent and opponent.get('id') is not None else None,
            'opponentName': opponent.get('name') if opponent else None,
            'competitionId': str(competition.get('id')) if competition and competition.get('id') is not None else None,
            'competitionName': competition.get('name') if competition else None,
            'stats': _decode_stats(clean_headers, values),
        })
    return output

from __future__ import annotations

from typing import Any


SPORTSAPIPRO_PROVIDER_CAPABILITIES: dict[str, bool] = {
    'supports_game_results': True,
    'supports_team_stats': True,
    'supports_player_props': True,
    'supports_live_status': True,
}


SPORTSAPIPRO_STAT_TYPE_MAP: dict[int, str | tuple[str, str]] = {
_STAT_TYPE_TO_FIELD: dict[int, str] = {
    11: 'minutes',
    92: 'points',
    25: 'rebounds',
    26: 'assists',
    27: 'steals',
    29: 'blocks',
    88: ('fieldGoalsMade', 'fieldGoalsAttempted'),
    17: ('threePointersMade', 'threePointersAttempted'),
    21: ('freeThrowsMade', 'freeThrowsAttempted'),
    88: 'fieldGoals',
    17: 'threePointers',
    21: 'freeThrows',
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
def _as_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ('id', 'athleteId', 'gameId', 'teamId', 'competitionId'):
            if value.get(key) is not None:
                return str(value.get(key))
    return _as_string(value)


def _extract_name(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ('name', 'shortName', 'displayName', 'title'):
            if value.get(key):
                return str(value.get(key))
    return _as_string(value)


def _extract_from_any(payload: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload and payload.get(key) is not None:
                return payload.get(key)
    return None


def _coerce_int(value: Any) -> int:
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
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _parse_ratio(value: Any) -> tuple[int, int]:
    if value is None:
        return (0, 0)
    text = str(value).strip()
    if '/' not in text:
        parsed = _coerce_int(text)
        return (parsed, 0)
    made_text, attempted_text = text.split('/', 1)
    return (_coerce_int(made_text), _coerce_int(attempted_text))


def _normalized_game(event: dict[str, Any]) -> dict[str, Any] | None:
    game_id = _extract_id(_extract_from_any(event, ('id', 'gameId')))
    if not game_id:
        return None

    competition = _extract_from_any(event, ('competition', 'league', 'tournament'))
    home = _extract_from_any(event, ('homeTeam', 'home', 'teamHome'))
    away = _extract_from_any(event, ('awayTeam', 'away', 'teamAway'))

    return {
        'id': game_id,
        'competitionId': _extract_id(_extract_from_any(event, ('competitionId',))) or _extract_id(competition),
        'competitionName': _extract_name(_extract_from_any(event, ('competitionName',))) or _extract_name(competition),
        'homeTeam': _extract_name(home),
        'awayTeam': _extract_name(away),
        'homeTeamId': _extract_id(home),
        'awayTeamId': _extract_id(away),
        'status': _as_string(_extract_from_any(event, ('status', 'gameStatus'))),
        'startTime': _as_string(_extract_from_any(event, ('startTime', 'startDate', 'date', 'scheduledAt'))),
    }


def normalize_games_payload(payload: Any) -> list[dict[str, Any]]:
    rows = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        possible_rows = _extract_from_any(payload, ('games', 'results', 'data', 'events'))
        if isinstance(possible_rows, list):
            rows = possible_rows
        else:
            rows = [payload]

    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = _normalized_game(row)
        if normalized:
            output.append(normalized)
    return output


def _extract_header_types(headers: Any) -> list[int | None]:
    if not isinstance(headers, list):
        return []
    output: list[int | None] = []
    for header in headers:
        if isinstance(header, dict):
            raw_type = _extract_from_any(header, ('type', 'statType', 'code', 'id'))
        else:
            raw_type = header
        try:
            output.append(int(raw_type))
        except (TypeError, ValueError):
            output.append(None)
    return output


def _extract_row_value(row: dict[str, Any], *keys: str) -> Any:
    return _extract_from_any(row, keys)


def _build_default_stats() -> dict[str, int]:
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


def _apply_stat_value(stats: dict[str, int], field: str, raw_value: Any) -> None:
    if field == 'fieldGoals':
        made, attempted = _parse_ratio(raw_value)
        stats['fieldGoalsMade'] = made
        stats['fieldGoalsAttempted'] = attempted
        return
    if field == 'threePointers':
        made, attempted = _parse_ratio(raw_value)
        stats['threePointersMade'] = made
        stats['threePointersAttempted'] = attempted
        return
    if field == 'freeThrows':
        made, attempted = _parse_ratio(raw_value)
        stats['freeThrowsMade'] = made
        stats['freeThrowsAttempted'] = attempted
        return
    if field in stats:
        stats[field] = _coerce_int(raw_value)


def normalize_athlete_games_payload(athlete_id: str, payload: Any) -> list[dict[str, Any]]:
    rows: list[Any] = []
    headers: Any = []
    if isinstance(payload, dict):
        rows = _extract_from_any(payload, ('rows', 'games', 'data', 'results')) or []
        headers = _extract_from_any(payload, ('headers', 'statHeaders', 'columns')) or []
    elif isinstance(payload, list):
        rows = payload

    if not isinstance(rows, list):
        rows = []

    header_types = _extract_header_types(headers)
    output: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        stats = _build_default_stats()
        values = _extract_row_value(row, 'values', 'stats', 'statValues')
        if isinstance(values, list):
            for idx, raw_value in enumerate(values):
                if idx >= len(header_types):
                    continue
                stat_type = header_types[idx]
                if stat_type is None:
                    continue
                field = _STAT_TYPE_TO_FIELD.get(stat_type)
                if not field:
                    continue
                _apply_stat_value(stats, field, raw_value)

        opponent = _extract_row_value(row, 'opponent', 'opponentTeam')
        competition = _extract_row_value(row, 'competition', 'league', 'tournament')
        game_id = _extract_id(_extract_row_value(row, 'gameId', 'id', 'eventId'))

        output.append(
            {
                'athleteId': str(athlete_id),
                'gameId': game_id,
                'date': _as_string(_extract_row_value(row, 'date', 'gameDate', 'startTime')),
                'opponentId': _extract_id(_extract_row_value(row, 'opponentId', 'opponentTeamId')) or _extract_id(opponent),
                'opponentName': _extract_name(_extract_row_value(row, 'opponentName')) or _extract_name(opponent),
                'competitionId': _extract_id(_extract_row_value(row, 'competitionId')) or _extract_id(competition),
                'competitionName': _extract_name(_extract_row_value(row, 'competitionName')) or _extract_name(competition),
                'stats': stats,
            }
        )

    return output

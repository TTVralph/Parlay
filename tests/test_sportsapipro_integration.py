from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.providers.sportsapipro_client import SportsAPIProClient, SportsAPIProError
from app.providers.sportsapipro_normalizer import normalize_athlete_game_logs


client = TestClient(main_module.app)


class _StubResponse:
    def __init__(self, status_code: int, payload=None, text: str = '') -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_missing_sportsapipro_key(monkeypatch) -> None:
    monkeypatch.delenv('SPORTSAPIPRO_KEY', raising=False)
    resp = client.get('/api/sportsapipro/games/current')
    assert resp.status_code == 500
    assert resp.json()['detail']['code'] == 'sportsapipro_missing_key'


def test_sportsapipro_auth_failure_maps_error(monkeypatch) -> None:
    monkeypatch.setenv('SPORTSAPIPRO_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, params=None, timeout: float = 15.0):
        return _StubResponse(401, payload={'message': 'unauthorized'})

    monkeypatch.setattr('app.providers.sportsapipro_client.httpx.get', _fake_get)
    resp = client.get('/api/sportsapipro/games/current')
    assert resp.status_code == 502
    assert resp.json()['detail']['code'] == 'sportsapipro_auth_error'


def test_games_results_normalizes_payload(monkeypatch) -> None:
    monkeypatch.setenv('SPORTSAPIPRO_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, params=None, timeout: float = 15.0):
        assert headers['x-api-key'] == 'test-key'
        assert '/games/results' in url
        return _StubResponse(200, payload={
            'rows': [
                {
                    'id': 100,
                    'competition': {'id': 10, 'name': 'NBA'},
                    'homeTeam': {'id': 1, 'name': 'Nuggets'},
                    'awayTeam': {'id': 2, 'name': 'Lakers'},
                    'status': {'type': 'finished'},
                    'startTime': '2026-03-08T00:00:00Z',
                }
            ]
        })

    monkeypatch.setattr('app.providers.sportsapipro_client.httpx.get', _fake_get)

    resp = client.get('/api/sportsapipro/games/results', params={'date': '2026-03-08'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['games'][0] == {
        'id': '100',
        'competitionId': '10',
        'competitionName': 'NBA',
        'homeTeam': 'Nuggets',
        'awayTeam': 'Lakers',
        'homeTeamId': '1',
        'awayTeamId': '2',
        'status': 'finished',
        'startTime': '2026-03-08T00:00:00Z',
    }


def test_athlete_logs_normalization_parses_ratios() -> None:
    payload = {
        'headers': [
            {'type': 11},
            {'type': 92},
            {'type': 25},
            {'type': 26},
            {'type': 17},
            {'type': 88},
            {'type': 21},
            {'type': 999},
        ],
        'rows': [
            {
                'gameId': 'g1',
                'date': '2026-03-08',
                'opponent': {'id': 44, 'name': 'Suns'},
                'competition': {'id': 3, 'name': 'NBA'},
                'values': ['35', '28', '11', '10', '2/10', '10/23', '2/6', 'x'],
            }
        ],
    }
    logs = normalize_athlete_game_logs('53646', payload)
    stats = logs[0]['stats']
    assert stats['minutes'] == 35
    assert stats['points'] == 28
    assert stats['rebounds'] == 11
    assert stats['assists'] == 10
    assert stats['threePointersMade'] == 2
    assert stats['threePointersAttempted'] == 10
    assert stats['fieldGoalsMade'] == 10
    assert stats['fieldGoalsAttempted'] == 23
    assert stats['freeThrowsMade'] == 2
    assert stats['freeThrowsAttempted'] == 6


def test_athlete_logs_normalization_handles_missing_values() -> None:
    payload = {
        'headers': [{'type': 92}, {'type': 88}, {'type': 17}, {'type': 21}],
        'rows': [{'values': [None, 'bad', '', '3/4']}],
    }
    logs = normalize_athlete_game_logs('53646', payload)
    stats = logs[0]['stats']
    assert stats['points'] == 0
    assert stats['fieldGoalsMade'] == 0
    assert stats['fieldGoalsAttempted'] == 0
    assert stats['threePointersMade'] == 0
    assert stats['threePointersAttempted'] == 0
    assert stats['freeThrowsMade'] == 3
    assert stats['freeThrowsAttempted'] == 4


def test_athlete_normalized_route_serializes(monkeypatch) -> None:
    monkeypatch.setenv('SPORTSAPIPRO_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, params=None, timeout: float = 15.0):
        return _StubResponse(200, payload={
            'headers': [{'type': 92}, {'type': 17}],
            'rows': [{'gameId': 1, 'date': '2026-03-08', 'values': ['22', '4/9']}],
        })

    monkeypatch.setattr('app.providers.sportsapipro_client.httpx.get', _fake_get)
    resp = client.get('/api/sportsapipro/athlete/53646/game-log-normalized')
    assert resp.status_code == 200
    body = resp.json()
    assert body['athleteId'] == '53646'
    assert body['logs'][0]['stats']['points'] == 22
    assert body['logs'][0]['stats']['threePointersAttempted'] == 9


def test_sportsapipro_client_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv('SPORTSAPIPRO_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, params=None, timeout: float = 15.0):
        return _StubResponse(200, payload=ValueError('bad json'))

    monkeypatch.setattr('app.providers.sportsapipro_client.httpx.get', _fake_get)
    api = SportsAPIProClient.from_env()
    try:
        api.get_games_current()
        assert False, 'expected SportsAPIProError'
    except SportsAPIProError as exc:
        assert exc.code == 'sportsapipro_invalid_json'


def test_provider_capabilities_includes_sportsapipro() -> None:
    resp = client.get('/api/providers/capabilities')
    assert resp.status_code == 200
    body = resp.json()
    assert body['providers']['sportsapipro'] == {
        'supports_game_results': True,
        'supports_team_stats': True,
        'supports_player_props': True,
        'supports_live_status': True,
    }

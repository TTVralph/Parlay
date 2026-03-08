from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

import app.main as main_module
from app.providers.allsports_client import AllSportsClient, AllSportsError


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


def test_games_endpoint_validates_date(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')
    resp = client.get('/api/allsports/games', params={'date': '03-08-2026'})
    assert resp.status_code == 400
    assert 'YYYY-MM-DD' in resp.json()['detail']


def test_games_endpoint_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv('RAPIDAPI_KEY', raising=False)
    resp = client.get('/api/allsports/games', params={'date': '2026-03-08'})
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'RAPIDAPI_KEY is not configured'


def test_games_endpoint_normalizes_payload(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        assert '/api/basketball/matches/8/3/2026' in url
        assert headers['x-rapidapi-host'] == 'allsportsapi2.p.rapidapi.com'
        return _StubResponse(200, payload={'events': [
            {
                'id': 123,
                'homeTeam': {'name': 'Lakers'},
                'awayTeam': {'name': 'Celtics'},
                'status': {'type': 'finished'},
                'startTimestamp': 1772937600,
            }
        ]})

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/games', params={'date': '2026-03-08'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['date'] == '2026-03-08'
    assert body['games'][0] == {
        'id': '123',
        'homeTeam': 'Lakers',
        'awayTeam': 'Celtics',
        'status': 'finished',
        'startTime': 1772937600,
    }


def test_match_stats_endpoint_handles_missing_match(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(404, payload={'message': 'not found'})

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/999/stats')
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Match not found'


def test_match_stats_endpoint_normalizes_payload(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload={
            'event': {
                'id': 555,
                'homeTeam': {'name': 'Nuggets'},
                'awayTeam': {'name': 'Suns'},
            },
            'statistics': [{'groupName': 'Team', 'items': []}],
            'players': [{'team': 'Nuggets', 'players': []}],
        })

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/555/stats')
    assert resp.status_code == 200
    body = resp.json()
    assert body['matchId'] == '555'
    assert body['homeTeam'] == 'Nuggets'
    assert body['awayTeam'] == 'Suns'
    assert isinstance(body['teamStats'], list)
    assert body['playerStats'] is None


def test_client_invalid_json_raises_error(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload=ValueError('bad json'))

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    client_instance = AllSportsClient.from_env()
    try:
        client_instance.get_games_by_date(date(2026, 3, 8))
        assert False, 'Expected AllSportsError'
    except AllSportsError as exc:
        assert 'invalid JSON' in exc.message


def test_match_stats_endpoint_populates_player_stats_when_present(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload={
            'event': {
                'id': 777,
                'homeTeam': {'name': 'Heat'},
                'awayTeam': {'name': 'Knicks'},
            },
            'statistics': [{'groupName': 'Team', 'items': []}],
            'players': [
                {'team': {'name': 'Heat'}, 'players': [{'name': 'A', 'points': 25}]},
            ],
        })

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/777/stats')
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body['playerStats'], list)
    assert len(body['playerStats']) == 1


def test_provider_capabilities_endpoint_returns_allsports_caps() -> None:
    resp = client.get('/api/providers/capabilities')
    assert resp.status_code == 200
    body = resp.json()
    assert body['providers']['allsports'] == {
        'supports_game_results': True,
        'supports_team_stats': True,
        'supports_player_props': False,
        'supports_live_status': True,
    }


def test_match_stats_debug_endpoint_returns_shape_summary(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload={
            'event': {'id': 555, 'homeTeam': {'name': 'Nuggets'}, 'awayTeam': {'name': 'Suns'}},
            'statistics': [{'groupName': 'Team', 'items': []}],
            'players': [{'team': 'Nuggets', 'players': []}],
        })

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/555/stats/debug')
    assert resp.status_code == 200
    body = resp.json()
    assert body['payloadShape']['teamStatsCount'] == 1
    assert body['payloadShape']['playerBlockCount'] == 1
    assert body['payloadShape']['playerRowCount'] == 0
    assert body['payloadShape']['hasPlayerStats'] is False
    assert body['normalizedPreview']['playerStatsPresent'] is False


def test_match_stats_endpoint_handles_list_payload(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload=[{
            'event': {'id': 321, 'homeTeam': {'name': 'Bulls'}, 'awayTeam': {'name': 'Pistons'}},
            'statistics': [{'groupName': 'Team', 'items': []}],
            'players': None,
        }])

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/321/stats')
    assert resp.status_code == 200
    body = resp.json()
    assert body['matchId'] == '321'
    assert body['teamStats'] == [{'groupName': 'Team', 'items': []}]
    assert body['playerStats'] is None


def test_match_stats_endpoint_returns_structured_error_when_nested_fields_missing(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload={'statistics': []})

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/888/stats')
    assert resp.status_code == 422
    detail = resp.json()['detail']
    assert detail['code'] == 'stats_payload_missing_event'
    assert 'top_level_keys' in detail['details']


def test_match_stats_endpoint_handles_null_sections(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload={
            'event': {'id': 901, 'homeTeam': {'name': 'Spurs'}, 'awayTeam': {'name': 'Mavs'}},
            'statistics': None,
            'players': None,
        })

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/901/stats')
    assert resp.status_code == 200
    body = resp.json()
    assert body['teamStats'] == []
    assert body['playerStats'] is None


def test_match_stats_debug_endpoint_never_crashes_on_unexpected_shape(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload=['unexpected'])

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/500/stats/debug')
    assert resp.status_code == 200
    body = resp.json()
    assert body['topLevelType'] == 'list'
    assert body['normalizationError']['code'] == 'stats_payload_list_without_object'


def test_match_stats_raw_endpoint_returns_safe_preview(monkeypatch) -> None:
    monkeypatch.setenv('RAPIDAPI_KEY', 'test-key')

    def _fake_get(url: str, headers: dict, timeout: float):
        return _StubResponse(200, payload=[{'secretKey': 'abcd', 'event': {'id': 44}}])

    monkeypatch.setattr('app.providers.allsports_client.httpx.get', _fake_get)

    resp = client.get('/api/allsports/match/44/stats/raw')
    assert resp.status_code == 200
    body = resp.json()
    assert body['top_level_type'] == 'list'
    assert body['list_length'] == 1
    assert body['first_item_keys'] == ['event', 'secretKey']
    assert '[redacted]' in body['preview']

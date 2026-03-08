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
    assert isinstance(body['playerStats'], list)


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

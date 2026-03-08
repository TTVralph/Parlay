from fastapi.testclient import TestClient

from app.main import app, _public_check_rate_limit_hits


client = TestClient(app)


def test_check_slip_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv('PUBLIC_CHECK_RATE_LIMIT_PER_MINUTE', '2')
    monkeypatch.setenv('PUBLIC_CHECK_RATE_LIMIT_WINDOW_SECONDS', '60')
    _public_check_rate_limit_hits.clear()

    ok1 = client.post('/check-slip', json={'text': 'Denver ML'})
    ok2 = client.post('/check-slip', json={'text': 'Denver ML'})
    limited = client.post('/check-slip', json={'text': 'Denver ML'})

    assert ok1.status_code == 200
    assert ok2.status_code == 200
    assert limited.status_code == 429
    assert 'Too many slip checks' in limited.json()['detail']


def test_rate_limit_can_be_disabled(monkeypatch):
    monkeypatch.setenv('PUBLIC_CHECK_RATE_LIMIT_PER_MINUTE', '0')
    _public_check_rate_limit_hits.clear()

    for _ in range(5):
        resp = client.post('/check-slip', json={'text': 'Denver ML'})
        assert resp.status_code == 200

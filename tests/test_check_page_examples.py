from fastapi.testclient import TestClient

from app.main import app


def test_check_page_mentions_one_leg_per_line() -> None:
    client = TestClient(app)
    resp = client.get('/check')
    assert resp.status_code == 200
    html = resp.text
    assert 'One leg per line.' in html
    assert 'Jokic over 24.5 points' in html


def test_check_page_includes_clickable_sample_slips() -> None:
    client = TestClient(app)
    resp = client.get('/check')
    assert resp.status_code == 200
    html = resp.text
    assert 'NBA Props' in html
    assert 'MLB Mix' in html
    assert 'NFL Mix' in html
    assert "data-sample='sample_nba_props'" in html
    assert "data-sample='sample_mlb'" in html
    assert "data-sample='sample_nfl'" in html
    assert 'const sampleSlips=' in html
    assert 'Jokic over 24.5 points' in html
    assert 'Dodgers ML' in html
    assert 'Mahomes over 265.5 passing yards' in html


def test_check_slip_returns_friendly_shape() -> None:
    client = TestClient(app)
    text = 'Denver ML\nJokic over 24.5 points\nGame Total Over 228.5'
    resp = client.post('/check-slip', json={'text': text})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert isinstance(body['legs'], list)
    assert body['parlay_result'] in {'cashed', 'lost', 'pending', 'needs_review'}
    assert set(body['legs'][0].keys()) == {'leg', 'result', 'matched_event'}

from fastapi.testclient import TestClient

from app.main import app


def test_check_page_has_clickable_examples() -> None:
    client = TestClient(app)
    resp = client.get('/check')
    assert resp.status_code == 200
    html = resp.text
    assert 'NBA Player Props' in html
    assert 'NBA Moneyline' in html
    assert 'Mixed Parlay' in html
    assert 'data-sample="props"' in html
    assert 'data-sample="moneyline"' in html
    assert 'data-sample="mixed"' in html


def test_check_slip_accepts_example_format_lines() -> None:
    client = TestClient(app)
    text = 'Denver ML\nJokic over 24.5 points\nGame Total Over 228.5\nOdds +420\nStake 15'
    resp = client.post('/check-slip', json={'text': text})
    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'pending'
    assert [leg['leg'] for leg in body['legs']] == [
        'Denver ML',
        'Jokic over 24.5 points',
        'Game Total Over 228.5',
        'Odds +420',
        'Stake 15',
    ]

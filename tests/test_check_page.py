from fastapi.testclient import TestClient

from app.main import app


def test_check_page_has_copy_summary_button():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    assert 'Copy Summary' in page.text


def test_check_slip_returns_graded_legs_and_overall():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['parlay_result'] == 'lost'
    assert [leg['result'] for leg in body['legs']] == ['win', 'win', 'loss']

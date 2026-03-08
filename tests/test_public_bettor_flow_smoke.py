from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_public_pages_return_200() -> None:
    for path in ['/', '/check', '/leaderboard']:
        resp = client.get(path)
        assert resp.status_code == 200


def test_check_slip_grading_route_still_works() -> None:
    resp = client.post('/check-slip', json={'text': 'Denver ML\nJokic 25+ pts'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['parlay_result'] in {'cashed', 'lost', 'still_live', 'needs_review'}
    assert len(body['legs']) >= 1

from fastapi.testclient import TestClient

from app.main import app


def test_check_slip_endpoint_returns_review_when_unmatched_legs():
    client = TestClient(app)

    response = client.post('/check-slip', json={'text': 'Leg A\n\n Leg B  \n'})

    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['parlay_result'] == 'needs_review'
    assert body['legs'] == [
        {'leg': 'Leg A', 'result': 'review', 'matched_event': None},
        {'leg': 'Leg B', 'result': 'review', 'matched_event': None},
    ]

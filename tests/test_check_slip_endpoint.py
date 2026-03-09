from fastapi.testclient import TestClient

from app.main import app


def test_check_slip_endpoint_returns_review_when_unmatched_legs():
    client = TestClient(app)

    response = client.post('/check-slip', json={'text': 'Leg A\n\n Leg B  \n'})

    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['parlay_result'] == 'needs_review'
    assert body['legs'][0]['leg'] == 'Leg A'
    assert body['legs'][1]['leg'] == 'Leg B'
    assert body['legs'][0]['result'] == 'review'
    assert body['legs'][1]['result'] == 'review'
    assert body['legs'][0]['matched_event'] is None
    assert body['legs'][1]['matched_event'] is None
    assert body['legs'][0]['candidate_games'] == []
    assert body['legs'][1]['candidate_games'] == []
    assert body['legs'][0]['explanation_reason'] == 'Low-confidence parse; send to manual review'

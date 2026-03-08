from fastapi.testclient import TestClient

from app.main import app


def test_check_slip_endpoint_parses_lines_as_pending_legs():
    client = TestClient(app)

    response = client.post('/check-slip', json={'text': 'Leg A\n\n Leg B  \n'})

    assert response.status_code == 200
    assert response.json() == {
        'legs': [
            {'leg': 'Leg A', 'result': 'pending'},
            {'leg': 'Leg B', 'result': 'pending'},
        ],
        'parlay_result': 'pending',
    }

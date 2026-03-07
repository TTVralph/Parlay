from fastapi.testclient import TestClient

from app.main import app


def test_x_fetch_grade_uses_mock_provider() -> None:
    with TestClient(app) as client:
        response = client.post('/ingest/x/fetch-and-grade', json={'tweet_id': 'demo-1'})
        assert response.status_code == 200
        body = response.json()
        assert body['source_type'] == 'tweet'
        assert body['source_ref'].endswith('/status/demo-1')
        assert body['cleaned_text'] == 'Denver ML\nJokic 25+ pts'
        assert body['result']['overall'] == 'cashed'



def test_review_queue_auto_enqueues_needs_review_ticket() -> None:
    with TestClient(app) as client:
        create_resp = client.post('/ingest/x/fetch-grade-and-save', json={'tweet_id': 'demo-review'})
        assert create_resp.status_code == 200
        ticket = create_resp.json()
        assert ticket['overall'] == 'needs_review'
        assert ticket['source_type'] == 'tweet'
        assert ticket['review_items']
        review_id = ticket['review_items'][0]['review_id']

        queue_resp = client.get('/review-queue')
        assert queue_resp.status_code == 200
        queue = queue_resp.json()
        matching = [item for item in queue if item['review_id'] == review_id and item['ticket_id'] == ticket['ticket_id']]
        assert matching
        assert matching[0]['status'] == 'open'

        resolve_resp = client.post(f'/review-queue/{review_id}/resolve', json={
            'status': 'approved',
            'resolution_note': 'Manual reviewer confirmed parser needs alias expansion',
        })
        assert resolve_resp.status_code == 200
        resolved = resolve_resp.json()
        assert resolved['status'] == 'approved'
        assert resolved['resolution_note'].startswith('Manual reviewer confirmed')

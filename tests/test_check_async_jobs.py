import time

from fastapi.testclient import TestClient

from app.main import app, _public_check_jobs


client = TestClient(app)


def test_check_job_submit_and_poll_to_complete(monkeypatch):
    monkeypatch.setenv('PUBLIC_CHECK_RATE_LIMIT_PER_MINUTE', '1000')
    _public_check_jobs.clear()

    create = client.post('/check/jobs', json={'text': 'Denver ML\nJokic 25+ pts'})
    assert create.status_code == 200
    payload = create.json()
    assert payload['status'] == 'pending'
    job_id = payload['job_id']

    final = None
    for _ in range(30):
        polled = client.get(f'/check/jobs/{job_id}')
        assert polled.status_code == 200
        body = polled.json()
        if body['status'] == 'complete':
            final = body
            break
        time.sleep(0.02)

    assert final is not None
    assert final['result']['ok'] is True
    assert final['result']['parlay_result'] in {'cashed', 'lost', 'pending', 'needs_review'}


def test_check_job_returns_404_for_missing_job():
    resp = client.get('/check/jobs/not-a-real-job')
    assert resp.status_code == 404


def test_check_job_submit_requires_text():
    resp = client.post('/check/jobs', json={'text': '   '})
    assert resp.status_code == 400

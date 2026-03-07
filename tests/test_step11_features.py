from fastapi.testclient import TestClient

from app.main import app


def admin_headers():
    return {"Authorization": "Bearer dev-admin-token"}


def test_admin_auth_status_requires_token():
    client = TestClient(app)
    resp = client.get('/admin/auth/status')
    assert resp.status_code == 401
    ok = client.get('/admin/auth/status', headers=admin_headers())
    assert ok.status_code == 200
    assert ok.json()['authenticated'] is True


def test_public_pages_and_ticket_moderation():
    client = TestClient(app)
    payload = {
        "tweet_id": "1",
        "username": "endgamepicks",
        "text": "Denver ML\nJokic over 24.5 points",
        "posted_at": "2026-03-07T18:00:00"
    }
    saved = client.post('/ingest/tweet/grade-and-save', json=payload)
    assert saved.status_code == 200
    ticket_id = saved.json()['ticket_id']

    board = client.get('/public/leaderboard')
    assert board.status_code == 200
    assert any(row['username'] == 'endgamepicks' for row in board.json()['rows'])

    page = client.get('/leaderboard')
    assert page.status_code == 200
    assert 'Public Capper Leaderboard' in page.text

    hide = client.post(f'/admin/moderation/tickets/{ticket_id}/hide', json={'reason': 'spam'}, headers=admin_headers())
    assert hide.status_code == 200

    public_profile = client.get('/public/cappers/endgamepicks')
    assert public_profile.status_code == 200
    assert all(t['ticket_id'] != ticket_id for t in public_profile.json()['recent_tickets'])

    hidden = client.get('/admin/moderation/tickets/hidden', headers=admin_headers())
    assert hidden.status_code == 200
    assert any(t['ticket_id'] == ticket_id for t in hidden.json())


def test_capper_profile_moderation_hides_public_profile():
    client = TestClient(app)
    payload = {
        "tweet_id": "2",
        "username": "capperx",
        "text": "Denver ML",
        "posted_at": "2026-03-07T18:00:00"
    }
    client.post('/ingest/tweet/grade-and-save', json=payload)
    hide = client.post('/admin/moderation/cappers/capperx/hide-profile', json={'reason': 'abuse'}, headers=admin_headers())
    assert hide.status_code == 200
    resp = client.get('/public/cappers/capperx')
    assert resp.status_code == 404

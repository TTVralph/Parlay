from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    login = client.post('/admin/auth/login', json={'username': 'admin-capper-crud', 'password': 'secret123'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_admin_can_create_edit_and_deactivate_capper_profile() -> None:
    tweet = client.post(
        '/ingest/tweet/grade-and-save',
        json={
            'tweet_id': 'cappercrud1',
            'username': 'cappercrud',
            'text': 'Denver ML\nJokic 25+ pts',
        },
    )
    assert tweet.status_code == 200

    board_before = client.get('/public/leaderboard')
    assert board_before.status_code == 200
    assert any(row['username'] == 'cappercrud' for row in board_before.json()['rows'])

    headers = _admin_headers()

    created = client.post(
        '/admin/cappers',
        json={'username': 'cappercrud', 'display_name': 'Capper Crud', 'bio': 'Track record', 'is_public': True},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()['username'] == 'cappercrud'
    assert created.json()['display_name'] == 'Capper Crud'

    updated = client.patch('/admin/cappers/cappercrud', json={'bio': 'Updated bio'}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()['bio'] == 'Updated bio'

    deactivated = client.post('/admin/cappers/cappercrud/deactivate', json={'reason': 'policy'}, headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()['is_public'] is False

    board_after = client.get('/public/leaderboard')
    assert board_after.status_code == 200
    assert all(row['username'] != 'cappercrud' for row in board_after.json()['rows'])


def test_admin_cappers_endpoints_require_admin_auth() -> None:
    resp = client.get('/admin/cappers')
    assert resp.status_code == 401

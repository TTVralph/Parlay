from fastapi.testclient import TestClient

from app.main import app


def test_user_register_login_logout_flow():
    client = TestClient(app)
    reg = client.post('/auth/register', json={'username': 'ralph', 'password': 'secret12', 'email': 'ralph@example.com'})
    assert reg.status_code == 200
    token = reg.json()['access_token']

    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200
    assert me.json()['username'] == 'ralph'

    out = client.post('/auth/logout', headers={'Authorization': f'Bearer {token}'})
    assert out.status_code == 200
    denied = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert denied.status_code == 401

    login = client.post('/auth/login', json={'username': 'ralph', 'password': 'secret12'})
    assert login.status_code == 200
    assert login.json()['user']['username'] == 'ralph'


def test_admin_session_login_and_frontend_page():
    client = TestClient(app)
    login = client.post('/admin/auth/login', json={'username': 'opsadmin', 'password': 'topsecret'})
    assert login.status_code == 200
    token = login.json()['access_token']

    sessions = client.get('/admin/auth/sessions', headers={'Authorization': f'Bearer {token}'})
    assert sessions.status_code == 200
    assert any(row['username'] == 'opsadmin' for row in sessions.json()['rows'])

    page = client.get('/app')
    assert page.status_code == 200
    assert 'ParlayBot Step 12' in page.text
    assert 'Saved admin sessions' in page.text

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import app
from app.db.session import engine


def test_schema_migrations_and_built_frontend_assets_exist():
    client = TestClient(app)
    page = client.get('/app')
    assert page.status_code == 200
    assert 'ParlayBot Step 13' in page.text

    asset = client.get('/assets/app.js')
    assert asset.status_code == 200
    assert 'loadLeaderboard' in asset.text

    inspector = inspect(engine)
    assert 'schema_migrations' in inspector.get_table_names()
    with engine.begin() as conn:
        rows = conn.execute(text('SELECT version FROM schema_migrations ORDER BY version')).fetchall()
    versions = [row[0] for row in rows]
    assert '20260307_002_user_roles' in versions
    assert '20260307_003_capper_profile_fields' in versions


def test_capper_role_can_manage_own_profile_and_member_cannot():
    client = TestClient(app)

    reg = client.post('/auth/register', json={
        'username': 'capperuser',
        'password': 'secret12',
        'role': 'capper',
        'linked_capper_username': 'endgamepicks',
    })
    assert reg.status_code == 200
    capper_token = reg.json()['access_token']

    me = client.get('/capper/me', headers={'Authorization': f'Bearer {capper_token}'})
    assert me.status_code == 200
    assert me.json()['username'] == 'endgamepicks'

    patch = client.patch('/capper/me', json={'display_name': 'Endgame Picks', 'bio': 'Verified capper', 'is_public': True}, headers={'Authorization': f'Bearer {capper_token}'})
    assert patch.status_code == 200
    assert patch.json()['display_name'] == 'Endgame Picks'
    assert patch.json()['bio'] == 'Verified capper'

    public_profile = client.get('/public/cappers/endgamepicks')
    assert public_profile.status_code == 200

    member = client.post('/auth/register', json={'username': 'regularmember', 'password': 'secret12'})
    member_token = member.json()['access_token']
    denied = client.get('/capper/me', headers={'Authorization': f'Bearer {member_token}'})
    assert denied.status_code == 403

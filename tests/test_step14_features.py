from fastapi.testclient import TestClient

from app.main import app


def _admin_headers(client: TestClient):
    login = client.post('/admin/auth/login', json={'username': 'admin14', 'password': 'secret14'})
    token = login.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _member_headers(client: TestClient):
    reg = client.post('/auth/register', json={'username': 'member14', 'password': 'secret14', 'role': 'member'})
    token = reg.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_billing_subscription_flow_and_plans():
    client = TestClient(app)
    user_headers = _member_headers(client)
    admin_headers = _admin_headers(client)

    plans = client.get('/billing/plans')
    assert plans.status_code == 200
    codes = {row['code'] for row in plans.json()['rows']}
    assert {'free', 'pro', 'pro_plus'} <= codes

    checkout = client.post('/billing/subscribe', json={'plan_code': 'pro'}, headers=user_headers)
    assert checkout.status_code == 200
    body = checkout.json()
    assert body['plan_code'] == 'pro'
    assert body['status'] == 'pending'

    complete = client.post(f"/billing/mock/checkout/{body['subscription_id']}/complete", headers=admin_headers)
    assert complete.status_code == 200
    assert complete.json()['status'] == 'active'

    mine = client.get('/billing/me', headers=user_headers)
    assert mine.status_code == 200
    assert mine.json()['plan_code'] == 'pro'
    assert mine.json()['status'] == 'active'


def test_affiliate_resolution_and_capper_verification_public_profile():
    client = TestClient(app)
    admin_headers = _admin_headers(client)

    upsert = client.post('/affiliate/links', json={
        'bookmaker': 'draftkings',
        'base_url': 'https://example.com/dk',
        'affiliate_code': 'aff123',
        'campaign_code': 'spring',
        'is_active': True,
    }, headers=admin_headers)
    assert upsert.status_code == 200
    assert upsert.json()['bookmaker'] == 'draftkings'

    resolved = client.post('/affiliate/resolve', json={
        'bookmaker': 'draftkings',
        'capper_username': 'endgamepicks',
        'ticket_id': 'ticket123',
    })
    assert resolved.status_code == 200
    url = resolved.json()['resolved_url']
    assert 'aff=aff123' in url
    assert 'campaign=spring' in url
    assert 'capper=endgamepicks' in url

    verify = client.post('/admin/cappers/endgamepicks/verify', json={'badge': 'sharp', 'note': 'manual review approved'}, headers=admin_headers)
    assert verify.status_code == 200
    assert verify.json()['verified'] is True
    assert verify.json()['verification_badge'] == 'sharp'

    profile = client.get('/public/cappers/endgamepicks')
    assert profile.status_code == 200
    assert profile.json()['verified'] is True
    assert profile.json()['verification_badge'] == 'sharp'

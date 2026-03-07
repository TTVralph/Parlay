import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app


def _register(client: TestClient, username: str, role: str = 'member'):
    res = client.post('/auth/register', json={'username': username, 'password': 'secret15', 'role': role})
    assert res.status_code == 200
    return {'Authorization': f"Bearer {res.json()['access_token']}"}


def _admin_headers(client: TestClient):
    login = client.post('/admin/auth/login', json={'username': 'admin15', 'password': 'secret15'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


def _sign(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()


def test_entitlement_gates_and_billing_entitlements():
    client = TestClient(app)
    user_headers = _register(client, 'member15a')
    admin_headers = _admin_headers(client)

    locked = client.get('/pro/dashboard/cappers-roi', headers=user_headers)
    assert locked.status_code == 403

    entitlements = client.get('/billing/entitlements', headers=user_headers)
    assert entitlements.status_code == 200
    assert entitlements.json()['plan_code'] == 'free'
    assert 'roi_dashboard' not in entitlements.json()['entitlements']

    checkout = client.post('/billing/subscribe', json={'plan_code': 'pro'}, headers=user_headers)
    assert checkout.status_code == 200
    sub_id = checkout.json()['subscription_id']

    complete = client.post(f'/billing/mock/checkout/{sub_id}/complete', headers=admin_headers)
    assert complete.status_code == 200
    assert complete.json()['status'] == 'active'

    entitlements = client.get('/billing/entitlements', headers=user_headers)
    assert entitlements.status_code == 200
    assert entitlements.json()['plan_code'] == 'pro'
    assert 'roi_dashboard' in entitlements.json()['entitlements']

    unlocked = client.get('/pro/dashboard/cappers-roi', headers=user_headers)
    assert unlocked.status_code == 200


def test_stripe_checkout_and_webhook_activation():
    client = TestClient(app)
    user_headers = _register(client, 'member15b')

    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro_plus'}, headers=user_headers)
    assert checkout.status_code == 200
    body = checkout.json()
    assert body['provider'] == 'stripe'
    assert 'checkout.stripe.com' in body['checkout_url']
    assert body['status'] == 'pending'

    webhook_payload = {
        'id': 'evt_step15_paid',
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'provider_checkout_id': body['checkout_url'].split('/pay/')[1].split('?')[0],
            }
        },
    }
    signature = _sign(webhook_payload)
    hook = client.post('/billing/stripe/webhook', json=webhook_payload, headers={'Stripe-Signature': signature})
    assert hook.status_code == 200
    assert hook.json()['processed'] is True

    me = client.get('/billing/me', headers=user_headers)
    assert me.status_code == 200
    assert me.json()['plan_code'] == 'pro_plus'
    assert me.json()['status'] == 'active'


def test_affiliate_click_tracking_and_analytics_gated():
    client = TestClient(app)
    admin_headers = _admin_headers(client)
    free_headers = _register(client, 'member15c')
    pro_headers = _register(client, 'member15d')

    sub = client.post('/billing/subscribe', json={'plan_code': 'pro'}, headers=pro_headers)
    sub_id = sub.json()['subscription_id']
    client.post(f'/billing/mock/checkout/{sub_id}/complete', headers=admin_headers)

    upsert = client.post('/affiliate/links', json={
        'bookmaker': 'fanduel',
        'base_url': 'https://example.com/fd',
        'affiliate_code': 'afffd',
        'campaign_code': 'cmp15',
        'is_active': True,
    }, headers=admin_headers)
    assert upsert.status_code == 200

    for capper in ['alpha', 'beta', 'alpha']:
        res = client.post('/affiliate/resolve', json={'bookmaker': 'fanduel', 'capper_username': capper, 'source': 'public_profile'})
        assert res.status_code == 200
        assert 'aff=afffd' in res.json()['resolved_url']

    blocked = client.get('/affiliate/analytics', headers=free_headers)
    assert blocked.status_code == 403

    analytics = client.get('/affiliate/analytics', headers=pro_headers)
    assert analytics.status_code == 200
    rows = analytics.json()['rows']
    assert rows[0]['bookmaker'] == 'fanduel'
    assert rows[0]['clicks'] == 3
    assert rows[0]['unique_cappers'] == 2

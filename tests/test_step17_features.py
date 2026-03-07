import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app


def _register_and_login(client: TestClient, username: str = 'step17user') -> str:
    resp = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'email': f'{username}@example.com'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def _admin_login(client: TestClient) -> str:
    resp = client.post('/admin/auth/login', json={'username': 'admin', 'password': 'adminpass'})
    if resp.status_code != 200:
        client.post('/auth/register', json={'username': 'admin', 'password': 'adminpass', 'email': 'admin@example.com'})
        from app.db.session import SessionLocal
        from app.services.repository import get_user_by_username, set_user_role
        db = SessionLocal()
        try:
            user = get_user_by_username(db, 'admin')
            set_user_role(db, user, role='admin')
        finally:
            db.close()
        resp = client.post('/admin/auth/login', json={'username': 'admin', 'password': 'adminpass'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def test_billing_history_and_email_notifications_after_stripe_events():
    client = TestClient(app)
    token = _register_and_login(client, 'historyuser')
    headers = {'Authorization': f'Bearer {token}'}

    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro'}, headers=headers)
    assert checkout.status_code == 200
    checkout_url = checkout.json()['checkout_url']
    checkout_id = checkout_url.split('/pay/')[1].split('?')[0]

    completed = {
        'id': 'evt_step17_completed',
        'type': 'checkout.session.completed',
        'data': {'object': {'client_reference_id': checkout_id, 'customer': 'cus_hist', 'subscription': 'sub_hist'}},
    }
    raw = json.dumps(completed).encode('utf-8')
    sig = hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()
    resp = client.post('/billing/stripe/webhook', content=raw, headers={'Stripe-Signature': sig, 'Content-Type': 'application/json'})
    assert resp.status_code == 200

    invoice = {
        'id': 'evt_step17_invoice',
        'type': 'invoice.paid',
        'data': {'object': {
            'id': 'in_test_001',
            'client_reference_id': checkout_id,
            'customer': 'cus_hist',
            'subscription': 'sub_hist',
            'amount_paid': 1900,
            'currency': 'usd',
            'hosted_invoice_url': 'https://billing.example/invoices/in_test_001',
        }},
    }
    raw2 = json.dumps(invoice).encode('utf-8')
    sig2 = hmac.new(b'dev-stripe-webhook-secret', raw2, hashlib.sha256).hexdigest()
    resp2 = client.post('/billing/stripe/webhook', content=raw2, headers={'Stripe-Signature': sig2, 'Content-Type': 'application/json'})
    assert resp2.status_code == 200

    invoices = client.get('/billing/invoices', headers=headers)
    assert invoices.status_code == 200
    assert invoices.json()['rows'][0]['provider_invoice_id'] == 'in_test_001'

    emails = client.get('/billing/emails', headers=headers)
    assert emails.status_code == 200
    template_keys = {row['template_key'] for row in emails.json()['rows']}
    assert 'subscription_activated' in template_keys
    assert 'invoice_paid' in template_keys

    history = client.get('/billing/history', headers=headers)
    assert history.status_code == 200
    assert len(history.json()['invoices']) >= 1
    assert len(history.json()['email_notifications']) >= 2


def test_affiliate_conversion_tracking_and_analytics():
    client = TestClient(app)
    user_token = _register_and_login(client, 'affuser')
    admin_token = _admin_login(client)
    admin_headers = {'Authorization': f'Bearer {admin_token}'}
    user_headers = {'Authorization': f'Bearer {user_token}'}

    upsert = client.post('/affiliate/links', json={'bookmaker': 'DraftKings', 'base_url': 'https://dk.example/join', 'affiliate_code': 'abc', 'campaign_code': 'camp1', 'is_active': True}, headers=admin_headers)
    assert upsert.status_code == 200

    resolve = client.post('/affiliate/resolve', json={'bookmaker': 'DraftKings', 'capper_username': 'endgamepicks', 'source': 'step17'}, headers=user_headers)
    assert resolve.status_code == 200
    click_token = resolve.json()['click_token']
    assert click_token

    conv = client.post('/affiliate/conversions', json={'click_token': click_token, 'revenue_amount': 125.5, 'external_ref': 'conv_001'}, headers=admin_headers)
    assert conv.status_code == 200
    assert conv.json()['revenue_amount'] == 125.5

    analytics = client.get('/affiliate/analytics/draftkings', headers=admin_headers)
    assert analytics.status_code == 200
    row = analytics.json()['rows'][0]
    assert row['clicks'] >= 1
    assert row['conversions'] == 1
    assert row['revenue'] == 125.5
    assert row['conversion_rate'] > 0

    conversions = client.get('/affiliate/conversions?bookmaker=draftkings', headers=admin_headers)
    assert conversions.status_code == 200
    assert conversions.json()['rows'][0]['external_ref'] == 'conv_001'


def test_payment_failed_creates_email_notification():
    client = TestClient(app)
    token = _register_and_login(client, 'failedpay')
    headers = {'Authorization': f'Bearer {token}'}

    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro'}, headers=headers)
    checkout_id = checkout.json()['checkout_url'].split('/pay/')[1].split('?')[0]
    completed = {
        'id': 'evt_step17_completed_2',
        'type': 'checkout.session.completed',
        'data': {'object': {'client_reference_id': checkout_id, 'customer': 'cus_fail', 'subscription': 'sub_fail'}},
    }
    raw = json.dumps(completed).encode('utf-8')
    sig = hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()
    client.post('/billing/stripe/webhook', content=raw, headers={'Stripe-Signature': sig, 'Content-Type': 'application/json'})

    failed = {
        'id': 'evt_step17_failed',
        'type': 'invoice.payment_failed',
        'data': {'object': {'client_reference_id': checkout_id, 'customer': 'cus_fail', 'subscription': 'sub_fail'}},
    }
    raw2 = json.dumps(failed).encode('utf-8')
    sig2 = hmac.new(b'dev-stripe-webhook-secret', raw2, hashlib.sha256).hexdigest()
    resp = client.post('/billing/stripe/webhook', content=raw2, headers={'Stripe-Signature': sig2, 'Content-Type': 'application/json'})
    assert resp.status_code == 200

    emails = client.get('/billing/emails', headers=headers)
    assert emails.status_code == 200
    assert any(row['template_key'] == 'invoice_payment_failed' for row in emails.json()['rows'])

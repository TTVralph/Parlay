import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app


def _register_and_login(client: TestClient, username: str = 'step18user') -> str:
    resp = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'email': f'{username}@example.com'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def _admin_login(client: TestClient) -> str:
    resp = client.post('/admin/auth/login', json={'username': 'admin18', 'password': 'adminpass'})
    if resp.status_code != 200:
        client.post('/auth/register', json={'username': 'admin18', 'password': 'adminpass', 'email': 'admin18@example.com'})
        from app.db.session import SessionLocal
        from app.services.repository import get_user_by_username, set_user_role
        db = SessionLocal()
        try:
            user = get_user_by_username(db, 'admin18')
            set_user_role(db, user, role='admin')
        finally:
            db.close()
        resp = client.post('/admin/auth/login', json={'username': 'admin18', 'password': 'adminpass'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def _activate_subscription(client: TestClient, headers: dict[str, str]) -> str:
    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro'}, headers=headers)
    assert checkout.status_code == 200
    checkout_id = checkout.json()['checkout_url'].split('/pay/')[1].split('?')[0]
    completed = {
        'id': f'evt_step18_{checkout_id}',
        'type': 'checkout.session.completed',
        'data': {'object': {'client_reference_id': checkout_id, 'customer': 'cus_step18', 'subscription': 'sub_step18'}},
    }
    raw = json.dumps(completed).encode('utf-8')
    sig = hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()
    resp = client.post('/billing/stripe/webhook', content=raw, headers={'Stripe-Signature': sig, 'Content-Type': 'application/json'})
    assert resp.status_code == 200

    invoice = {
        'id': f'evt_step18_inv_{checkout_id}',
        'type': 'invoice.paid',
        'data': {'object': {
            'id': f'in_step18_{checkout_id}',
            'client_reference_id': checkout_id,
            'customer': 'cus_step18',
            'subscription': 'sub_step18',
            'amount_paid': 1900,
            'currency': 'usd',
            'hosted_invoice_url': 'https://billing.example/invoices/in_step18',
        }},
    }
    raw2 = json.dumps(invoice).encode('utf-8')
    sig2 = hmac.new(b'dev-stripe-webhook-secret', raw2, hashlib.sha256).hexdigest()
    resp2 = client.post('/billing/stripe/webhook', content=raw2, headers={'Stripe-Signature': sig2, 'Content-Type': 'application/json'})
    assert resp2.status_code == 200
    return f'in_step18_{checkout_id}'


def test_invoice_links_and_pdf_download():
    client = TestClient(app)
    token = _register_and_login(client, 'invoicepdf')
    headers = {'Authorization': f'Bearer {token}'}
    invoice_id = _activate_subscription(client, headers)

    links = client.get(f'/billing/invoices/{invoice_id}/links', headers=headers)
    assert links.status_code == 200
    payload = links.json()
    assert payload['pdf_download_url'].endswith('/download?token=' + payload['pdf_download_url'].split('token=')[1])
    assert payload['pdf_filename'].endswith('.pdf')

    download = client.get(f'/billing/invoices/{invoice_id}/download', headers=headers)
    assert download.status_code == 200
    assert download.headers['content-type'].startswith('application/pdf')
    assert download.content.startswith(b'%PDF-1.4')


def test_email_notifications_include_provider_fields():
    client = TestClient(app)
    token = _register_and_login(client, 'emailprovider')
    headers = {'Authorization': f'Bearer {token}'}
    _activate_subscription(client, headers)

    emails = client.get('/billing/emails', headers=headers)
    assert emails.status_code == 200
    row = emails.json()['rows'][0]
    assert row['provider'] in {'mock', 'smtp'}
    assert row['provider_message_id']


def test_affiliate_postback_and_webhook_ingestion():
    client = TestClient(app)
    admin_token = _admin_login(client)
    user_token = _register_and_login(client, 'webhookuser')
    admin_headers = {'Authorization': f'Bearer {admin_token}'}
    user_headers = {'Authorization': f'Bearer {user_token}'}

    upsert = client.post('/affiliate/links', json={'bookmaker': 'DraftKings', 'base_url': 'https://dk.example/join', 'affiliate_code': 'abc', 'campaign_code': 'camp1', 'is_active': True}, headers=admin_headers)
    assert upsert.status_code == 200
    resolve = client.post('/affiliate/resolve', json={'bookmaker': 'DraftKings', 'capper_username': 'endgamepicks', 'source': 'step18'}, headers=user_headers)
    assert resolve.status_code == 200
    click_token = resolve.json()['click_token']

    postback = client.post('/affiliate/postback', json={'click_token': click_token, 'bookmaker': 'DraftKings', 'revenue_amount': 77.0, 'external_ref': 'pb_001'}, headers=admin_headers)
    assert postback.status_code == 200
    assert postback.json()['status'] == 'recorded'

    webhook = client.post('/affiliate/webhooks/impact', json={'payload': {'subid': click_token, 'bookmaker': 'DraftKings', 'payout': 55.5, 'conversion_id': 'wh_001'}}, headers=admin_headers)
    assert webhook.status_code == 200
    assert webhook.json()['network'] == 'impact'
    assert webhook.json()['status'] == 'recorded'

    events = client.get('/affiliate/webhooks', headers=admin_headers)
    assert events.status_code == 200
    assert len(events.json()['rows']) >= 2

    conversions = client.get('/affiliate/conversions?bookmaker=draftkings', headers=admin_headers)
    assert conversions.status_code == 200
    assert len(conversions.json()['rows']) >= 2

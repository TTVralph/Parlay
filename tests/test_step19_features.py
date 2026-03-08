import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from app.emailer import send_email_message


def _register_and_login(client: TestClient, username: str = 'step19user') -> str:
    resp = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'email': f'{username}@example.com'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def _activate_subscription(client: TestClient, headers: dict[str, str]) -> str:
    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro'}, headers=headers)
    assert checkout.status_code == 200
    checkout_id = checkout.json()['checkout_url'].split('/pay/')[1].split('?')[0]
    completed = {
        'id': f'evt_step19_{checkout_id}',
        'type': 'checkout.session.completed',
        'data': {'object': {'client_reference_id': checkout_id, 'customer': 'cus_step19', 'subscription': 'sub_step19'}},
    }
    raw = json.dumps(completed).encode('utf-8')
    sig = hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()
    resp = client.post('/billing/stripe/webhook', content=raw, headers={'Stripe-Signature': sig, 'Content-Type': 'application/json'})
    assert resp.status_code == 200

    invoice = {
        'id': f'evt_step19_inv_{checkout_id}',
        'type': 'invoice.paid',
        'data': {'object': {
            'id': f'in_step19_{checkout_id}',
            'client_reference_id': checkout_id,
            'customer': 'cus_step19',
            'subscription': 'sub_step19',
            'amount_paid': 2900,
            'currency': 'usd',
            'hosted_invoice_url': 'https://billing.example/invoices/in_step19',
        }},
    }
    raw2 = json.dumps(invoice).encode('utf-8')
    sig2 = hmac.new(b'dev-stripe-webhook-secret', raw2, hashlib.sha256).hexdigest()
    resp2 = client.post('/billing/stripe/webhook', content=raw2, headers={'Stripe-Signature': sig2, 'Content-Type': 'application/json'})
    assert resp2.status_code == 200
    return f'in_step19_{checkout_id}'


def test_signed_public_invoice_link_download():
    client = TestClient(app)
    token = _register_and_login(client, 'signedinvoice')
    headers = {'Authorization': f'Bearer {token}'}
    invoice_id = _activate_subscription(client, headers)

    res = client.get(f'/billing/invoices/{invoice_id}/public-link', headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert '/public/invoices/' in payload['public_url']

    dl = client.get(payload['public_url'])
    assert dl.status_code == 200
    assert dl.headers['content-type'].startswith('application/pdf')
    assert dl.content.startswith(b'%PDF-1.4')


def test_ops_pages_exist():
    client = TestClient(app)
    for path in ['/ops/billing', '/ops/emails', '/ops/affiliate-webhooks']:
        res = client.get(path)
        assert res.status_code == 200
        assert 'html' in res.headers['content-type']


def test_resend_and_mailgun_dry_run(monkeypatch):
    monkeypatch.setenv('EMAIL_DRY_RUN', 'true')
    monkeypatch.setenv('EMAIL_PROVIDER', 'resend')
    resend = send_email_message(to_email='a@example.com', subject='Hello', body_text='world')
    assert resend.provider == 'resend'
    assert resend.status in {'queued', 'sent'}

    monkeypatch.setenv('EMAIL_PROVIDER', 'mailgun')
    mailgun = send_email_message(to_email='a@example.com', subject='Hello', body_text='world')
    assert mailgun.provider == 'mailgun'
    assert mailgun.status in {'queued', 'sent'}


def test_landing_page_exists_with_expected_ctas():
    client = TestClient(app)
    res = client.get('/')
    assert res.status_code == 200
    body = res.text
    assert 'Did This Parlay Cash?' in body
    assert 'Paste your bet slip and instantly see if it hit.' in body
    assert "href='/check'" in body
    assert "href='/app'" in body

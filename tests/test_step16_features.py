import hmac
import hashlib
import json
from fastapi.testclient import TestClient

from app.main import app


def _register_and_login(client: TestClient, username: str = 'billuser') -> str:
    resp = client.post('/auth/register', json={'username': username, 'password': 'secret123', 'email': f'{username}@example.com'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def test_billing_account_cancel_resume_and_portal():
    client = TestClient(app)
    token = _register_and_login(client, 'billflow')
    headers = {'Authorization': f'Bearer {token}'}

    checkout = client.post('/billing/stripe/checkout', json={'plan_code': 'pro'}, headers=headers)
    assert checkout.status_code == 200
    payload = checkout.json()
    assert payload['provider'] == 'stripe'

    webhook_payload = {
        'id': 'evt_step16_account',
        'type': 'checkout.session.completed',
        'data': {'object': {'client_reference_id': payload['checkout_url'].split('/pay/')[1].split('?')[0], 'customer': 'cus_step16', 'subscription': 'sub_step16'}},
    }
    raw = json.dumps(webhook_payload).encode('utf-8')
    sig = hmac.new(b'dev-stripe-webhook-secret', raw, hashlib.sha256).hexdigest()
    hook = client.post('/billing/stripe/webhook', content=raw, headers={'Stripe-Signature': sig, 'Content-Type': 'application/json'})
    assert hook.status_code == 200

    account = client.get('/billing/account', headers=headers)
    assert account.status_code == 200
    assert account.json()['subscription']['provider_customer_id'] == 'cus_step16'

    cancel = client.post('/billing/cancel', json={'immediate': False}, headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()['cancel_at_period_end'] is True

    resume = client.post('/billing/resume', headers=headers)
    assert resume.status_code == 200
    assert resume.json()['cancel_at_period_end'] is False

    portal = client.post('/billing/portal', json={'return_url': 'https://example.com/app'}, headers=headers)
    assert portal.status_code == 200
    assert 'billing.stripe.com' in portal.json()['url']

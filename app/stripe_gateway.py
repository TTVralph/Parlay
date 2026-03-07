from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass
class StripeCheckoutResult:
    checkout_id: str
    checkout_url: str
    customer_id: str | None = None
    subscription_id: str | None = None
    mode: str = 'mock'


@dataclass
class StripePortalResult:
    portal_url: str
    customer_id: str | None = None
    mode: str = 'mock'


def stripe_sdk_enabled() -> bool:
    return os.getenv('STRIPE_USE_SDK', 'false').lower() in {'1', 'true', 'yes'}


def _load_stripe_module():
    try:
        import stripe  # type: ignore
        return stripe
    except Exception:
        return None


def create_checkout_session(*, plan_code: str, success_url: str, cancel_url: str, customer_email: str | None = None, customer_id: str | None = None) -> StripeCheckoutResult:
    if stripe_sdk_enabled():
        stripe = _load_stripe_module()
        api_key = os.getenv('STRIPE_SECRET_KEY')
        price_prefix = os.getenv('STRIPE_PRICE_LOOKUP_PREFIX', 'price_')
        if stripe and api_key:
            stripe.api_key = api_key
            metadata = {'plan_code': plan_code}
            kwargs = {
                'mode': 'subscription',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'line_items': [{'price': f'{price_prefix}{plan_code}', 'quantity': 1}],
                'metadata': metadata,
                'client_reference_id': f'plan:{plan_code}',
            }
            if customer_id:
                kwargs['customer'] = customer_id
            elif customer_email:
                kwargs['customer_email'] = customer_email
            session = stripe.checkout.Session.create(**kwargs)
            return StripeCheckoutResult(
                checkout_id=session.get('id') or f'cs_{secrets.token_hex(8)}',
                checkout_url=session.get('url') or '',
                customer_id=session.get('customer'),
                subscription_id=session.get('subscription'),
                mode='sdk',
            )
    checkout_id = f'chk_{secrets.token_hex(8)}'
    url = f'https://checkout.stripe.com/pay/{checkout_id}?plan={plan_code}'
    return StripeCheckoutResult(checkout_id=checkout_id, checkout_url=url, customer_id=customer_id or f'cus_{secrets.token_hex(6)}', subscription_id=f'sub_{secrets.token_hex(6)}', mode='mock')


def create_billing_portal(*, customer_id: str | None, return_url: str) -> StripePortalResult:
    if stripe_sdk_enabled() and customer_id:
        stripe = _load_stripe_module()
        api_key = os.getenv('STRIPE_SECRET_KEY')
        if stripe and api_key:
            stripe.api_key = api_key
            session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
            return StripePortalResult(portal_url=session.get('url') or return_url, customer_id=customer_id, mode='sdk')
    customer_id = customer_id or f'cus_{secrets.token_hex(6)}'
    return StripePortalResult(portal_url=f'https://billing.stripe.com/p/session/{customer_id}?return_url={return_url}', customer_id=customer_id, mode='mock')

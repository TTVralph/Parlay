from __future__ import annotations

import base64
import json
import os
import secrets
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass
class EmailSendResult:
    provider: str
    status: str
    message_id: str | None = None
    error: str | None = None


def email_provider() -> str:
    return os.getenv('EMAIL_PROVIDER', 'mock').lower().strip()


def _dry_run_enabled() -> bool:
    return os.getenv('EMAIL_DRY_RUN', 'false').lower().strip() in {'1', 'true', 'yes', 'on'}


def _fake_send(provider: str) -> EmailSendResult:
    status = 'queued' if provider in {'resend', 'mailgun'} else 'sent'
    return EmailSendResult(provider=provider, status=status, message_id=f'{provider}_{secrets.token_hex(8)}')


def _post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode('utf-8') or '{}'
    return json.loads(raw)


def _post_form(url: str, headers: dict[str, str], payload: dict[str, str]) -> str:
    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8')


def _send_via_resend(*, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> EmailSendResult:
    api_key = os.getenv('RESEND_API_KEY')
    from_email = os.getenv('RESEND_FROM_EMAIL', 'noreply@example.com')
    if _dry_run_enabled():
        return _fake_send('resend')
    if not api_key:
        return EmailSendResult(provider='resend', status='failed', error='RESEND_API_KEY not configured')
    try:
        payload = {'from': from_email, 'to': [to_email], 'subject': subject, 'text': body_text}
        if body_html:
            payload['html'] = body_html
        response = _post_json('https://api.resend.com/emails', {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, payload)
        return EmailSendResult(provider='resend', status='sent', message_id=response.get('id'))
    except urllib.error.HTTPError as exc:
        return EmailSendResult(provider='resend', status='failed', error=f'HTTP {exc.code}')
    except Exception as exc:
        return EmailSendResult(provider='resend', status='failed', error=str(exc))


def _send_via_mailgun(*, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> EmailSendResult:
    api_key = os.getenv('MAILGUN_API_KEY')
    domain = os.getenv('MAILGUN_DOMAIN')
    from_email = os.getenv('MAILGUN_FROM_EMAIL', f'postmaster@{domain}' if domain else 'noreply@example.com')
    if _dry_run_enabled():
        return _fake_send('mailgun')
    if not api_key or not domain:
        return EmailSendResult(provider='mailgun', status='failed', error='MAILGUN_API_KEY or MAILGUN_DOMAIN not configured')
    try:
        headers = {'Authorization': 'Basic ' + base64.b64encode(f'api:{api_key}'.encode('utf-8')).decode('ascii')}
        payload = {'from': from_email, 'to': to_email, 'subject': subject, 'text': body_text}
        if body_html:
            payload['html'] = body_html
        _post_form(f'https://api.mailgun.net/v3/{domain}/messages', headers, payload)
        return EmailSendResult(provider='mailgun', status='sent', message_id=f'mailgun_{secrets.token_hex(8)}')
    except urllib.error.HTTPError as exc:
        return EmailSendResult(provider='mailgun', status='failed', error=f'HTTP {exc.code}')
    except Exception as exc:
        return EmailSendResult(provider='mailgun', status='failed', error=str(exc))


def send_email_message(*, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> EmailSendResult:
    provider = email_provider()
    if provider == 'smtp':
        host = os.getenv('SMTP_HOST')
        port = int(os.getenv('SMTP_PORT', '587'))
        username = os.getenv('SMTP_USERNAME')
        password = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('SMTP_FROM_EMAIL', username or 'noreply@example.com')
        if _dry_run_enabled():
            return _fake_send('smtp')
        if not host:
            return EmailSendResult(provider='smtp', status='failed', error='SMTP_HOST not configured')
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype='html')
        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
            return EmailSendResult(provider='smtp', status='sent', message_id=msg.get('Message-ID') or f'smtp_{secrets.token_hex(8)}')
        except Exception as exc:
            return EmailSendResult(provider='smtp', status='failed', error=str(exc))
    if provider == 'resend':
        return _send_via_resend(to_email=to_email, subject=subject, body_text=body_text, body_html=body_html)
    if provider == 'mailgun':
        return _send_via_mailgun(to_email=to_email, subject=subject, body_text=body_text, body_html=body_html)
    return EmailSendResult(provider='mock', status='sent', message_id=f'mock_{secrets.token_hex(8)}')

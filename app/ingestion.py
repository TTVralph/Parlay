from __future__ import annotations

import json
import re
from typing import Any

NOISE_PREFIXES = (
    'parlay', 'sgp', 'same game parlay', 'slip', 'ticket', 'bet slip', 'tail or fade',
    'lock', 'lotd', 'my play', 'play:', 'picks:', 'free play', 'sprinkle', 'ladder'
)

ODDS_RE = re.compile(r'^[+\-]\d{2,4}$')
HANDLE_RE = re.compile(r'@[A-Za-z0-9_]{1,15}')
HASHTAG_RE = re.compile(r'#[A-Za-z0-9_]+')
URL_RE = re.compile(r'https?://\S+')
BULLET_RE = re.compile(r'^[\-•*]+\s*')


def strip_social_noise(text: str) -> str:
    text = URL_RE.sub(' ', text)
    text = HANDLE_RE.sub(' ', text)
    text = HASHTAG_RE.sub(' ', text)
    text = text.replace('\r', '\n')
    text = re.sub(r'[|]+', '\n', text)
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = BULLET_RE.sub('', raw_line).strip()
        if not line:
            continue
        if line.lower() in NOISE_PREFIXES:
            continue
        if ODDS_RE.match(line):
            continue
        if line.lower().startswith('risk ') or line.lower().startswith('to win '):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()


def flatten_tweet_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ('text', 'note_text', 'quoted_text'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    media_text = payload.get('media_text')
    if isinstance(media_text, list):
        parts.extend(str(item).strip() for item in media_text if str(item).strip())
    return '\n'.join(parts).strip()


def build_tweet_source_ref(payload: dict[str, Any]) -> str | None:
    tweet_id = payload.get('tweet_id') or payload.get('id')
    username = payload.get('username') or payload.get('author_handle')
    if tweet_id and username:
        return f'https://x.com/{username}/status/{tweet_id}'
    if tweet_id:
        return str(tweet_id)
    return None


def normalize_tweet_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_text = flatten_tweet_text(payload)
    cleaned_text = strip_social_noise(raw_text)
    return {
        'source_type': 'tweet',
        'source_ref': build_tweet_source_ref(payload),
        'raw_payload': payload,
        'raw_text': raw_text,
        'cleaned_text': cleaned_text,
    }


def dump_source_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

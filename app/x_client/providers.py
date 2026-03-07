from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .base import TweetPayload, XClient

SAMPLE_TWEETS: dict[str, dict[str, Any]] = {
    'demo-1': {
        'tweet_id': 'demo-1',
        'username': 'capperx',
        'text': 'PARLAY\nDenver ML\nJokic 25+ pts\n+145',
        'posted_at': '2026-03-07T18:15:00',
    },
    'demo-review': {
        'tweet_id': 'demo-review',
        'username': 'weirdslips',
        'text': 'PARLAY\nUnknown Guy 27.5 pts\n+340',
        'posted_at': '2026-03-07T18:15:00',
    },
    'watch-1': {
        'tweet_id': 'watch-1',
        'username': 'watchcapper',
        'text': 'PARLAY\nDenver ML\nJokic 25+ pts\n+140',
        'posted_at': '2026-03-07T18:00:00',
    },
    'watch-2': {
        'tweet_id': 'watch-2',
        'username': 'watchcapper',
        'text': 'PARLAY\nUnknown Guy 27.5 pts\n+340',
        'posted_at': '2026-03-07T19:00:00',
    },
}


class MockXClient:
    provider_name = 'mock'

    def __init__(self) -> None:
        fixture_path = os.getenv('X_MOCK_TWEETS_PATH')
        self._tweets = dict(SAMPLE_TWEETS)
        if fixture_path and Path(fixture_path).exists():
            with open(fixture_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._tweets.update(data)

    def _row_to_payload(self, row: dict[str, Any]) -> TweetPayload:
        posted_at = row.get('posted_at')
        return TweetPayload(
            tweet_id=str(row['tweet_id']),
            username=row.get('username'),
            text=row.get('text', ''),
            quoted_text=row.get('quoted_text'),
            note_text=row.get('note_text'),
            media_text=list(row.get('media_text', [])),
            posted_at=datetime.fromisoformat(posted_at) if posted_at else None,
            raw_payload=row,
        )

    def fetch_tweet(self, tweet_id: str) -> TweetPayload:
        row = self._tweets.get(tweet_id)
        if not row:
            raise KeyError(f'Mock tweet {tweet_id} not found')
        return self._row_to_payload(row)

    def fetch_user_recent(self, username: str, max_results: int = 5) -> list[TweetPayload]:
        username_key = username.lower().lstrip('@')
        rows = [row for row in self._tweets.values() if str(row.get('username', '')).lower() == username_key]
        rows.sort(key=lambda row: row.get('posted_at', ''), reverse=True)
        return [self._row_to_payload(row) for row in rows[:max_results]]


class TwitterApiV2Client:
    provider_name = 'api_v2'

    def __init__(self) -> None:
        token = os.getenv('X_BEARER_TOKEN')
        if not token:
            raise RuntimeError('X_BEARER_TOKEN is required for api_v2 X provider')
        self._token = token
        self._base_url = os.getenv('X_API_BASE_URL', 'https://api.x.com/2')

    def _headers(self) -> dict[str, str]:
        return {'Authorization': f'Bearer {self._token}'}

    def _parse_tweet(self, payload: dict[str, Any]) -> TweetPayload:
        data = payload.get('data') or {}
        includes = payload.get('includes') or {}
        users = {item.get('id'): item for item in includes.get('users', [])}
        media = {item.get('media_key'): item for item in includes.get('media', [])}
        username = users.get(data.get('author_id'), {}).get('username')
        media_keys = (((data.get('attachments') or {}).get('media_keys')) or [])
        media_text = [media[key].get('alt_text', '') for key in media_keys if media.get(key)]
        note_text = ((data.get('note_tweet') or {}).get('text'))
        created_at = data.get('created_at')
        posted_at = None
        if created_at:
            posted_at = datetime.fromisoformat(created_at.replace('Z', '+00:00')).replace(tzinfo=None)
        return TweetPayload(
            tweet_id=str(data.get('id')),
            username=username,
            text=data.get('text', ''),
            quoted_text=None,
            note_text=note_text,
            media_text=[item for item in media_text if item],
            posted_at=posted_at,
            raw_payload=payload,
        )

    def fetch_tweet(self, tweet_id: str) -> TweetPayload:
        url = f'{self._base_url}/tweets/{tweet_id}'
        params = {
            'expansions': 'author_id,attachments.media_keys',
            'tweet.fields': 'created_at,note_tweet',
            'user.fields': 'username',
            'media.fields': 'alt_text',
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        return self._parse_tweet(payload)

    def fetch_user_recent(self, username: str, max_results: int = 5) -> list[TweetPayload]:
        username_key = username.lower().lstrip('@')
        with httpx.Client(timeout=20.0) as client:
            user_resp = client.get(
                f'{self._base_url}/users/by/username/{username_key}',
                headers=self._headers(),
                params={'user.fields': 'username'},
            )
            user_resp.raise_for_status()
            user_payload = user_resp.json()
            user_id = ((user_payload.get('data') or {}).get('id'))
            if not user_id:
                return []
            timeline_resp = client.get(
                f'{self._base_url}/users/{user_id}/tweets',
                headers=self._headers(),
                params={
                    'max_results': max_results,
                    'expansions': 'author_id,attachments.media_keys',
                    'tweet.fields': 'created_at,note_tweet',
                    'user.fields': 'username',
                    'media.fields': 'alt_text',
                    'exclude': 'replies,retweets',
                },
            )
            timeline_resp.raise_for_status()
            timeline = timeline_resp.json()

        tweets: list[TweetPayload] = []
        includes = timeline.get('includes') or {}
        users = includes.get('users', [])
        media = includes.get('media', [])
        for row in timeline.get('data', []):
            tweets.append(self._parse_tweet({'data': row, 'includes': {'users': users, 'media': media}}))
        return tweets



def get_x_client() -> XClient:
    provider_name = os.getenv('X_PROVIDER', 'mock').lower()
    if provider_name in {'api', 'api_v2', 'twitter', 'x'}:
        return TwitterApiV2Client()
    return MockXClient()

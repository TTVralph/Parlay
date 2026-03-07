from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class TweetPayload:
    tweet_id: str
    username: str | None
    text: str
    posted_at: datetime | None = None
    quoted_text: str | None = None
    note_text: str | None = None
    media_text: list[str] = field(default_factory=list)
    raw_payload: dict | None = None

    def to_ingest_payload(self) -> dict:
        return {
            'tweet_id': self.tweet_id,
            'username': self.username,
            'text': self.text,
            'quoted_text': self.quoted_text,
            'note_text': self.note_text,
            'media_text': self.media_text,
            'posted_at': self.posted_at,
        }


class XClient(Protocol):
    provider_name: str

    def fetch_tweet(self, tweet_id: str) -> TweetPayload: ...

    def fetch_user_recent(self, username: str, max_results: int = 5) -> list[TweetPayload]: ...

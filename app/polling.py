from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .grader import grade_text
from .ingestion import dump_source_payload, normalize_tweet_payload
from .services.repository import (
    create_poll_run,
    enqueue_review_if_needed,
    save_graded_ticket,
    update_watched_account_poll_state,
)
from .x_client.base import TweetPayload


def poll_account_once(db: Session, account, x_client, max_tweets: int = 5):
    tweets: list[TweetPayload] = x_client.fetch_user_recent(account.username, max_results=max_tweets)
    saved = 0
    newest_source_ref: str | None = None
    for tweet in tweets:
        if account.last_seen_source_ref and f"{account.username}:{tweet.tweet_id}" == account.last_seen_source_ref:
            break
        payload = tweet.to_ingest_payload()
        normalized = normalize_tweet_payload(payload)
        result = grade_text(normalized['cleaned_text'], posted_at=tweet.posted_at)
        ticket = save_graded_ticket(
            db,
            normalized['cleaned_text'],
            result,
            posted_at=tweet.posted_at,
            source_type='tweet',
            source_ref=normalized['source_ref'],
            source_payload_json=dump_source_payload(tweet.raw_payload or payload),
        )
        enqueue_review_if_needed(db, ticket, result)
        saved += 1
        newest_source_ref = newest_source_ref or normalized['source_ref']

    update_watched_account_poll_state(db, account, source_ref=newest_source_ref)
    return create_poll_run(
        db,
        username=account.username,
        status='success',
        fetched_count=len(tweets),
        saved_count=saved,
        detail=f'Polled at {datetime.utcnow().isoformat()} and saved {saved} ticket(s)',
        watched_account_id=account.id,
    )

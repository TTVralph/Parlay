from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from .db.session import SessionLocal
from .services.repository import create_poll_run, get_due_watched_accounts
from .polling import poll_account_once
from .x_client import get_x_client


@dataclass
class SchedulerConfig:
    enabled: bool
    interval_seconds: int


def get_scheduler_config() -> SchedulerConfig:
    enabled = os.getenv('POLL_SCHEDULER_ENABLED', 'false').lower() in {'1', 'true', 'yes'}
    interval_seconds = int(os.getenv('POLL_SCHEDULER_INTERVAL_SECONDS', '60'))
    return SchedulerConfig(enabled=enabled, interval_seconds=interval_seconds)


def run_due_polls_once() -> list:
    db = SessionLocal()
    try:
        due = get_due_watched_accounts(db)
        runs = []
        x_client = get_x_client()
        for account in due:
            try:
                runs.append(poll_account_once(db, account, x_client=x_client, max_tweets=5))
            except Exception as exc:
                runs.append(create_poll_run(db, username=account.username, status='error', fetched_count=0, saved_count=0, detail=str(exc), watched_account_id=account.id))
        return runs
    finally:
        db.close()


_STOP = False
_THREAD = None


def scheduler_loop() -> None:
    cfg = get_scheduler_config()
    while not _STOP:
        run_due_polls_once()
        time.sleep(max(cfg.interval_seconds, 5))


def start_scheduler_thread() -> None:
    global _THREAD
    cfg = get_scheduler_config()
    if not cfg.enabled or _THREAD is not None:
        return
    _THREAD = threading.Thread(target=scheduler_loop, daemon=True, name='poll-scheduler')
    _THREAD.start()

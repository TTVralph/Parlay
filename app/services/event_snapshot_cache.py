from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
import threading
import time
from typing import Callable

from app.services.event_snapshot import EventSnapshot


@dataclass
class _CacheEntry:
    snapshot: EventSnapshot
    expires_at: float


class EventSnapshotCache:
    """In-memory cache for event snapshots keyed by (sport, event_id)."""

    def __init__(
        self,
        *,
        live_ttl_seconds: int = 30,
        recently_finished_ttl_seconds: int = 600,
        historical_ttl_seconds: int = 86400,
        enabled: bool | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._live_ttl_seconds = int(live_ttl_seconds)
        self._recently_finished_ttl_seconds = int(recently_finished_ttl_seconds)
        self._historical_ttl_seconds = int(historical_ttl_seconds)
        self._enabled = enabled if enabled is not None else not self._env_disables_cache()
        self._now_fn = now_fn or time.time

        self._entries: dict[tuple[str, str], _CacheEntry] = {}
        self._in_flight: dict[tuple[str, str], threading.Event] = {}
        self._lock = threading.Lock()

        self._hits = 0
        self._misses = 0
        self._last_ttl: int | None = None

    @staticmethod
    def _env_disables_cache() -> bool:
        value = str(os.getenv('PARLAY_DISABLE_EVENT_SNAPSHOT_CACHE', '')).strip().lower()
        return value in {'1', 'true', 'yes', 'on'}

    @staticmethod
    def _normalized_key(sport: str | None, event_id: str) -> tuple[str, str]:
        return (str(sport or '').strip().upper() or 'UNKNOWN', str(event_id or '').strip())

    @staticmethod
    def _status_bucket(status: str | None) -> str:
        normalized = str(status or '').strip().lower()
        if normalized in {'live', 'in', 'in_progress', 'inprogress', 'halftime'}:
            return 'live'
        if normalized in {'final', 'complete', 'completed', 'closed', 'settled', 'post'}:
            return 'final'
        return 'other'

    @staticmethod
    def _parse_event_date(event_date: str | None) -> date | None:
        if not event_date:
            return None
        try:
            return datetime.fromisoformat(str(event_date).replace('Z', '+00:00')).date()
        except ValueError:
            return None

    def _ttl_for_snapshot(self, snapshot: EventSnapshot | None) -> int:
        if snapshot is None:
            return self._live_ttl_seconds
        status_bucket = self._status_bucket(snapshot.event_status)
        if status_bucket == 'live':
            return self._live_ttl_seconds
        if status_bucket == 'final':
            event_day = self._parse_event_date(snapshot.event_date)
            if event_day is None:
                return self._recently_finished_ttl_seconds
            today_utc = datetime.now(timezone.utc).date()
            days_old = (today_utc - event_day).days
            if days_old <= 1:
                return self._recently_finished_ttl_seconds
            return self._historical_ttl_seconds
        return self._recently_finished_ttl_seconds

    def _purge_expired_locked(self) -> None:
        now = self._now_fn()
        expired = [key for key, value in self._entries.items() if value.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    def get_snapshot(
        self,
        *,
        sport: str | None,
        event_id: str,
        include_play_by_play: bool,
        fetcher: Callable[[], EventSnapshot | None],
    ) -> EventSnapshot | None:
        if not self._enabled:
            return fetcher()
        key = self._normalized_key(sport, event_id)

        with self._lock:
            self._purge_expired_locked()
            cached = self._entries.get(key)
            if cached is not None:
                if include_play_by_play and cached.snapshot.normalized_play_by_play is None:
                    pass
                else:
                    self._hits += 1
                    return cached.snapshot

            waiter = self._in_flight.get(key)
            if waiter is None:
                waiter = threading.Event()
                self._in_flight[key] = waiter
                producer = True
                self._misses += 1
            else:
                producer = False

        if not producer:
            waiter.wait()
            with self._lock:
                self._purge_expired_locked()
                cached = self._entries.get(key)
                if cached is not None:
                    if include_play_by_play and cached.snapshot.normalized_play_by_play is None:
                        return fetcher()
                    self._hits += 1
                    return cached.snapshot
            return fetcher()

        try:
            snapshot = fetcher()
            ttl = self._ttl_for_snapshot(snapshot)
            with self._lock:
                self._last_ttl = ttl
                if snapshot is not None:
                    self._entries[key] = _CacheEntry(snapshot=snapshot, expires_at=self._now_fn() + ttl)
            return snapshot
        finally:
            with self._lock:
                complete = self._in_flight.pop(key, None)
                if complete is not None:
                    complete.set()

    def get_stats(self) -> dict[str, int | None]:
        with self._lock:
            self._purge_expired_locked()
            return {
                'snapshot_cache_hits': self._hits,
                'snapshot_cache_misses': self._misses,
                'snapshot_cache_ttl': self._last_ttl,
                'snapshot_cache_size': len(self._entries),
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._in_flight.clear()
            self._hits = 0
            self._misses = 0
            self._last_ttl = None


_EVENT_SNAPSHOT_CACHE: EventSnapshotCache | None = None


def get_event_snapshot_cache() -> EventSnapshotCache:
    global _EVENT_SNAPSHOT_CACHE
    if _EVENT_SNAPSHOT_CACHE is None:
        _EVENT_SNAPSHOT_CACHE = EventSnapshotCache()
    return _EVENT_SNAPSHOT_CACHE

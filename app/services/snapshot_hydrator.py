from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any

from app.services.daily_event_manifest import DailyEventManifestService
from app.services.event_snapshot import EventSnapshotService


@dataclass
class HydrationSummary:
    events_seen: int = 0
    snapshots_built: int = 0
    snapshots_reused: int = 0
    snapshots_persisted: int = 0
    skipped_stale_or_unneeded: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class SnapshotHydrator:
    """Background-style snapshot prebuilder driven by daily manifests."""

    def __init__(
        self,
        *,
        daily_manifest_service: DailyEventManifestService | None = None,
        event_snapshot_service: EventSnapshotService | None = None,
        hydrate_live_events: bool = True,
    ) -> None:
        self._daily_manifest_service = daily_manifest_service or DailyEventManifestService()
        self._event_snapshot_service = event_snapshot_service or EventSnapshotService()
        self._hydrate_live_events = hydrate_live_events

    @staticmethod
    def _status_bucket(status: str | None) -> str:
        normalized = str(status or '').strip().lower()
        if normalized in {'final', 'complete', 'completed', 'closed', 'settled', 'post'}:
            return 'final'
        if normalized in {'live', 'in', 'in_progress', 'inprogress', 'halftime'}:
            return 'live'
        if normalized in {'postponed', 'cancelled', 'canceled'}:
            return 'postponed_or_cancelled'
        if normalized in {'pre', 'scheduled', 'pregame'}:
            return 'scheduled'
        return 'unknown'

    def should_hydrate_event(self, event_manifest_entry: dict[str, Any]) -> bool:
        status = self._status_bucket(str(event_manifest_entry.get('game_status') or ''))
        if status == 'final':
            return True
        if status == 'live':
            return self._hydrate_live_events
        if status == 'postponed_or_cancelled':
            return False
        return status in {'scheduled', 'unknown'}

    def hydrate_date(self, sport: str, date_value: str | date | datetime) -> dict[str, int]:
        summary = HydrationSummary()
        manifest = self._daily_manifest_service.get_daily_manifest(sport, date_value)
        if not manifest:
            return summary.to_dict()

        for event in manifest.get('events') or []:
            summary.events_seen += 1
            if not isinstance(event, dict) or not self.should_hydrate_event(event):
                summary.skipped_stale_or_unneeded += 1
                continue

            event_id = str(event.get('event_id') or '').strip()
            if not event_id:
                summary.skipped_stale_or_unneeded += 1
                continue

            event_date = event.get('date') or manifest.get('date')
            self._hydrate_one(event_id=event_id, event_date=event_date, summary=summary)

        return summary.to_dict()

    def hydrate_events(self, event_ids: list[str]) -> dict[str, int]:
        summary = HydrationSummary()
        for raw_event_id in event_ids:
            summary.events_seen += 1
            event_id = str(raw_event_id or '').strip()
            if not event_id:
                summary.skipped_stale_or_unneeded += 1
                continue
            self._hydrate_one(event_id=event_id, event_date=None, summary=summary)
        return summary.to_dict()

    def _hydrate_one(self, *, event_id: str, event_date: str | None, summary: HydrationSummary) -> None:
        cached_before = self._event_snapshot_service._snapshots.get(event_id)  # noqa: SLF001
        cached_before_is_fresh = bool(
            cached_before
            and self._event_snapshot_service.is_snapshot_fresh(cached_before, cached_before.event_status)
        )

        persisted_before = self._event_snapshot_service._snapshot_store.load_snapshot(event_id)  # noqa: SLF001

        try:
            snapshot = self._event_snapshot_service.get_event_snapshot(event_id, event_date=event_date)
        except Exception:
            summary.errors += 1
            return

        if snapshot is None:
            summary.errors += 1
            return

        reused = cached_before_is_fresh or snapshot.snapshot_origin == 'persisted'
        if reused:
            summary.snapshots_reused += 1
            return

        summary.snapshots_built += 1
        if self._event_snapshot_service.should_persist_snapshot(snapshot) and persisted_before is None:
            summary.snapshots_persisted += 1

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from typing import TYPE_CHECKING

from app.services.play_by_play_provider import PlayByPlayEvent

if TYPE_CHECKING:
    from app.services.event_snapshot import EventSnapshot


class SnapshotStore:
    """Simple local JSON persistence for finalized event snapshots."""

    def __init__(self, base_dir: str | Path = 'data/snapshots') -> None:
        self._base_dir = Path(base_dir)

    def _path_for(self, event_id: str) -> Path:
        return self._base_dir / f'{event_id}.json'

    def snapshot_exists(self, event_id: str) -> bool:
        return self._path_for(event_id).exists()

    def load_snapshot(self, event_id: str) -> "EventSnapshot" | None:
        path = self._path_for(event_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return self._snapshot_from_payload(payload)

    def save_snapshot(self, event_id: str, snapshot: "EventSnapshot") -> None:
        path = self._path_for(event_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._snapshot_to_payload(snapshot)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')

    def _snapshot_to_payload(self, snapshot: "EventSnapshot") -> dict[str, Any]:
        return {
            'event_id': snapshot.event_id,
            'sport': snapshot.sport,
            'league': snapshot.league,
            'event_date': snapshot.event_date,
            'event_status': snapshot.event_status,
            'home_team': snapshot.home_team,
            'away_team': snapshot.away_team,
            'normalized_player_stats': snapshot.normalized_player_stats,
            'normalized_team_stats': snapshot.normalized_team_map,
            'metadata': {
                'raw_scoreboard_event': snapshot.raw_scoreboard_event,
                'raw_summary': snapshot.raw_summary,
                'raw_play_by_play': snapshot.raw_play_by_play,
            },
            'normalized_play_by_play': [asdict(event) for event in (snapshot.normalized_play_by_play or [])],
            'diagnostics': asdict(snapshot.diagnostics),
        }

    def _snapshot_from_payload(self, payload: dict[str, Any]) -> "EventSnapshot" | None:
        event_id = str(payload.get('event_id') or '').strip()
        if not event_id:
            return None
        metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
        raw_pbp = payload.get('normalized_play_by_play')
        normalized_play_by_play = None
        if isinstance(raw_pbp, list):
            normalized_play_by_play = []
            for item in raw_pbp:
                if not isinstance(item, dict):
                    continue
                try:
                    normalized_play_by_play.append(PlayByPlayEvent(**item))
                except TypeError:
                    continue

        from app.services.event_snapshot import EventSnapshot, SnapshotDiagnostics

        diagnostics_payload = payload.get('diagnostics') if isinstance(payload.get('diagnostics'), dict) else {}
        diagnostics = SnapshotDiagnostics(
            available_player_ids=list(diagnostics_payload.get('available_player_ids') or []),
            available_stat_keys=list(diagnostics_payload.get('available_stat_keys') or []),
            missing_player_stats=list(diagnostics_payload.get('missing_player_stats') or []),
            missing_stat_keys=list(diagnostics_payload.get('missing_stat_keys') or []),
            snapshot_build_sources=dict(diagnostics_payload.get('snapshot_build_sources') or {}),
        )
        return EventSnapshot(
            event_id=event_id,
            sport=payload.get('sport'),
            league=payload.get('league'),
            event_date=payload.get('event_date'),
            event_status=payload.get('event_status'),
            home_team=payload.get('home_team') or {},
            away_team=payload.get('away_team') or {},
            raw_scoreboard_event=metadata.get('raw_scoreboard_event'),
            raw_summary=metadata.get('raw_summary'),
            raw_play_by_play=metadata.get('raw_play_by_play'),
            normalized_player_stats=payload.get('normalized_player_stats') or {},
            normalized_team_map=payload.get('normalized_team_stats') or {},
            normalized_play_by_play=normalized_play_by_play,
            diagnostics=diagnostics,
        )

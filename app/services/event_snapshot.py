from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from app.services.gamecast_provider import ESPNGamecastProvider
from app.services.play_by_play_provider import ESPNPlayByPlayProvider, PlayByPlayEvent
from app.services.scoreboard_provider import ESPNScoreboardProvider
from app.services.snapshot_store import SnapshotStore


@dataclass
class SnapshotDiagnostics:
    available_player_ids: list[str] = field(default_factory=list)
    available_stat_keys: list[str] = field(default_factory=list)
    missing_player_stats: list[str] = field(default_factory=list)
    missing_stat_keys: list[str] = field(default_factory=list)
    snapshot_build_sources: dict[str, bool] = field(default_factory=dict)
    event_status: str | None = None
    built_at: str | None = None
    persisted_at: str | None = None
    snapshot_origin: str | None = None
    period_data_present: bool = False
    available_period_labels: list[str] = field(default_factory=list)
    period_scores_complete_by_label: dict[str, bool] = field(default_factory=dict)
    period_extraction_source: str | None = None


@dataclass
class EventSnapshot:
    event_id: str
    sport: str | None = None
    league: str | None = None
    event_date: str | None = None
    event_status: str | None = None
    home_team: dict[str, Any] = field(default_factory=dict)
    away_team: dict[str, Any] = field(default_factory=dict)
    raw_scoreboard_event: dict[str, Any] | None = None
    raw_summary: dict[str, Any] | None = None
    raw_play_by_play: dict[str, Any] | None = None
    normalized_player_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    normalized_team_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    normalized_event_result: dict[str, Any] = field(default_factory=dict)
    normalized_period_results: list[dict[str, Any]] = field(default_factory=list)
    normalized_play_by_play: list[PlayByPlayEvent] | None = None
    built_at: str | None = None
    persisted_at: str | None = None
    snapshot_origin: str | None = None
    diagnostics: SnapshotDiagnostics = field(default_factory=SnapshotDiagnostics)

    def get_stat_coverage(self) -> dict[str, Any]:
        stat_keys: set[str] = set()
        missing_stats: dict[str, list[str]] = {}
        for entry in self.normalized_player_stats.values():
            player_name = str(entry.get('display_name') or entry.get('player_id') or 'unknown')
            stats = entry.get('stats') or {}
            stat_keys.update(str(key) for key in stats.keys())
            if not stats:
                missing_stats[player_name] = []

        sources = self.diagnostics.snapshot_build_sources
        snapshot_source = 'summary'
        if sources.get('summary') and sources.get('boxscore') and sources.get('pbp'):
            snapshot_source = 'summary+boxscore+pbp'
        elif sources.get('summary') and sources.get('boxscore'):
            snapshot_source = 'summary+boxscore'
        elif sources.get('pbp'):
            snapshot_source = 'pbp'

        return {
            'players': len(self.normalized_player_stats),
            'stat_keys': sorted(stat_keys),
            'missing_stats': missing_stats,
            'snapshot_source': snapshot_source,
        }


class EventSnapshotService:
    """Composes provider outputs into one reusable per-event snapshot."""

    def __init__(
        self,
        *,
        scoreboard_provider: ESPNScoreboardProvider | None = None,
        gamecast_provider: ESPNGamecastProvider | None = None,
        play_by_play_provider: ESPNPlayByPlayProvider | None = None,
        snapshot_store: SnapshotStore | None = None,
        scheduled_freshness_seconds: int = 60,
        live_freshness_seconds: int = 20,
    ) -> None:
        self._scoreboard_provider = scoreboard_provider or ESPNScoreboardProvider()
        self._gamecast_provider = gamecast_provider or ESPNGamecastProvider()
        self._play_by_play_provider = play_by_play_provider or ESPNPlayByPlayProvider()
        self._snapshot_store = snapshot_store or SnapshotStore()
        self._snapshots: dict[str, EventSnapshot] = {}
        self._scheduled_freshness_seconds = scheduled_freshness_seconds
        self._live_freshness_seconds = live_freshness_seconds

    @staticmethod
    def _is_final_status(status: str | None) -> bool:
        return str(status or '').strip().lower() in {'final', 'complete', 'completed', 'closed', 'settled'}

    @staticmethod
    def _status_bucket(status: str | None) -> str:
        normalized = str(status or '').strip().lower()
        if normalized in {'live', 'in', 'in_progress', 'inprogress', 'halftime'}:
            return 'live'
        if normalized in {'pre', 'scheduled', 'pregame'}:
            return 'scheduled'
        if normalized in {'postponed', 'cancelled', 'canceled'}:
            return 'postponed_or_cancelled'
        if EventSnapshotService._is_final_status(normalized):
            return 'final'
        return 'unknown'

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _norm_name(value: str) -> str:
        return re.sub(r'[^a-z0-9]', '', value.lower())

    @staticmethod
    def _parse_event_date(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
        except ValueError:
            return value

    def _scoreboard_event_for(self, event_id: str, event_date: str | None = None) -> dict[str, Any] | None:
        if not event_date:
            return None
        events = self._scoreboard_provider.fetch_events_for_date(event_date)
        return next((event for event in events if str(event.get('event_id')) == event_id), None)

    @staticmethod
    def _extract_status_from_scoreboard_event(scoreboard_event: dict[str, Any] | None) -> str | None:
        if not scoreboard_event:
            return None
        for key in ('event_status', 'status', 'state'):
            value = scoreboard_event.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                for nested_key in ('state', 'type', 'name'):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        return nested
        return None

    def is_snapshot_fresh(self, snapshot: EventSnapshot, event_status: str | None) -> bool:
        status_bucket = self._status_bucket(event_status)
        if status_bucket == 'final':
            return True
        if status_bucket == 'postponed_or_cancelled':
            return False
        built_at = self._parse_iso(snapshot.built_at)
        if built_at is None:
            return False
        age_seconds = (datetime.now(timezone.utc) - built_at).total_seconds()
        if status_bucket == 'live':
            return age_seconds <= self._live_freshness_seconds
        if status_bucket == 'scheduled':
            return age_seconds <= self._scheduled_freshness_seconds
        return age_seconds <= self._scheduled_freshness_seconds

    def should_persist_snapshot(self, snapshot: EventSnapshot) -> bool:
        return self._status_bucket(snapshot.event_status) == 'final'

    def _hydrate_snapshot_metadata(self, snapshot: EventSnapshot, *, origin: str, persisted_at: str | None = None) -> EventSnapshot:
        snapshot.snapshot_origin = origin
        snapshot.persisted_at = persisted_at
        snapshot.diagnostics.event_status = snapshot.event_status
        snapshot.diagnostics.built_at = snapshot.built_at
        snapshot.diagnostics.persisted_at = persisted_at
        snapshot.diagnostics.snapshot_origin = origin
        return snapshot

    def _persisted_snapshot_has_status_mismatch(
        self,
        *,
        persisted_snapshot: EventSnapshot,
        event_date: str | None,
    ) -> bool:
        if not self._is_final_status(persisted_snapshot.event_status):
            return True
        scoreboard_event = self._scoreboard_event_for(persisted_snapshot.event_id, event_date=event_date)
        live_status = self._extract_status_from_scoreboard_event(scoreboard_event)
        return bool(live_status and self._status_bucket(live_status) != 'final')

    def _team_maps_from_summary(self, summary: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
        if not summary:
            return {}, {}, {}
        competitions = ((summary.get('header') or {}).get('competitions') or [])
        competition = competitions[0] if competitions else {}
        competitors = competition.get('competitors') or []
        home = next((c for c in competitors if c.get('homeAway') == 'home'), {})
        away = next((c for c in competitors if c.get('homeAway') == 'away'), {})

        def _team_obj(raw: dict[str, Any]) -> dict[str, Any]:
            team = raw.get('team') or {}
            return {
                'id': str(team.get('id') or '').strip() or None,
                'name': str(team.get('displayName') or team.get('name') or '').strip() or None,
                'abbr': str(team.get('abbreviation') or '').strip() or None,
                'score': raw.get('score'),
            }

        home_obj = _team_obj(home)
        away_obj = _team_obj(away)
        team_map: dict[str, dict[str, Any]] = {}
        for team_obj in (home_obj, away_obj):
            for key in (team_obj.get('id'), team_obj.get('abbr'), team_obj.get('name')):
                if key:
                    team_map[str(key)] = team_obj
        return home_obj, away_obj, team_map

    @staticmethod
    def _coerce_score(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    def _normalized_event_result(
        self,
        *,
        event_status: str | None,
        home_team: dict[str, Any],
        away_team: dict[str, Any],
    ) -> dict[str, Any]:
        home_score = self._coerce_score(home_team.get('score'))
        away_score = self._coerce_score(away_team.get('score'))
        margin = (home_score - away_score) if home_score is not None and away_score is not None else None
        winner = None
        if margin is not None and margin != 0:
            winner = 'home' if margin > 0 else 'away'
        combined_total = (home_score + away_score) if home_score is not None and away_score is not None else None
        return {
            'event_status': event_status,
            'is_final': self._is_final_status(event_status),
            'home_team_id': home_team.get('id'),
            'away_team_id': away_team.get('id'),
            'home_team_name': home_team.get('name'),
            'away_team_name': away_team.get('name'),
            'home_team_abbr': home_team.get('abbr'),
            'away_team_abbr': away_team.get('abbr'),
            'home_score': home_score,
            'away_score': away_score,
            'winner': winner,
            'margin': margin,
            'combined_total': combined_total,
        }

    def _normalized_period_results(
        self,
        *,
        summary: dict[str, Any] | None,
        scoreboard_event: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        competitions = ((summary or {}).get('header') or {}).get('competitions') or []
        competition = competitions[0] if competitions else {}
        competitors = competition.get('competitors') or []
        home = next((entry for entry in competitors if entry.get('homeAway') == 'home'), {})
        away = next((entry for entry in competitors if entry.get('homeAway') == 'away'), {})

        home_linescores = home.get('linescores') or []
        away_linescores = away.get('linescores') or []

        source = None
        if home_linescores or away_linescores:
            source = 'summary_competitor_linescores'
        else:
            home_linescores = (scoreboard_event or {}).get('home_linescores') or []
            away_linescores = (scoreboard_event or {}).get('away_linescores') or []
            if home_linescores or away_linescores:
                source = 'scoreboard_event_linescores'

        period_count = max(len(home_linescores), len(away_linescores))
        if period_count <= 0:
            return [], None

        normalized: list[dict[str, Any]] = []
        running_home = 0
        running_away = 0
        cumulative_available = True
        for index in range(period_count):
            home_raw = home_linescores[index] if index < len(home_linescores) else None
            away_raw = away_linescores[index] if index < len(away_linescores) else None
            home_value = self._coerce_score((home_raw or {}).get('value')) if isinstance(home_raw, dict) else self._coerce_score(home_raw)
            away_value = self._coerce_score((away_raw or {}).get('value')) if isinstance(away_raw, dict) else self._coerce_score(away_raw)
            if home_value is None or away_value is None:
                cumulative_available = False
            else:
                running_home += home_value
                running_away += away_value

            period_number = index + 1
            label_candidates = []
            if isinstance(home_raw, dict):
                label_candidates.extend([home_raw.get('displayValue'), home_raw.get('period')])
            if isinstance(away_raw, dict):
                label_candidates.extend([away_raw.get('displayValue'), away_raw.get('period')])
            label = next((str(value).strip() for value in label_candidates if str(value or '').strip()), str(period_number))

            period_total = (home_value + away_value) if home_value is not None and away_value is not None else None
            normalized.append(
                {
                    'period_number': period_number,
                    'period_label': label,
                    'home_score': home_value,
                    'away_score': away_value,
                    'combined_total': period_total,
                    'cumulative_home_score': running_home if cumulative_available else None,
                    'cumulative_away_score': running_away if cumulative_available else None,
                    'is_score_complete': home_value is not None and away_value is not None,
                    'source': source,
                    'source_metadata': {
                        'home_linescore_raw': home_raw,
                        'away_linescore_raw': away_raw,
                    },
                }
            )
        return normalized, source

    def _player_stats_from_summary(self, summary: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not summary:
            return {}
        players: dict[str, dict[str, Any]] = {}
        box_players = ((summary.get('boxscore') or {}).get('players') or [])
        for team_block in box_players:
            team_name = str((team_block.get('team') or {}).get('displayName') or '').strip() or None
            for stat_block in team_block.get('statistics') or []:
                labels = [str(x or '').strip() for x in (stat_block.get('labels') or [])]
                for athlete_row in stat_block.get('athletes') or []:
                    athlete_obj = athlete_row.get('athlete') or {}
                    display_name = str(athlete_obj.get('displayName') or '').strip()
                    if not display_name:
                        continue
                    key = self._norm_name(display_name)
                    entry = players.setdefault(
                        key,
                        {
                            'player_id': str(athlete_obj.get('id') or '').strip() or None,
                            'display_name': display_name,
                            'team': team_name,
                            'stats': {},
                        },
                    )
                    stats = athlete_row.get('stats') or []
                    for idx, label in enumerate(labels):
                        if not label or idx >= len(stats):
                            continue
                        entry['stats'][label] = stats[idx]

        for entry in players.values():
            stats = entry.get('stats') or {}
            values: dict[str, float] = {}
            for key, raw in stats.items():
                text = str(raw).strip()
                if not text or text == '--':
                    continue
                if '-' in text and key.lower() in {'3pt made', '3pt field goals made', 'threes made'}:
                    text = text.split('-', 1)[0]
                try:
                    values[key] = float(text)
                except ValueError:
                    continue
            pts = values.get('PTS') or values.get('points')
            reb = values.get('REB') or values.get('rebounds')
            ast = values.get('AST') or values.get('assists')
            if pts is not None and reb is not None:
                entry['stats']['PR'] = float(pts + reb)
            if pts is not None and ast is not None:
                entry['stats']['PA'] = float(pts + ast)
            if reb is not None and ast is not None:
                entry['stats']['RA'] = float(reb + ast)
            if pts is not None and reb is not None and ast is not None:
                entry['stats']['PRA'] = float(pts + reb + ast)

        return players

    def build_event_snapshot(
        self,
        event_id: str,
        *,
        event_date: str | None = None,
        include_play_by_play: bool = False,
    ) -> EventSnapshot | None:
        normalized_event_id = str(event_id or '').strip()
        if not normalized_event_id:
            return None
        existing = self._snapshots.get(normalized_event_id)
        if existing is not None:
            if not self.is_snapshot_fresh(existing, existing.event_status):
                self._snapshots.pop(normalized_event_id, None)
            else:
                self._hydrate_snapshot_metadata(existing, origin=existing.snapshot_origin or 'rebuilt', persisted_at=existing.persisted_at)
                if include_play_by_play and existing.normalized_play_by_play is None:
                    existing.normalized_play_by_play = self._play_by_play_provider.get_normalized_events(normalized_event_id)
                    existing.diagnostics.snapshot_build_sources['pbp'] = bool(existing.normalized_play_by_play)
                    if self.should_persist_snapshot(existing):
                        existing.persisted_at = self._now_iso()
                        self._snapshot_store.save_snapshot(normalized_event_id, existing)
                        self._hydrate_snapshot_metadata(existing, origin=existing.snapshot_origin or 'rebuilt', persisted_at=existing.persisted_at)
                return existing

        persisted = self._snapshot_store.load_snapshot(normalized_event_id)
        if persisted is not None:
            if not self._persisted_snapshot_has_status_mismatch(persisted_snapshot=persisted, event_date=event_date):
                self._hydrate_snapshot_metadata(
                    persisted,
                    origin='persisted',
                    persisted_at=persisted.persisted_at or self._now_iso(),
                )
                if include_play_by_play and persisted.normalized_play_by_play is None:
                    persisted.normalized_play_by_play = self._play_by_play_provider.get_normalized_events(normalized_event_id)
                    persisted.diagnostics.snapshot_build_sources['pbp'] = bool(persisted.normalized_play_by_play)
                    if self.should_persist_snapshot(persisted):
                        persisted.persisted_at = self._now_iso()
                        self._snapshot_store.save_snapshot(normalized_event_id, persisted)
                        self._hydrate_snapshot_metadata(persisted, origin='persisted', persisted_at=persisted.persisted_at)
                self._snapshots[normalized_event_id] = persisted
                return persisted

        summary_normalized = self._gamecast_provider.fetch_normalized(normalized_event_id)
        summary_raw = summary_normalized.get('raw') if summary_normalized else None
        scoreboard_event = self._scoreboard_event_for(normalized_event_id, event_date=event_date)

        home_team, away_team, team_map = self._team_maps_from_summary(summary_raw)
        player_stats = self._player_stats_from_summary(summary_raw)

        competition_date = None
        if summary_raw:
            competition_date = (((summary_raw.get('header') or {}).get('competitions') or [{}])[0].get('date'))
        event_status = ((summary_normalized or {}).get('status') or {}).get('state') if summary_normalized else None
        snapshot = EventSnapshot(
            event_id=normalized_event_id,
            sport='NBA',
            league='NBA',
            event_date=self._parse_event_date(competition_date or event_date),
            event_status=event_status,
            home_team=home_team,
            away_team=away_team,
            raw_scoreboard_event=scoreboard_event,
            raw_summary=summary_raw,
            raw_play_by_play=summary_raw,
            normalized_player_stats=player_stats,
            normalized_team_map=team_map,
            normalized_event_result=self._normalized_event_result(
                event_status=event_status,
                home_team=home_team,
                away_team=away_team,
            ),
            normalized_period_results=[],
            normalized_play_by_play=None,
            built_at=self._now_iso(),
            persisted_at=None,
            snapshot_origin='rebuilt',
            diagnostics=SnapshotDiagnostics(
                available_player_ids=sorted(
                    {
                        str(entry.get('player_id')).strip()
                        for entry in player_stats.values()
                        if str(entry.get('player_id') or '').strip()
                    }
                ),
                available_stat_keys=sorted(
                    {
                        str(stat_key)
                        for entry in player_stats.values()
                        for stat_key in (entry.get('stats') or {}).keys()
                    }
                ),
                missing_player_stats=sorted(
                    [
                        str(entry.get('display_name') or key)
                        for key, entry in player_stats.items()
                        if not (entry.get('stats') or {})
                    ]
                ),
                missing_stat_keys=[],
                snapshot_build_sources={
                    'summary': summary_raw is not None,
                    'boxscore': bool(((summary_raw or {}).get('boxscore') or {}).get('players')),
                    'pbp': False,
                },
                event_status=event_status,
                built_at=self._now_iso(),
                persisted_at=None,
                snapshot_origin='rebuilt',
            ),
        )
        normalized_period_results, period_source = self._normalized_period_results(
            summary=summary_raw,
            scoreboard_event=scoreboard_event,
        )
        snapshot.normalized_period_results = normalized_period_results
        snapshot.diagnostics.period_data_present = bool(normalized_period_results)
        snapshot.diagnostics.available_period_labels = [
            str(item.get('period_label'))
            for item in normalized_period_results
            if str(item.get('period_label') or '').strip()
        ]
        snapshot.diagnostics.period_scores_complete_by_label = {
            str(item.get('period_label')): bool(item.get('is_score_complete'))
            for item in normalized_period_results
            if str(item.get('period_label') or '').strip()
        }
        snapshot.diagnostics.period_extraction_source = period_source

        if include_play_by_play:
            snapshot.normalized_play_by_play = self._play_by_play_provider.get_normalized_events(normalized_event_id)
            snapshot.diagnostics.snapshot_build_sources['pbp'] = bool(snapshot.normalized_play_by_play)

        self._snapshots[normalized_event_id] = snapshot
        if self.should_persist_snapshot(snapshot):
            snapshot.persisted_at = self._now_iso()
            self._snapshot_store.save_snapshot(normalized_event_id, snapshot)
            self._hydrate_snapshot_metadata(snapshot, origin='rebuilt', persisted_at=snapshot.persisted_at)
        else:
            self._hydrate_snapshot_metadata(snapshot, origin='rebuilt', persisted_at=None)
        return snapshot

    def get_event_snapshot(
        self,
        event_id: str,
        *,
        event_date: str | None = None,
        include_play_by_play: bool = False,
    ) -> EventSnapshot | None:
        return self.build_event_snapshot(
            event_id,
            event_date=event_date,
            include_play_by_play=include_play_by_play,
        )

    def get_many_event_snapshots(
        self,
        event_ids: list[str],
        *,
        event_dates: dict[str, str] | None = None,
        include_play_by_play_event_ids: set[str] | None = None,
    ) -> dict[str, EventSnapshot]:
        snapshots: dict[str, EventSnapshot] = {}
        for event_id in event_ids:
            include_play_by_play = event_id in (include_play_by_play_event_ids or set())
            snapshot = self.build_event_snapshot(
                event_id,
                event_date=(event_dates or {}).get(event_id),
                include_play_by_play=include_play_by_play,
            )
            if snapshot is not None:
                snapshots[event_id] = snapshot
        return snapshots

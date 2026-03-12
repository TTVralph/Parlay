from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

from app.services.gamecast_provider import ESPNGamecastProvider
from app.services.play_by_play_provider import ESPNPlayByPlayProvider, PlayByPlayEvent
from app.services.scoreboard_provider import ESPNScoreboardProvider


@dataclass
class SnapshotDiagnostics:
    available_player_ids: list[str] = field(default_factory=list)
    available_stat_keys: list[str] = field(default_factory=list)
    missing_player_stats: list[str] = field(default_factory=list)
    missing_stat_keys: list[str] = field(default_factory=list)
    snapshot_build_sources: dict[str, bool] = field(default_factory=dict)


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
    normalized_play_by_play: list[PlayByPlayEvent] | None = None
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
    ) -> None:
        self._scoreboard_provider = scoreboard_provider or ESPNScoreboardProvider()
        self._gamecast_provider = gamecast_provider or ESPNGamecastProvider()
        self._play_by_play_provider = play_by_play_provider or ESPNPlayByPlayProvider()
        self._snapshots: dict[str, EventSnapshot] = {}

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
            if include_play_by_play and existing.normalized_play_by_play is None:
                existing.normalized_play_by_play = self._play_by_play_provider.get_normalized_events(normalized_event_id)
                existing.diagnostics.snapshot_build_sources['pbp'] = bool(existing.normalized_play_by_play)
            return existing

        summary_normalized = self._gamecast_provider.fetch_normalized(normalized_event_id)
        summary_raw = summary_normalized.get('raw') if summary_normalized else None
        scoreboard_event = self._scoreboard_event_for(normalized_event_id, event_date=event_date)

        home_team, away_team, team_map = self._team_maps_from_summary(summary_raw)
        player_stats = self._player_stats_from_summary(summary_raw)

        competition_date = None
        if summary_raw:
            competition_date = (((summary_raw.get('header') or {}).get('competitions') or [{}])[0].get('date'))
        snapshot = EventSnapshot(
            event_id=normalized_event_id,
            sport='NBA',
            league='NBA',
            event_date=self._parse_event_date(competition_date or event_date),
            event_status=((summary_normalized or {}).get('status') or {}).get('state') if summary_normalized else None,
            home_team=home_team,
            away_team=away_team,
            raw_scoreboard_event=scoreboard_event,
            raw_summary=summary_raw,
            raw_play_by_play=summary_raw,
            normalized_player_stats=player_stats,
            normalized_team_map=team_map,
            normalized_play_by_play=None,
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
            ),
        )
        if include_play_by_play:
            snapshot.normalized_play_by_play = self._play_by_play_provider.get_normalized_events(normalized_event_id)
            snapshot.diagnostics.snapshot_build_sources['pbp'] = bool(snapshot.normalized_play_by_play)

        self._snapshots[normalized_event_id] = snapshot
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

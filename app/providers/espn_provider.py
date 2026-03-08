from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import EventInfo, ResultsProvider, TeamResult


_SUPPORTED_PLAYER_MARKETS = {
    'player_points': {'points', 'pts', 'point'},
    'player_assists': {'assists', 'ast', 'assist'},
    'player_rebounds': {'rebounds', 'reb', 'total rebounds'},
    'player_threes': {'3pt made', '3pt field goals made', 'three point field goals made', 'threes made', '3-pointers made'},
}


class ESPNNBAResultsProvider(ResultsProvider):
    """Conservative NBA-only provider backed by ESPN public endpoints."""

    def __init__(self, timeout_s: float = 3.0) -> None:
        self._timeout_s = timeout_s
        self._scoreboard_cache: dict[str, dict[str, Any]] = {}
        self._summary_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r'[^a-z0-9]', '', text.lower())

    def _fetch_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        full_url = url
        if params:
            full_url = f'{url}?{urlencode(params)}'
        try:
            with urlopen(full_url, timeout=self._timeout_s) as resp:  # noqa: S310
                if getattr(resp, 'status', 200) != 200:
                    return None
                return json.loads(resp.read().decode('utf-8'))
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
        except Exception:
            return None

    def _day_key(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime('%Y%m%d')

    def _scoreboard_for_day(self, day_key: str) -> dict[str, Any] | None:
        if day_key in self._scoreboard_cache:
            return self._scoreboard_cache[day_key]
        payload = self._fetch_json(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
            params={'dates': day_key},
        )
        if payload is not None:
            self._scoreboard_cache[day_key] = payload
        return payload

    def _event_status_from_comp(self, comp: dict[str, Any]) -> str:
        status = ((comp.get('status') or {}).get('type') or {})
        if status.get('completed') is True:
            return 'final'
        state = str(status.get('state') or '').lower()
        if state in {'in', 'in_progress'}:
            return 'live'
        return 'scheduled'

    def _team_matches(self, team_name: str, competitor: dict[str, Any]) -> bool:
        team = competitor.get('team') or {}
        candidates = {
            str(team.get('displayName') or ''),
            str(team.get('shortDisplayName') or ''),
            str(team.get('name') or ''),
            str(team.get('abbreviation') or ''),
        }
        norm_target = self._norm(team_name)
        return any(self._norm(item) == norm_target for item in candidates if item)

    def _candidate_days(self, as_of: datetime | None) -> list[str]:
        anchor = as_of or datetime.now(timezone.utc)
        days = [anchor + timedelta(days=delta) for delta in (-1, 0, 1)]
        return [self._day_key(day) for day in days]

    def _event_info_from_scoreboard(self, event: dict[str, Any]) -> EventInfo | None:
        comps = event.get('competitions') or []
        if not comps:
            return None
        comp = comps[0]
        competitors = comp.get('competitors') or []
        home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
        away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
        if not home or not away:
            return None
        start_raw = event.get('date')
        try:
            start_time = datetime.fromisoformat(str(start_raw).replace('Z', '+00:00'))
        except Exception:
            return None
        return EventInfo(
            event_id=str(event.get('id')),
            sport='NBA',
            home_team=str((home.get('team') or {}).get('displayName') or ''),
            away_team=str((away.get('team') or {}).get('displayName') or ''),
            start_time=start_time,
        )

    def _summary(self, event_id: str) -> dict[str, Any] | None:
        if event_id in self._summary_cache:
            return self._summary_cache[event_id]
        payload = self._fetch_json(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary',
            params={'event': event_id},
        )
        if payload is not None:
            self._summary_cache[event_id] = payload
        return payload

    def get_event_status(self, event_id: str) -> str | None:
        summary = self._summary(event_id)
        if summary:
            header = (summary.get('header') or {}).get('competitions') or []
            if header:
                return self._event_status_from_comp(header[0])
        return None

    def resolve_team_event(self, team: str, as_of: datetime | None) -> EventInfo | None:
        for day_key in self._candidate_days(as_of):
            board = self._scoreboard_for_day(day_key)
            if not board:
                continue
            for event in board.get('events') or []:
                comps = event.get('competitions') or []
                if not comps:
                    continue
                competitors = comps[0].get('competitors') or []
                if any(self._team_matches(team, comp) for comp in competitors):
                    return self._event_info_from_scoreboard(event)
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None) -> EventInfo | None:
        target = self._norm(player)
        for day_key in self._candidate_days(as_of):
            board = self._scoreboard_for_day(day_key)
            if not board:
                continue
            for event in board.get('events') or []:
                info = self._event_info_from_scoreboard(event)
                if not info:
                    continue
                summary = self._summary(info.event_id)
                if not summary:
                    continue
                for team_block in (summary.get('boxscore') or {}).get('players') or []:
                    for stat_block in team_block.get('statistics') or []:
                        for athlete in stat_block.get('athletes') or []:
                            name = str((athlete.get('athlete') or {}).get('displayName') or '')
                            if self._norm(name) == target:
                                return info
        return None

    def get_team_result(self, team: str, event_id: str | None = None) -> TeamResult | None:
        if not event_id:
            return None
        summary = self._summary(event_id)
        if not summary:
            return None
        status = self.get_event_status(event_id)
        if status not in {'final', 'live'}:
            return None

        header = (summary.get('header') or {}).get('competitions') or []
        if not header:
            return None
        comp = header[0]
        competitors = comp.get('competitors') or []
        home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
        away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
        if not home or not away:
            return None

        home_name = str((home.get('team') or {}).get('displayName') or '')
        away_name = str((away.get('team') or {}).get('displayName') or '')
        if self._norm(team) not in {self._norm(home_name), self._norm(away_name)}:
            return None

        try:
            home_score = int(home.get('score'))
            away_score = int(away.get('score'))
        except Exception:
            return None

        event = EventInfo(
            event_id=event_id,
            sport='NBA',
            home_team=home_name,
            away_team=away_name,
            start_time=datetime.fromisoformat(str(comp.get('date')).replace('Z', '+00:00')),
        )
        ml_winner = home_name if home_score > away_score else away_name
        return TeamResult(
            event=event,
            moneyline_win=(self._norm(team) == self._norm(ml_winner)),
            home_score=home_score,
            away_score=away_score,
        )

    def _extract_player_stat(self, event_id: str, player: str, market_type: str) -> float | None:
        aliases = _SUPPORTED_PLAYER_MARKETS.get(market_type)
        if not aliases:
            return None
        summary = self._summary(event_id)
        if not summary:
            return None
        target = self._norm(player)

        for team_block in (summary.get('boxscore') or {}).get('players') or []:
            for stat_block in team_block.get('statistics') or []:
                labels = [str(x).strip().lower() for x in (stat_block.get('labels') or [])]
                idx = None
                for i, label in enumerate(labels):
                    if label in aliases:
                        idx = i
                        break
                if idx is None:
                    continue
                for athlete in stat_block.get('athletes') or []:
                    name = str((athlete.get('athlete') or {}).get('displayName') or '')
                    if self._norm(name) != target:
                        continue
                    stats = athlete.get('stats') or []
                    if idx >= len(stats):
                        return None
                    try:
                        return float(stats[idx])
                    except Exception:
                        return None
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None) -> float | None:
        if not event_id:
            return None
        status = self.get_event_status(event_id)
        if status not in {'final', 'live'}:
            return None
        return self._extract_player_stat(event_id, player, market_type)

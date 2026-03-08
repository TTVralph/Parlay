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
    'player_threes': {'3pt made', '3pt field goals made', 'three point field goals made', 'threes made', '3-pointers made', '3pt', '3pm'},
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
        candidates = self._team_name_candidates(competitor)
        norm_target = self._norm(team_name)
        return any(self._norm(item) == norm_target for item in candidates if item)

    def _team_name_candidates(self, competitor: dict[str, Any]) -> set[str]:
        team = competitor.get('team') or {}
        location = str(team.get('location') or '').strip()
        display = str(team.get('displayName') or '').strip()
        short = str(team.get('shortDisplayName') or '').strip()
        name = str(team.get('name') or '').strip()
        candidates = {
            display,
            short,
            name,
            str(team.get('abbreviation') or '').strip(),
            location,
        }
        if location and name:
            candidates.add(f'{location} {name}')
        if location and display:
            candidates.add(f'{location} {display}')
        return {item for item in candidates if item}

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
                if self._resolve_player_name(summary, player) is not None:
                    return info
        return None

    def get_team_result(self, team: str, event_id: str | None = None) -> TeamResult | None:
        if not event_id:
            return None
        summary = self._summary(event_id)
        if not summary:
            return None
        status = self.get_event_status(event_id)
        if status != 'final':
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

        home_candidates = self._team_name_candidates(home)
        away_candidates = self._team_name_candidates(away)
        home_name = str((home.get('team') or {}).get('displayName') or '') or next(iter(home_candidates), '')
        away_name = str((away.get('team') or {}).get('displayName') or '') or next(iter(away_candidates), '')
        norm_team = self._norm(team)
        if norm_team not in {self._norm(item) for item in (*home_candidates, *away_candidates)}:
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
        if home_score == away_score:
            return None
        winning_candidates = home_candidates if home_score > away_score else away_candidates
        return TeamResult(
            event=event,
            moneyline_win=any(norm_team == self._norm(item) for item in winning_candidates),
            home_score=home_score,
            away_score=away_score,
        )

    def _resolve_player_name(self, summary: dict[str, Any], player: str) -> str | None:
        target_full = self._norm(player)
        target_last = self._norm(player.split()[-1]) if player.split() else ''
        matches: dict[str, str] = {}
        for team_block in (summary.get('boxscore') or {}).get('players') or []:
            for stat_block in team_block.get('statistics') or []:
                for athlete in stat_block.get('athletes') or []:
                    athlete_obj = athlete.get('athlete') or {}
                    athlete_id = str(athlete_obj.get('id') or '')
                    display_name = str(athlete_obj.get('displayName') or '').strip()
                    if not display_name:
                        continue
                    athlete_full = self._norm(display_name)
                    athlete_last = self._norm(display_name.split()[-1]) if display_name.split() else ''
                    if target_full and target_full == athlete_full:
                        matches[athlete_id or athlete_full] = display_name
                        continue
                    if target_last and athlete_last and target_last == athlete_last:
                        matches[athlete_id or athlete_full] = display_name
        if len(matches) == 1:
            return next(iter(matches.values()))
        return None

    def _parse_stat_value(self, raw_value: Any, market_type: str) -> float | None:
        text = str(raw_value).strip()
        if not text or text == '--':
            return None
        if market_type == 'player_threes' and '-' in text:
            made, _sep, _attempts = text.partition('-')
            try:
                return float(int(made))
            except Exception:
                return None
        try:
            return float(text)
        except Exception:
            return None

    def _extract_player_stat(self, event_id: str, player: str, market_type: str) -> float | None:
        aliases = _SUPPORTED_PLAYER_MARKETS.get(market_type)
        if not aliases:
            return None
        summary = self._summary(event_id)
        if not summary:
            return None
        resolved_player_name = self._resolve_player_name(summary, player)
        if not resolved_player_name:
            return None
        target = self._norm(resolved_player_name)

        for team_block in (summary.get('boxscore') or {}).get('players') or []:
            for stat_block in team_block.get('statistics') or []:
                labels = [self._norm(str(x).strip().lower()) for x in (stat_block.get('labels') or [])]
                idx = None
                for i, label in enumerate(labels):
                    if label in {self._norm(item) for item in aliases}:
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
                    return self._parse_stat_value(stats[idx], market_type)
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None) -> float | None:
        if not event_id:
            return None
        status = self.get_event_status(event_id)
        if status != 'final':
            return None
        return self._extract_player_stat(event_id, player, market_type)

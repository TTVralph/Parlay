from __future__ import annotations

from datetime import datetime, timedelta

from .base import EventInfo, ResultsProvider, TeamResult
from ..sample_results import EVENTS, PLAYER_RESULTS_BY_EVENT


class SampleResultsProvider(ResultsProvider):
    def _event_info(self, event_id: str) -> EventInfo:
        row = EVENTS[event_id]
        return EventInfo(
            event_id=event_id,
            sport=row['sport'],
            home_team=row['home_team'],
            away_team=row['away_team'],
            start_time=row['start_time'],
        )

    def _candidate_events_for_team(self, team: str) -> list[EventInfo]:
        matches: list[EventInfo] = []
        for event_id, row in EVENTS.items():
            if team in {row['home_team'], row['away_team']}:
                matches.append(self._event_info(event_id))
        return sorted(matches, key=lambda item: item.start_time)

    def _candidate_events_for_player(self, player: str) -> list[EventInfo]:
        matches: list[EventInfo] = []
        for event_id, box in PLAYER_RESULTS_BY_EVENT.items():
            if player in box:
                matches.append(self._event_info(event_id))
        return sorted(matches, key=lambda item: item.start_time)

    def _resolve_by_time(self, events: list[EventInfo], as_of: datetime | None) -> EventInfo | None:
        if not events:
            return None
        if as_of is None:
            return events[0]

        future_buffer = timedelta(hours=8)
        future_candidates = [e for e in events if as_of <= e.start_time <= as_of + future_buffer]
        if future_candidates:
            return min(future_candidates, key=lambda item: item.start_time)

        recent_past = [e for e in events if e.start_time <= as_of <= e.start_time + timedelta(hours=8)]
        if recent_past:
            return max(recent_past, key=lambda item: item.start_time)

        historical = [e for e in events if e.start_time <= as_of]
        if historical:
            return max(historical, key=lambda item: item.start_time)

        return min(events, key=lambda item: item.start_time)

    def _resolve_unique_by_time(self, events: list[EventInfo], as_of: datetime | None) -> EventInfo | None:
        if not events:
            return None
        if as_of is None:
            return events[0] if len(events) == 1 else None

        future_buffer = timedelta(hours=8)
        future_candidates = [e for e in events if as_of <= e.start_time <= as_of + future_buffer]
        if len(future_candidates) == 1:
            return future_candidates[0]
        if len(future_candidates) > 1:
            return None

        recent_past = [e for e in events if e.start_time <= as_of <= e.start_time + timedelta(hours=8)]
        if len(recent_past) == 1:
            return recent_past[0]
        if len(recent_past) > 1:
            return None

        historical = [e for e in events if e.start_time <= as_of]
        if len(historical) == 1:
            return historical[0]
        if len(historical) > 1:
            return None

        return events[0] if len(events) == 1 else None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None) -> list[EventInfo]:
        events = self._candidate_events_for_team(team)
        if as_of is None:
            return events
        future_buffer = timedelta(hours=8)
        future_candidates = [e for e in events if as_of <= e.start_time <= as_of + future_buffer]
        if future_candidates:
            return future_candidates
        recent_past = [e for e in events if e.start_time <= as_of <= e.start_time + timedelta(hours=8)]
        if recent_past:
            return recent_past
        historical = [e for e in events if e.start_time <= as_of]
        return historical or events

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None) -> list[EventInfo]:
        events = self._candidate_events_for_player(player)
        if as_of is None:
            return events
        future_buffer = timedelta(hours=8)
        future_candidates = [e for e in events if as_of <= e.start_time <= as_of + future_buffer]
        if future_candidates:
            return future_candidates
        recent_past = [e for e in events if e.start_time <= as_of <= e.start_time + timedelta(hours=8)]
        if recent_past:
            return recent_past
        historical = [e for e in events if e.start_time <= as_of]
        return historical or events

    def resolve_team_event(self, team: str, as_of: datetime | None) -> EventInfo | None:
        return self._resolve_unique_by_time(self.resolve_team_event_candidates(team, as_of), as_of)

    def resolve_player_event(self, player: str, as_of: datetime | None) -> EventInfo | None:
        return self._resolve_unique_by_time(self.resolve_player_event_candidates(player, as_of), as_of)

    def get_team_result(self, team: str, event_id: str | None = None) -> TeamResult | None:
        if event_id is None:
            return None
        row = EVENTS.get(event_id)
        if not row or team not in {row['home_team'], row['away_team']}:
            return None
        event = self._event_info(event_id)
        return TeamResult(event=event, moneyline_win=(row['moneyline_winner'] == team), home_score=row['home_score'], away_score=row['away_score'])

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None) -> float | None:
        if event_id is None:
            return None
        event_box = PLAYER_RESULTS_BY_EVENT.get(event_id)
        if not event_box:
            return None
        player_result = event_box.get(player)
        if not player_result:
            return None
        return player_result.get(market_type)

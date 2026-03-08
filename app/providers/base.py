from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class EventInfo:
    event_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime

    @property
    def label(self) -> str:
        return f'{self.away_team} @ {self.home_team}'


@dataclass
class TeamResult:
    event: EventInfo
    moneyline_win: bool
    home_score: int
    away_score: int

    @property
    def total_points(self) -> int:
        return self.home_score + self.away_score

    def team_margin(self, team: str) -> int:
        if team == self.event.home_team:
            return self.home_score - self.away_score
        if team == self.event.away_team:
            return self.away_score - self.home_score
        raise ValueError('team not in event')


class ResultsProvider(Protocol):
    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False) -> EventInfo | None: ...
    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False) -> EventInfo | None: ...
    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False) -> list[EventInfo]: ...
    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False) -> list[EventInfo]: ...
    def get_team_result(self, team: str, event_id: str | None = None) -> TeamResult | None: ...
    def get_player_result(self, player: str, market_type: str, event_id: str | None = None) -> float | None: ...
    def did_player_appear(self, player: str, event_id: str | None = None) -> bool | None: ...

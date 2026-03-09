from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedSlipLeg:
    sport: str | None = None
    player_name: str | None = None
    market: str | None = None
    line: float | None = None
    selection: str | None = None
    raw_text: str = ''


@dataclass
class ParsedSlip:
    raw_text: str
    parsed_legs: list[ParsedSlipLeg] = field(default_factory=list)
    confidence: str = 'low'
    warnings: list[str] = field(default_factory=list)
    sportsbook_layout: str | None = None
    detected_bet_date: str | None = None
    stake_amount: float | None = None
    to_win_amount: float | None = None

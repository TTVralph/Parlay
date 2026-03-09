from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedSlipLeg:
    sport: str | None = None
    raw_player_text: str | None = None
    player_name: str | None = None
    market: str | None = None
    line: float | None = None
    selection: str | None = None
    raw_text: str = ''
    match_method: str | None = None
    match_confidence: str | None = None


@dataclass
class ParsedSlip:
    raw_text: str
    parsed_legs: list[ParsedSlipLeg] = field(default_factory=list)
    confidence: str = 'low'
    warnings: list[str] = field(default_factory=list)
    screenshot_state: str = 'unknown'
    sportsbook: str = 'unknown'
    sportsbook_layout: str | None = None
    detected_bet_date: str | None = None
    stake_amount: float | None = None
    to_win_amount: float | None = None
    preprocessing_metadata: dict[str, Any] | None = None
    primary_parser_status: str = 'not_attempted'
    fallback_parser_status: str = 'not_attempted'
    fallback_reason: str | None = None

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
class PrimaryParseDebug:
    status: str = 'not_attempted'
    failure_category: str | None = None
    provider_error: str | None = None
    confidence: str | None = None
    warnings: list[str] = field(default_factory=list)
    detected_sportsbook: str | None = None
    screenshot_state: str | None = None
    parsed_leg_count: int = 0


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
    primary_failure_category: str | None = None
    primary_provider_error: str | None = None
    primary_confidence: str | None = None
    primary_warnings: list[str] = field(default_factory=list)
    primary_detected_sportsbook: str | None = None
    primary_screenshot_state: str | None = None
    primary_parsed_leg_count: int = 0
    primary_result: ParsedSlip | None = None
    fallback_parser_status: str = 'not_attempted'
    fallback_reason: Literal['vision_provider_error', 'vision_empty_parse', 'vision_low_confidence', 'vision_schema_error', 'vision_preprocessing_error'] | None = None
    debug_artifacts: dict[str, str] | None = None

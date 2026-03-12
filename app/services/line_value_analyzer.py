from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import mean
from typing import Any

from app.models import Leg

SUPPORTED_PROP_MARKETS = {
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_threes',
    'player_pra',
    'player_pr',
    'player_pa',
    'player_ra',
    'moneyline',
    'spread',
    'game_total',
}

_LINE_KEYS = ('market_line', 'line', 'value', 'points', 'number', 'odds', 'american_odds')
_PROVIDER_KEYS = ('provider', 'bookmaker', 'book', 'source', 'sportsbook')


@dataclass(frozen=True)
class LineValueAnalysis:
    market_average_line: float | None
    user_line: float | None
    line_difference: float | None
    line_value_score: float | None
    line_value_label: str
    line_value_source: str | None = None
    providers_used: tuple[str, ...] = ()


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r'-?\d+(?:\.\d+)?', value)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _extract_from_candidate(candidate: Any) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    if not isinstance(candidate, dict):
        return rows

    provider = 'market'
    for key in _PROVIDER_KEYS:
        if key in candidate and candidate[key]:
            provider = str(candidate[key]).strip() or provider
            break

    for key in _LINE_KEYS:
        if key in candidate:
            value = _as_float(candidate.get(key))
            if value is not None:
                rows.append((provider, value))

    nested = candidate.get('comparison_lines') or candidate.get('lines') or candidate.get('markets')
    if isinstance(nested, list):
        for item in nested:
            rows.extend(_extract_from_candidate(item))
    elif isinstance(nested, dict):
        for maybe_provider, payload in nested.items():
            if isinstance(payload, dict):
                for key in _LINE_KEYS:
                    if key in payload:
                        value = _as_float(payload.get(key))
                        if value is not None:
                            rows.append((str(maybe_provider), value))

    return rows


def _extract_from_notes(notes: list[str]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for note in notes:
        if not isinstance(note, str):
            continue
        match = re.search(r'(?P<provider>[A-Za-z0-9 ._-]{2,32})\s*[:=-]?\s*(?P<line>-?\d+(?:\.\d+)?)', note)
        if not match:
            continue
        provider = match.group('provider').strip()
        line = _as_float(match.group('line'))
        if line is not None:
            rows.append((provider, line))
    return rows


def _label_from_score(score: float | None) -> str:
    if score is None:
        return 'unknown'
    if score >= 0.15:
        return 'good'
    if score <= -0.15:
        return 'bad'
    return 'neutral'


def _american_to_implied_probability(american_odds: float) -> float:
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return abs(american_odds) / (abs(american_odds) + 100.0)


def _moneyline_score_line_value(leg: Leg, market_avg: float) -> tuple[float | None, float | None, float | None]:
    user_line = float(leg.american_odds) if leg.american_odds is not None else None
    if user_line is None:
        return None, None, None

    market_prob = _american_to_implied_probability(market_avg)
    user_prob = _american_to_implied_probability(user_line)
    edge = market_prob - user_prob
    score = max(-1.0, min(1.0, edge / 0.08))
    return user_line, round(user_line - market_avg, 2), round(score, 2)


def _score_line_value(leg: Leg, market_avg: float | None) -> tuple[float | None, float | None, float | None]:
    if market_avg is None:
        return None, None, None

    if leg.market_type == 'moneyline':
        return _moneyline_score_line_value(leg, market_avg)

    if leg.line is None:
        return None, None, None

    user_line = float(leg.line)
    difference = round(user_line - market_avg, 2)
    if leg.market_type in {'spread', 'game_total'}:
        edge = abs(market_avg) - abs(user_line)
    elif leg.direction == 'over':
        edge = market_avg - user_line
    elif leg.direction == 'under':
        edge = user_line - market_avg
    else:
        edge = 0.0

    score = max(-1.0, min(1.0, edge / 2.0))
    return user_line, difference, round(score, 2)


def analyze_line_value(leg: Leg) -> LineValueAnalysis:
    if leg.market_type not in SUPPORTED_PROP_MARKETS:
        return LineValueAnalysis(None, None, None, None, 'unknown')

    collected: list[tuple[str, float]] = []
    for candidate in leg.event_candidates:
        collected.extend(_extract_from_candidate(candidate))
    collected.extend(_extract_from_notes(leg.notes))

    deduped: dict[str, float] = {}
    for provider, line in collected:
        key = provider.strip().lower() or f'provider-{len(deduped)}'
        deduped[key] = line

    if not deduped:
        return LineValueAnalysis(None, None, None, None, 'unknown')

    avg_line = round(mean(deduped.values()), 2)
    user_line, line_diff, score = _score_line_value(leg, avg_line)
    label = _label_from_score(score)
    return LineValueAnalysis(
        market_average_line=avg_line,
        user_line=user_line,
        line_difference=line_diff,
        line_value_score=score,
        line_value_label=label,
        line_value_source='market_consensus',
        providers_used=tuple(sorted(deduped.keys())),
    )


def analyze_line_value_against_market_line(leg: Leg, market_line: float, source: str) -> LineValueAnalysis:
    user_line, line_diff, score = _score_line_value(leg, market_line)
    return LineValueAnalysis(
        market_average_line=round(market_line, 2),
        user_line=user_line,
        line_difference=line_diff,
        line_value_score=score,
        line_value_label=_label_from_score(score),
        line_value_source=source,
        providers_used=(source,),
    )

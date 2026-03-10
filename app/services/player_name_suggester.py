from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from ..identity_resolution import get_sport_adapters
from .identity_normalizer import normalize_person_name


@dataclass(frozen=True)
class PlayerNameSuggestion:
    input_name: str
    suggested_name: str
    confidence_score: float
    confidence_level: str
    auto_applied: bool


def _split_name_parts(name: str) -> tuple[str, str]:
    parts = [p for p in normalize_person_name(name).split() if p]
    if len(parts) < 2:
        return '', ''
    return ' '.join(parts[:-1]), parts[-1]


def _looks_like_player_name(name: str) -> bool:
    normalized = normalize_person_name(name)
    parts = [p for p in normalized.split() if p]
    if len(parts) < 2:
        return False
    if any(len(part) < 2 for part in parts):
        return False
    return bool(re.fullmatch(r"[a-z\-\s']+", normalized))


def suggest_player_name(name: str | None, sport: str = 'NBA') -> PlayerNameSuggestion | None:
    raw_name = (name or '').strip()
    if not _looks_like_player_name(raw_name):
        return None

    first_input, last_input = _split_name_parts(raw_name)
    if not last_input:
        return None

    adapter = get_sport_adapters().get(sport)
    if not adapter:
        return None

    ranked: list[tuple[float, float, float, str]] = []
    normalized_input = normalize_person_name(raw_name)
    for player in adapter.load_players():
        candidate_name = player.full_name
        first_candidate, last_candidate = _split_name_parts(candidate_name)
        if not first_candidate or not last_candidate:
            continue

        last_score = SequenceMatcher(None, last_input, last_candidate).ratio()
        if last_score < 0.74:
            continue

        first_score = SequenceMatcher(None, first_input, first_candidate).ratio()
        full_score = SequenceMatcher(None, normalized_input, normalize_person_name(candidate_name)).ratio()
        weighted = (last_score * 0.62) + (full_score * 0.28) + (first_score * 0.10)
        ranked.append((weighted, last_score, first_score, candidate_name))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_weighted, best_last, best_first, best_name = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    separation = best_weighted - runner_up

    if normalize_person_name(best_name) == normalized_input:
        return None

    high_confidence = (
        best_weighted >= 0.922
        and best_last >= 0.95
        and best_first >= 0.65
        and separation >= 0.05
    )
    medium_confidence = (
        best_weighted >= 0.90
        and best_last >= 0.84
        and best_first >= 0.50
        and separation >= 0.03
    )

    if high_confidence:
        return PlayerNameSuggestion(
            input_name=raw_name,
            suggested_name=best_name,
            confidence_score=round(best_weighted, 3),
            confidence_level='HIGH',
            auto_applied=True,
        )
    if medium_confidence:
        return PlayerNameSuggestion(
            input_name=raw_name,
            suggested_name=best_name,
            confidence_score=round(best_weighted, 3),
            confidence_level='MEDIUM',
            auto_applied=False,
        )
    return None

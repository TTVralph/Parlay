from __future__ import annotations

SPORT_CAPABILITY_MATRIX: dict[str, dict[str, bool]] = {
    'nba': {
        'parsing': True,
        'event_matching': True,
        'settlement': True,
        'play_by_play_verification': True,
        'live_progress': True,
        'death_cards': True,
    },
    'wnba': {
        'parsing': True,
        'event_matching': True,
        'settlement': False,
        'play_by_play_verification': False,
        'live_progress': False,
        'death_cards': False,
    },
    'mlb': {
        'parsing': True,
        'event_matching': False,
        'settlement': False,
        'play_by_play_verification': False,
        'live_progress': False,
        'death_cards': False,
    },
    'nfl': {
        'parsing': True,
        'event_matching': False,
        'settlement': False,
        'play_by_play_verification': False,
        'live_progress': False,
        'death_cards': False,
    },
}


def get_sport_capabilities(sport: str) -> dict[str, bool] | None:
    return SPORT_CAPABILITY_MATRIX.get(sport.lower())

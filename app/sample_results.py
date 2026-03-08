"""Sample schedule + stats for local development."""

from __future__ import annotations

from datetime import datetime

EVENTS = {
    'nba-2026-03-06-den-nyk': {
        'sport': 'NBA',
        'home_team': 'Denver Nuggets',
        'away_team': 'New York Knicks',
        'start_time': datetime.fromisoformat('2026-03-06T20:00:00'),
        'home_score': 112,
        'away_score': 104,
        'moneyline_winner': 'Denver Nuggets',
    },
    'nba-2026-03-07-den-lal': {
        'sport': 'NBA',
        'home_team': 'Denver Nuggets',
        'away_team': 'Los Angeles Lakers',
        'start_time': datetime.fromisoformat('2026-03-07T20:00:00'),
        'home_score': 118,
        'away_score': 109,
        'moneyline_winner': 'Denver Nuggets',
    },
    'nba-2026-03-08-bos-gsw': {
        'sport': 'NBA',
        'home_team': 'Boston Celtics',
        'away_team': 'Golden State Warriors',
        'start_time': datetime.fromisoformat('2026-03-08T19:30:00'),
        'home_score': 121,
        'away_score': 112,
        'moneyline_winner': 'Boston Celtics',
    },
    'nba-2026-03-08-gsw-den': {
        'sport': 'NBA',
        'home_team': 'Golden State Warriors',
        'away_team': 'Denver Nuggets',
        'start_time': datetime.fromisoformat('2026-03-08T22:00:00'),
        'home_score': 119,
        'away_score': 110,
        'moneyline_winner': 'Golden State Warriors',
    },
    'nba-2026-03-09-okc-den': {
        'sport': 'NBA',
        'home_team': 'Oklahoma City Thunder',
        'away_team': 'Denver Nuggets',
        'start_time': datetime.fromisoformat('2026-03-09T20:00:00'),
        'home_score': 117,
        'away_score': 111,
        'moneyline_winner': 'Oklahoma City Thunder',
    },
    'nfl-2026-03-07-kc-buf': {
        'sport': 'NFL',
        'home_team': 'Kansas City Chiefs',
        'away_team': 'Buffalo Bills',
        'start_time': datetime.fromisoformat('2026-03-07T15:00:00'),
        'home_score': 31,
        'away_score': 27,
        'moneyline_winner': 'Kansas City Chiefs',
    },
    'mlb-2026-03-07-nyy-bos': {
        'sport': 'MLB',
        'home_team': 'New York Yankees',
        'away_team': 'Boston Red Sox',
        'start_time': datetime.fromisoformat('2026-03-07T13:00:00'),
        'home_score': 6,
        'away_score': 4,
        'moneyline_winner': 'New York Yankees',
    },
}

PLAYER_RESULTS_BY_EVENT = {
    'nba-2026-03-06-den-nyk': {
        'Nikola Jokic': {'player_points': 26, 'player_rebounds': 13, 'player_assists': 8, 'player_threes': 1, 'player_pra': 47},
        'Jamal Murray': {'player_points': 21, 'player_rebounds': 4, 'player_assists': 6, 'player_threes': 2, 'player_pra': 31},
        'Jalen Brunson': {'player_points': 29, 'player_rebounds': 3, 'player_assists': 7, 'player_threes': 4, 'player_pra': 39},
    },
    'nba-2026-03-07-den-lal': {
        'Nikola Jokic': {'player_points': 27, 'player_rebounds': 11, 'player_assists': 9, 'player_threes': 1, 'player_pra': 47},
        'Jamal Murray': {'player_points': 18, 'player_rebounds': 4, 'player_assists': 6, 'player_threes': 1, 'player_pra': 28},
        'LeBron James': {'player_points': 24, 'player_rebounds': 7, 'player_assists': 8, 'player_threes': 2, 'player_pra': 39},
    },
    'nba-2026-03-08-bos-gsw': {
        'Jayson Tatum': {'player_points': 29, 'player_rebounds': 8, 'player_assists': 5, 'player_threes': 3, 'player_pra': 42},
        'Stephen Curry': {'player_points': 31, 'player_rebounds': 5, 'player_assists': 6, 'player_threes': 6, 'player_pra': 42},
    },
    'nba-2026-03-08-gsw-den': {
        'Nikola Jokic': {'player_points': 28, 'player_rebounds': 10, 'player_assists': 9, 'player_threes': 3, 'player_pra': 47},
        'Jamal Murray': {'player_points': 25, 'player_rebounds': 5, 'player_assists': 6, 'player_threes': 4, 'player_pra': 36},
        'Stephen Curry': {'player_points': 35, 'player_rebounds': 5, 'player_assists': 7, 'player_threes': 7, 'player_pra': 47},
    },
    'nba-2026-03-09-okc-den': {
        'Nikola Jokic': {'player_points': 23, 'player_rebounds': 12, 'player_assists': 10, 'player_threes': 2, 'player_pra': 45},
        'Jamal Murray': {'player_points': 22, 'player_rebounds': 3, 'player_assists': 7, 'player_threes': 3, 'player_pra': 32},
        'Shai Gilgeous-Alexander': {'player_points': 33, 'player_rebounds': 6, 'player_assists': 7, 'player_threes': 2, 'player_pra': 46},
    },
    'nfl-2026-03-07-kc-buf': {
        'Patrick Mahomes': {'player_passing_yards': 312, 'player_rushing_yards': 28},
        'Josh Allen': {'player_passing_yards': 287, 'player_rushing_yards': 41},
        'CeeDee Lamb': {'player_receiving_yards': 0},
        'Christian McCaffrey': {'player_rushing_yards': 0, 'player_receiving_yards': 0},
    },
    'mlb-2026-03-07-nyy-bos': {
        'Aaron Judge': {'player_hits': 2},
        'Juan Soto': {'player_hits': 1},
        'Shohei Ohtani': {'player_hits': 0},
        'Mookie Betts': {'player_hits': 0},
    },
}

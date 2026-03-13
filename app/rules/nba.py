from __future__ import annotations

from app.rules.base import StatRule
from app.rules.helpers import compute_combo_stat, get_player_stat


NBA_RULES: dict[str, StatRule] = {
    'player_points': StatRule('NBA', 'player_points', ('PTS',), lambda s, pid, pname: get_player_stat(s, pid, 'PTS', player_name=pname), display_name='Points', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS',)),
    'player_rebounds': StatRule('NBA', 'player_rebounds', ('REB',), lambda s, pid, pname: get_player_stat(s, pid, 'REB', player_name=pname), display_name='Rebounds', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('REB',)),
    'player_assists': StatRule('NBA', 'player_assists', ('AST',), lambda s, pid, pname: get_player_stat(s, pid, 'AST', player_name=pname), display_name='Assists', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('AST',)),
    'player_threes': StatRule('NBA', 'player_threes', ('3PM',), lambda s, pid, pname: get_player_stat(s, pid, '3PM', player_name=pname), display_name='Threes Made'),
    'player_steals': StatRule('NBA', 'player_steals', ('STL',), lambda s, pid, pname: get_player_stat(s, pid, 'STL', player_name=pname), display_name='Steals'),
    'player_blocks': StatRule('NBA', 'player_blocks', ('BLK',), lambda s, pid, pname: get_player_stat(s, pid, 'BLK', player_name=pname), display_name='Blocks'),
    'player_turnovers': StatRule('NBA', 'player_turnovers', ('TOV',), lambda s, pid, pname: get_player_stat(s, pid, 'TOV', player_name=pname), display_name='Turnovers'),
    'player_pr': StatRule('NBA', 'player_pr', ('PTS', 'REB'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'REB'), player_name=pname), display_name='PR', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'REB')),
    'player_pa': StatRule('NBA', 'player_pa', ('PTS', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'AST'), player_name=pname), display_name='PA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'AST')),
    'player_ra': StatRule('NBA', 'player_ra', ('REB', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('REB', 'AST'), player_name=pname), display_name='RA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('REB', 'AST')),
    'player_pra': StatRule('NBA', 'player_pra', ('PTS', 'REB', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'REB', 'AST'), player_name=pname), display_name='PRA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'REB', 'AST')),
    'moneyline': StatRule('NBA', 'moneyline', tuple(), lambda s, pid, pname: None, display_name='Moneyline', supports_team_markets=True, supports_player_markets=False),
    'game_total': StatRule('NBA', 'game_total', tuple(), lambda s, pid, pname: None, display_name='Game Total', supports_team_markets=True, supports_player_markets=False),
}

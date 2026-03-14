from app.rules.base import StatRule
from app.rules.helpers import compute_combo_stat, get_player_stat

WNBA_RULES = {
    'player_points': StatRule('WNBA', 'player_points', ('PTS',), lambda s, pid, pname: get_player_stat(s, pid, 'PTS', player_name=pname), display_name='Points', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS',)),
    'player_rebounds': StatRule('WNBA', 'player_rebounds', ('REB',), lambda s, pid, pname: get_player_stat(s, pid, 'REB', player_name=pname), display_name='Rebounds', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('REB',)),
    'player_assists': StatRule('WNBA', 'player_assists', ('AST',), lambda s, pid, pname: get_player_stat(s, pid, 'AST', player_name=pname), display_name='Assists', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('AST',)),
    'player_threes': StatRule('WNBA', 'player_threes', ('3PM',), lambda s, pid, pname: get_player_stat(s, pid, '3PM', player_name=pname), display_name='Threes Made'),
    'player_pr': StatRule('WNBA', 'player_pr', ('PTS', 'REB'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'REB'), player_name=pname), display_name='PR', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'REB')),
    'player_pa': StatRule('WNBA', 'player_pa', ('PTS', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'AST'), player_name=pname), display_name='PA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'AST')),
    'player_ra': StatRule('WNBA', 'player_ra', ('REB', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('REB', 'AST'), player_name=pname), display_name='RA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('REB', 'AST')),
    'player_pra': StatRule('WNBA', 'player_pra', ('PTS', 'REB', 'AST'), lambda s, pid, pname: compute_combo_stat(s, pid, ('PTS', 'REB', 'AST'), player_name=pname), display_name='PRA', supports_live_progress=True, supports_kill_moment=True, live_progress_components=('PTS', 'REB', 'AST')),
}

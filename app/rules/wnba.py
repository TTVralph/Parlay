from app.rules.base import StatRule
from app.rules.helpers import get_player_stat

WNBA_RULES = {
    'player_points': StatRule('WNBA', 'player_points', ('PTS',), lambda s, pid, pname: get_player_stat(s, pid, 'PTS', player_name=pname), display_name='Points', supports_live_progress=True),
    'player_rebounds': StatRule('WNBA', 'player_rebounds', ('REB',), lambda s, pid, pname: get_player_stat(s, pid, 'REB', player_name=pname), display_name='Rebounds', supports_live_progress=True),
    'player_assists': StatRule('WNBA', 'player_assists', ('AST',), lambda s, pid, pname: get_player_stat(s, pid, 'AST', player_name=pname), display_name='Assists', supports_live_progress=True),
}

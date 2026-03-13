from app.rules.base import StatRule
from app.rules.helpers import get_player_stat

NHL_RULES = {
    'player_shots_on_goal': StatRule('NHL', 'player_shots_on_goal', ('SOG',), lambda s, pid, pname: get_player_stat(s, pid, 'SOG', player_name=pname), display_name='Shots on Goal'),
    'player_points': StatRule('NHL', 'player_points', ('NHL_PTS',), lambda s, pid, pname: get_player_stat(s, pid, 'NHL_PTS', player_name=pname), display_name='Points'),
}

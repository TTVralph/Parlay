from app.rules.base import StatRule
from app.rules.helpers import get_player_stat

NFL_RULES = {
    'player_passing_yards': StatRule('NFL', 'player_passing_yards', ('PASS_YDS',), lambda s, pid, pname: get_player_stat(s, pid, 'PASS_YDS', player_name=pname), display_name='Passing Yards'),
    'player_rushing_yards': StatRule('NFL', 'player_rushing_yards', ('RUSH_YDS',), lambda s, pid, pname: get_player_stat(s, pid, 'RUSH_YDS', player_name=pname), display_name='Rushing Yards'),
    'player_receiving_yards': StatRule('NFL', 'player_receiving_yards', ('REC_YDS',), lambda s, pid, pname: get_player_stat(s, pid, 'REC_YDS', player_name=pname), display_name='Receiving Yards'),
}

from app.rules.base import StatRule
from app.rules.helpers import get_player_stat

SOCCER_RULES = {
    'player_shots': StatRule('SOCCER', 'player_shots', ('SHOTS',), lambda s, pid, pname: get_player_stat(s, pid, 'SHOTS', player_name=pname), display_name='Shots'),
    'player_shots_on_target': StatRule('SOCCER', 'player_shots_on_target', ('SOT',), lambda s, pid, pname: get_player_stat(s, pid, 'SOT', player_name=pname), display_name='Shots on Target'),
}

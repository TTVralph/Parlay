from app.rules.base import StatRule

UFC_RULES = {
    'fight_winner': StatRule('UFC', 'fight_winner', tuple(), lambda s, pid, pname: None, display_name='Fight Winner', supports_player_markets=False, supports_team_markets=False),
}

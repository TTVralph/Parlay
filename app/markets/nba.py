from __future__ import annotations

from .base import MarketRegistryEntry, with_generated_variants

NBA_MARKET_REGISTRY: dict[str, MarketRegistryEntry] = with_generated_variants({
    'points': {'canonical_market_name': 'points', 'aliases': ['points', 'point', 'pts', 'PTS'], 'market_type': 'single_stat', 'stat_components': ['PTS'], 'display_name': 'Points', 'required_data_source': 'box_score'},
    'rebounds': {'canonical_market_name': 'rebounds', 'aliases': ['rebounds', 'reb', 'rebs', 'boards', 'REB'], 'market_type': 'single_stat', 'stat_components': ['REB'], 'display_name': 'Rebounds', 'required_data_source': 'box_score'},
    'assists': {'canonical_market_name': 'assists', 'aliases': ['assists', 'assist', 'ast', 'asts', 'AST'], 'market_type': 'single_stat', 'stat_components': ['AST'], 'display_name': 'Assists', 'required_data_source': 'box_score'},
    'steals': {'canonical_market_name': 'steals', 'aliases': ['steals', 'stl', 'steal', 'STL'], 'market_type': 'single_stat', 'stat_components': ['STL'], 'display_name': 'Steals', 'required_data_source': 'box_score'},
    'blocks': {'canonical_market_name': 'blocks', 'aliases': ['blocks', 'blk', 'block', 'BLK'], 'market_type': 'single_stat', 'stat_components': ['BLK'], 'display_name': 'Blocks', 'required_data_source': 'box_score'},
    'turnovers': {'canonical_market_name': 'turnovers', 'aliases': ['turnovers', 'turnover', 'to', 'tov', 'TO', 'TOV'], 'market_type': 'single_stat', 'stat_components': ['TOV'], 'display_name': 'Turnovers', 'required_data_source': 'box_score'},
    'three_pointers_made': {'canonical_market_name': 'three_pointers_made', 'aliases': ['threes', '3s', '3pm', '3 ptm', '3pt made', '3ptm', '3PTM', '3PM', 'made threes', 'three pointers', 'three-pointers', 'three pointers made', 'three-pointers made', 'three point field goals made', 'three-point field goals made'], 'market_type': 'single_stat', 'stat_components': ['3PM'], 'display_name': 'Three Pointers Made', 'required_data_source': 'box_score'},
    'field_goals_made': {'canonical_market_name': 'field_goals_made', 'aliases': ['field goals made', 'fgm', 'FGM', 'made field goals'], 'market_type': 'single_stat', 'stat_components': ['FGM'], 'display_name': 'Field Goals Made', 'required_data_source': 'box_score'},
    'free_throws_made': {'canonical_market_name': 'free_throws_made', 'aliases': ['free throws made', 'ftm', 'FTM', 'made free throws'], 'market_type': 'single_stat', 'stat_components': ['FTM'], 'display_name': 'Free Throws Made', 'required_data_source': 'box_score'},
    'offensive_rebounds': {'canonical_market_name': 'offensive_rebounds', 'aliases': ['offensive rebounds', 'oreb', 'OREB'], 'market_type': 'single_stat', 'stat_components': ['OREB'], 'display_name': 'Offensive Rebounds', 'required_data_source': 'box_score'},
    'defensive_rebounds': {'canonical_market_name': 'defensive_rebounds', 'aliases': ['defensive rebounds', 'dreb', 'DREB'], 'market_type': 'single_stat', 'stat_components': ['DREB'], 'display_name': 'Defensive Rebounds', 'required_data_source': 'box_score'},
    'minutes_played': {'canonical_market_name': 'minutes_played', 'aliases': ['minutes played', 'minutes', 'mins', 'min'], 'market_type': 'single_stat', 'stat_components': ['MIN'], 'display_name': 'Minutes Played', 'required_data_source': 'box_score'},
    'points_rebounds': {'canonical_market_name': 'points_rebounds', 'aliases': ['pr', 'p+r', 'pts+reb', 'pts + reb', 'points rebounds', 'points + rebounds', 'pts+rebs'], 'market_type': 'combo_stat', 'stat_components': ['PTS', 'REB'], 'display_name': 'Points + Rebounds', 'required_data_source': 'box_score'},
    'points_assists': {'canonical_market_name': 'points_assists', 'aliases': ['pa', 'p+a', 'pts+ast', 'pts + ast', 'points assists', 'points + assists'], 'market_type': 'combo_stat', 'stat_components': ['PTS', 'AST'], 'display_name': 'Points + Assists', 'required_data_source': 'box_score'},
    'rebounds_assists': {'canonical_market_name': 'rebounds_assists', 'aliases': ['ra', 'r+a', 'reb+ast', 'reb + ast', 'rebounds assists', 'rebounds + assists'], 'market_type': 'combo_stat', 'stat_components': ['REB', 'AST'], 'display_name': 'Rebounds + Assists', 'required_data_source': 'box_score'},
    'points_rebounds_assists': {'canonical_market_name': 'points_rebounds_assists', 'aliases': ['pra', 'p+r+a', 'pts+reb+ast', 'pts + reb + ast', 'pts reb ast', 'points rebounds assists', 'points + rebounds + assists', 'pts+rebs+asts'], 'market_type': 'combo_stat', 'stat_components': ['PTS', 'REB', 'AST'], 'display_name': 'Points + Rebounds + Assists', 'required_data_source': 'box_score'},
    'steals_blocks': {'canonical_market_name': 'steals_blocks', 'aliases': ['stocks', 'stl+blk', 'stl + blk', 'steals+blocks', 'steals + blocks', 'steals blocks'], 'market_type': 'combo_stat', 'stat_components': ['STL', 'BLK'], 'display_name': 'Steals + Blocks', 'required_data_source': 'box_score'},
    'points_threes': {'canonical_market_name': 'points_threes', 'aliases': ['points+threes', 'points + threes', 'pts+3pm', 'pts + 3pm', 'points three pointers made'], 'market_type': 'combo_stat', 'stat_components': ['PTS', '3PM'], 'display_name': 'Points + Three Pointers Made', 'required_data_source': 'box_score'},
    'rebounds_blocks': {'canonical_market_name': 'rebounds_blocks', 'aliases': ['rebounds+blocks', 'rebounds + blocks', 'reb+blk', 'reb + blk'], 'market_type': 'combo_stat', 'stat_components': ['REB', 'BLK'], 'display_name': 'Rebounds + Blocks', 'required_data_source': 'box_score'},
    'double_double': {'canonical_market_name': 'double_double', 'aliases': ['double double', 'double-double'], 'market_type': 'derived_stat', 'stat_components': [], 'display_name': 'Double Double', 'required_data_source': 'box_score'},
    'triple_double': {'canonical_market_name': 'triple_double', 'aliases': ['triple double', 'triple-double'], 'market_type': 'derived_stat', 'stat_components': [], 'display_name': 'Triple Double', 'required_data_source': 'box_score'},
    'first_basket': {'canonical_market_name': 'first_basket', 'aliases': ['first basket', 'first bucket', 'first scorer', 'to score first'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Basket', 'required_data_source': 'play_by_play'},
    'first_rebound': {'canonical_market_name': 'first_rebound', 'aliases': ['first rebound', 'to get first rebound'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Rebound', 'required_data_source': 'play_by_play'},
    'first_assist': {'canonical_market_name': 'first_assist', 'aliases': ['first assist', 'to record first assist'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Assist', 'required_data_source': 'play_by_play'},
    'first_three': {'canonical_market_name': 'first_three', 'aliases': ['first three', 'first 3 pointer', 'first 3pt made', 'first three-pointer made'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Three', 'required_data_source': 'play_by_play'},
    'last_basket': {'canonical_market_name': 'last_basket', 'aliases': ['last basket', 'last bucket', 'to score last'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'Last Basket', 'required_data_source': 'play_by_play'},
    'first_steal': {'canonical_market_name': 'first_steal', 'aliases': ['first steal'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Steal', 'required_data_source': 'play_by_play'},
    'first_block': {'canonical_market_name': 'first_block', 'aliases': ['first block'], 'market_type': 'event_sequence_prop', 'stat_components': [], 'display_name': 'First Block', 'required_data_source': 'play_by_play'},
}, [
    'points', 'rebounds', 'assists', 'steals', 'blocks', 'turnovers', 'three_pointers_made',
    'field_goals_made', 'free_throws_made', 'offensive_rebounds', 'defensive_rebounds', 'minutes_played',
    'points_rebounds', 'points_assists', 'rebounds_assists', 'points_rebounds_assists',
    'steals_blocks', 'points_threes', 'rebounds_blocks',
])

NBA_CANONICAL_TO_PLAYER_MARKET = {
    'points': 'player_points', 'rebounds': 'player_rebounds', 'assists': 'player_assists', 'steals': 'player_steals', 'blocks': 'player_blocks',
    'turnovers': 'player_turnovers', 'three_pointers_made': 'player_threes', 'field_goals_made': 'player_field_goals_made',
    'free_throws_made': 'player_free_throws_made', 'offensive_rebounds': 'player_offensive_rebounds', 'defensive_rebounds': 'player_defensive_rebounds',
    'minutes_played': 'player_minutes_played', 'points_rebounds': 'player_pr', 'points_assists': 'player_pa', 'rebounds_assists': 'player_ra',
    'points_rebounds_assists': 'player_pra', 'steals_blocks': 'player_stocks', 'points_threes': 'player_points_threes', 'rebounds_blocks': 'player_rebounds_blocks',
    'double_double': 'player_double_double', 'triple_double': 'player_triple_double', 'first_basket': 'player_first_basket',
    'first_rebound': 'player_first_rebound', 'first_assist': 'player_first_assist', 'first_three': 'player_first_three',
    'last_basket': 'player_last_basket', 'first_steal': 'player_first_steal', 'first_block': 'player_first_block',
}

for key, mapped in list(NBA_CANONICAL_TO_PLAYER_MARKET.items()):
    entry = NBA_MARKET_REGISTRY.get(key)
    if not entry or entry['required_data_source'] != 'box_score':
        continue
    NBA_CANONICAL_TO_PLAYER_MARKET[f'{key}_milestone'] = mapped
    NBA_CANONICAL_TO_PLAYER_MARKET[f'{key}_alternate_line'] = mapped

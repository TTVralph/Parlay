from app.parser import parse_text


def test_parse_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    legs = parse_text(text)
    assert len(legs) == 3
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].market_type == 'player_points'
    assert legs[1].team == 'Denver Nuggets'
    assert legs[2].market_type == 'player_threes'


def test_parse_full_name_nba_props_with_extended_market_labels() -> None:
    text = (
        'Nikola Jokic Over 1.5 Threes Made\n'
        'Cooper Flagg Over 25.5 PRA\n'
        'Kevin Durant Over 26.5 Points\n'
        'LaMelo Ball Over 19.5 Points\n'
        'Jaime Jaquez Over 3.5 Assists'
    )

    legs = parse_text(text)

    assert len(legs) == 5
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].market_type == 'player_threes'
    assert legs[1].player == 'Cooper Flagg'
    assert legs[1].market_type == 'player_pra'
    assert legs[2].player == 'Kevin Durant'
    assert legs[2].market_type == 'player_points'
    assert legs[3].player == 'LaMelo Ball'
    assert legs[3].market_type == 'player_points'
    assert legs[4].player == 'Jaime Jaquez Jr.'
    assert legs[4].market_type == 'player_assists'

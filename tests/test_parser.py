from app.parser import parse_text


def test_parse_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    legs = parse_text(text)
    assert len(legs) == 3
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].market_type == 'player_points'
    assert legs[1].team == 'Denver Nuggets'
    assert legs[2].market_type == 'player_threes'



def test_parse_plus_shorthand_with_opponent_context_and_partial_player_name() -> None:
    legs = parse_text('Draymond 5+ Assists Vs Thunder')
    assert len(legs) == 1
    leg = legs[0]
    assert leg.player == 'Draymond'
    assert leg.market_type == 'player_assists'
    assert leg.direction == 'over'
    assert leg.line == 4.5
    assert 'Opponent context: Oklahoma City Thunder' in leg.notes


def test_parse_plus_shorthand_points_for_non_alias_player_name() -> None:
    legs = parse_text('Gui Santos 20+ Points Vs OKC')
    assert len(legs) == 1
    leg = legs[0]
    assert leg.player == 'Gui Santos'
    assert leg.market_type == 'player_points'
    assert leg.line == 19.5
    assert leg.confidence >= 0.8
    assert 'Opponent context: Oklahoma City Thunder' in leg.notes


def test_parse_scotty_pippen_alias_to_scotty_pippen_jr() -> None:
    legs = parse_text('Scotty Pippen over 5.5 assists')
    assert len(legs) == 1
    assert legs[0].player == 'Scotty Pippen Jr.'


def test_parse_threes_made_alias_maps_to_player_threes() -> None:
    legs = parse_text('Nikola Jokic over 1.5 3pt made')
    assert len(legs) == 1
    assert legs[0].market_type == 'player_threes'

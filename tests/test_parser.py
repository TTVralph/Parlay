from app.parser import parse_text


def test_parse_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    legs = parse_text(text)
    assert len(legs) == 3
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].market_type == 'player_points'
    assert legs[1].team == 'Denver Nuggets'
    assert legs[2].market_type == 'player_threes'

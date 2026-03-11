from app.parser import parse_text


def test_parse_play_by_play_market_aliases() -> None:
    cases = [
        ('Jokic first basket', 'player_first_basket'),
        ('Nikola Jokic to score first', 'player_first_basket'),
        ('Jokic first rebound', 'player_first_rebound'),
        ('Jokic first assist', 'player_first_assist'),
        ('Jokic first 3 pointer', 'player_first_three'),
        ('Jokic last basket', 'player_last_basket'),
    ]
    for text, expected_market in cases:
        legs = parse_text(text)
        assert len(legs) == 1
        assert legs[0].market_type == expected_market
        assert legs[0].direction == 'yes'

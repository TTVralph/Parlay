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
    assert leg.player == 'Draymond Green'
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


def test_pts_plus_ast_normalizes_to_player_pa_without_low_confidence() -> None:
    legs = parse_text('Bam Adebayo Over 23.5 Pts + Ast')
    assert len(legs) == 1
    assert legs[0].market_type == 'player_pa'
    assert legs[0].confidence >= 0.9
    assert 'Could not parse stat type' not in legs[0].notes


def test_parse_handles_unicode_and_apostrophes_without_market_errors() -> None:
    legs = parse_text("Nikola Topić Over 10.5 Points\nKel'el Ware Over 10.5 Points\nOG Anunoby Under 2.5 Assists")
    assert len(legs) == 3
    assert all('Could not parse stat type' not in leg.notes for leg in legs)
    assert legs[0].market_type == 'player_points'
    assert legs[1].market_type == 'player_points'
    assert legs[2].market_type == 'player_assists'


def test_parse_shorthand_stat_aliases_are_consistent() -> None:
    lines = (
        'Jayson Tatum O26.5 PTS\n'
        'Domantas Sabonis over 12.5 rebs\n'
        'Trae Young under 10.5 asts\n'
        'Stephen Curry over 4.5 three-pointers\n'
        'Nikola Jokic over 47.5 PRA'
    )
    legs = parse_text(lines)
    assert [leg.market_type for leg in legs] == [
        'player_points',
        'player_rebounds',
        'player_assists',
        'player_threes',
        'player_pra',
    ]
    assert all(leg.parse_confidence and leg.parse_confidence >= 0.9 for leg in legs)


def test_parse_rejects_nonsense_as_unmatched() -> None:
    legs = parse_text('hello\nthis is a test\nrandom bet')
    assert len(legs) == 3
    assert all(leg.confidence == 0.0 for leg in legs)
    assert all('Unmatched leg' in leg.notes for leg in legs)

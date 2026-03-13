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


def test_parse_extracts_odds_without_dropping_legs() -> None:
    text = 'Draymond Green Over 5.5 Assists +500\nQuentin Grimes Over 22.5 Pts + Ast +250'
    legs = parse_text(text)
    assert len(legs) == 2
    assert legs[0].raw_text == 'Draymond Green Over 5.5 Assists'
    assert legs[0].market_type == 'player_assists'
    assert legs[0].american_odds == 500
    assert legs[0].decimal_odds == 6.0
    assert legs[1].raw_text == 'Quentin Grimes Over 22.5 Pts + Ast'
    assert legs[1].market_type == 'player_pa'
    assert legs[1].american_odds == 250
    assert legs[1].decimal_odds == 3.5


def test_parse_leg_without_odds_keeps_odds_empty() -> None:
    legs = parse_text('Jalen Brunson Over 25.5 Points')
    assert len(legs) == 1
    assert legs[0].american_odds is None
    assert legs[0].decimal_odds is None


def test_parse_odds_on_separate_line_attach_to_previous_leg() -> None:
    text = 'Jalen Brunson Over 25.5 Points\n+130\nOG Anunoby Under 2.5 Assists\nOdds -120'
    legs = parse_text(text)
    assert len(legs) == 2
    assert legs[0].raw_text == 'Jalen Brunson Over 25.5 Points'
    assert legs[0].american_odds == 130
    assert legs[1].raw_text == 'OG Anunoby Under 2.5 Assists'
    assert legs[1].american_odds == -120


def test_parse_initial_based_name_stays_ambiguous() -> None:
    legs = parse_text('J Brown Over 24.5 Points')
    assert len(legs) == 1
    assert legs[0].player == 'J Brown'
    assert legs[0].confidence <= 0.62
    assert any('player identity ambiguous' in note.lower() for note in legs[0].notes)


def test_parse_noisy_book_formatting_is_normalized() -> None:
    text = 'NIKOLA JOKIC: o24.5 pts, +100 | murray O 2.5 3pm (-125)'
    legs = parse_text(text)
    assert len(legs) == 2
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].american_odds == 100
    assert legs[1].player == 'Jamal Murray'
    assert legs[1].market_type == 'player_threes'
    assert legs[1].american_odds == -125


def test_parse_opponent_context_at_and_matchup_suffixes() -> None:
    at_legs = parse_text('Trae Young over 9.5 assists @ Lakers')
    matchup_legs = parse_text('Donovan Mitchell over 27.5 points (DEN vs LAL)')
    assert len(at_legs) == 1
    assert len(matchup_legs) == 1
    assert 'Opponent context: Los Angeles Lakers' in at_legs[0].notes
    assert 'Opponent context: Los Angeles Lakers' in matchup_legs[0].notes




def test_parse_matchup_line_attaches_game_matchup_context_with_alias_resolution() -> None:
    legs = parse_text('Dyson Daniels Over 9.5 Points\nNets @ Hawks')
    assert len(legs) == 1
    leg = legs[0]
    assert leg.game_matchup == 'Brooklyn Nets @ Atlanta Hawks'
    assert leg.possible_teams == ['Brooklyn Nets', 'Atlanta Hawks']
    assert any(note.startswith('Game matchup context: ') for note in leg.notes)


def test_parse_matchup_line_supports_vs_and_at_formats() -> None:
    vs_legs = parse_text('Dyson Daniels Over 9.5 Points\nBucks vs Heat')
    at_legs = parse_text('Dyson Daniels Over 9.5 Points\nWizards at Magic')
    assert vs_legs[0].game_matchup == 'Milwaukee Bucks @ Miami Heat'
    assert at_legs[0].game_matchup == 'Washington Wizards @ Orlando Magic'

def test_parse_number_first_notation() -> None:
    legs = parse_text('24.5+ points Nikola Jokic')
    assert len(legs) == 1
    assert legs[0].player == 'Nikola Jokic'
    assert legs[0].direction == 'over'
    assert legs[0].line == 24.0




def test_parse_to_score_milestone_points_normalizes_line() -> None:
    legs = parse_text('Dyson Daniels TO SCORE 10+ POINTS')
    assert len(legs) == 1
    leg = legs[0]
    assert leg.player == 'Dyson Daniels'
    assert leg.market_type == 'player_points'
    assert leg.direction == 'over'
    assert leg.line == 9.5
    assert leg.display_line == '10+'


def test_parse_to_record_milestone_rebounds_and_assists_normalizes_line() -> None:
    legs = parse_text('Dyson Daniels TO RECORD 8+ REBOUNDS\nDyson Daniels TO RECORD 8+ ASSISTS')
    assert len(legs) == 2
    assert legs[0].market_type == 'player_rebounds'
    assert legs[0].line == 7.5
    assert legs[0].display_line == '8+'
    assert legs[1].market_type == 'player_assists'
    assert legs[1].line == 7.5
    assert legs[1].display_line == '8+'

def test_parse_first_half_team_markets_remain_unmatched_until_registry_support() -> None:
    legs = parse_text('First Half Over 110.5\nLakers 1H -3.5')
    assert len(legs) == 2
    assert all(leg.market_type not in {'first_half_total', 'first_half_spread'} for leg in legs)

from app.models import Leg
from app.services.betstack_provider import BetStackProvider
from app.services.slip_risk_analyzer import analyze_leg_risk


def test_normalize_supported_event_markets() -> None:
    provider = BetStackProvider(api_key='x')

    spread = provider._normalize_event_market_row({'market': 'spreads', 'line': '-3.5', 'team': 'Denver'})
    total = provider._normalize_event_market_row({'market': 'totals', 'total': '228.5'})
    ml = provider._normalize_event_market_row({'market': 'h2h', 'odds': '-120', 'team': 'Denver'})

    assert spread and spread['market_type'] == 'spread' and spread['line'] == -3.5
    assert total and total['market_type'] == 'game_total' and total['line'] == 228.5
    assert ml and ml['market_type'] == 'moneyline' and ml['american_odds'] == -120.0


def test_normalize_supported_player_prop_markets() -> None:
    provider = BetStackProvider(api_key='x')
    row = provider._normalize_player_prop_row({'market': 'points', 'player_name': 'Nikola Jokic', 'line': '24.5', 'direction': 'over'})
    combo = provider._normalize_player_prop_row({'market': 'pra', 'player': 'Nikola Jokic', 'value': '39.5', 'side': 'under'})

    assert row and row['market_type'] == 'player_points' and row['line'] == 24.5
    assert combo and combo['market_type'] == 'player_pra' and combo['direction'] == 'under'


def test_analyze_leg_uses_betstack_consensus_when_found(monkeypatch) -> None:
    leg = Leg(
        raw_text='Jokic over 24.5 points',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.9,
    )

    class FakeProvider:
        enabled = True

        def fetch_all_odds(self, *, sport: str = 'basketball'):
            return [{'market_type': 'player_points', 'line': 25.5, 'normalized_player': 'jokic nikola'}]

        def lookup_leg_line_from_odds(self, _: Leg, odds_rows):
            return odds_rows[0]

    monkeypatch.setattr('app.services.slip_risk_analyzer.BetStackProvider.from_env', lambda: FakeProvider())

    analyzed = analyze_leg_risk(leg)

    assert analyzed.market_line == 25.5
    assert analyzed.line_difference == -1.0
    assert analyzed.line_value_source == 'betstack_consensus'


def test_analyze_leg_falls_back_to_statistical_baseline_when_no_betstack_match(monkeypatch) -> None:
    leg = Leg(
        raw_text='Jokic over 24.5 points',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.9,
    )

    class FakeProvider:
        enabled = True

        def fetch_all_odds(self, *, sport: str = 'basketball'):
            return []

        def lookup_leg_line_from_odds(self, _: Leg, odds_rows):
            return None

    monkeypatch.setattr('app.services.slip_risk_analyzer.BetStackProvider.from_env', lambda: FakeProvider())

    analyzed = analyze_leg_risk(leg)

    assert analyzed.market_line is None
    assert analyzed.line_value_source == 'statistical_baseline'
    assert analyzed.line_value_text == 'Consensus line unavailable. Using statistical baseline.'


def test_settlement_models_unchanged_by_analyzer_extension() -> None:
    leg = Leg(raw_text='Denver ML', market_type='moneyline', team='Denver Nuggets', confidence=0.9)
    assert hasattr(leg, 'market_type')
    assert not hasattr(leg, 'line_value_source')


def test_analyze_slip_fetches_betstack_once_for_all_legs(monkeypatch) -> None:
    from app.services.slip_risk_analyzer import analyze_slip_risk

    calls = {'fetch': 0}

    class FakeProvider:
        enabled = True

        def fetch_all_odds(self, *, sport: str = 'basketball'):
            calls['fetch'] += 1
            return [{'market_type': 'player_points', 'line': 25.5, 'normalized_player': 'jokic nikola'}]

        def lookup_leg_line_from_odds(self, _: Leg, odds_rows):
            return odds_rows[0] if odds_rows else None

    monkeypatch.setattr('app.services.slip_risk_analyzer.BetStackProvider.from_env', lambda: FakeProvider())

    legs = [
        Leg(raw_text='Jokic over 24.5 points', market_type='player_points', player='Nikola Jokic', direction='over', line=24.5, confidence=0.9),
        Leg(raw_text='Jokic over 26.5 points', market_type='player_points', player='Nikola Jokic', direction='over', line=26.5, confidence=0.9),
    ]

    response = analyze_slip_risk(legs)

    assert response.ok is True
    assert calls['fetch'] == 1

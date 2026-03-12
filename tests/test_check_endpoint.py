import json
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_check_empty_textarea_message():
    res = client.post('/check', json={'text': '   '})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Paste at least one leg first.'
    assert body['legs'] == []
    assert body['parsed_legs'] == []


def test_check_no_legs_parsed_message(monkeypatch):
    monkeypatch.setattr('app.main.parse_text', lambda _text: [])
    res = client.post('/check', json={'text': 'LeBron over 20.5 points'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No valid betting legs detected.'
    assert body['parse_warning'] == 'No valid betting legs detected.'


def test_check_grading_error_message(monkeypatch):
    def _raise(_text):
        raise RuntimeError('boom')

    monkeypatch.setattr('app.main.grade_text', _raise)
    res = client.post('/check', json={'text': 'Celtics ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Could not grade this slip right now.'
    assert body['grading_warning'] == 'Parsed legs were detected, but grading did not complete.'


def test_check_with_stake_returns_estimated_payout_and_profit():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 20})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['estimated_profit'] == 30.0
    assert body['estimated_payout'] == 50.0
    assert body['american_odds_used'] == [150]
    assert body['decimal_odds_used'] == 2.5
    assert body['parsed_legs'] == ['Denver ML']


def test_check_rejects_invalid_stake():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 'abc'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Enter a valid numeric stake amount.'
    assert body['parsed_legs'] == []


def test_check_maps_pending_to_still_live():
    res = client.post('/check-slip', json={'text': 'Nikola Jokic over 250.5 passing yards'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['parlay_result'] in {'still_live', 'needs_review'}
    assert body['legs'][0]['result'] in {'pending', 'review'}


def test_check_sets_grading_warning_when_all_legs_unmatched(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None):
        leg = Leg(raw_text='Denver ML', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95)
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)
    res = client.post('/check-slip', json={'text': 'Denver ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['grading_warning'] == 'Parsed legs were detected, but ESPN matching could not settle any leg.'


def test_check_nonsense_input_is_rejected():
    res = client.post('/check-slip', json={'text': 'hello\nthis is a test\nrandom bet'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No valid betting legs detected.'
    assert body['legs'] == []


def test_check_with_stake_without_odds_preserves_full_grading_payload(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    res = client.post('/check-slip', json={'text': 'Denver ML', 'stake_amount': 100})
    assert res.status_code == 200
    body = res.json()

    assert body['ok'] is True
    assert body['message']
    assert body['payout_message'] == 'Add odds in your slip text (for example +120) to estimate payout.'
    assert body['stake_amount'] == 100.0
    assert 'estimated_profit' not in body
    assert 'estimated_payout' not in body
    assert body['parsed_legs'] == ['Denver ML']
    assert body['legs']
    assert 'parse_confidence' in body


def test_check_same_slip_payload_shape_matches_with_or_without_stake(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    base = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    with_stake_no_odds = client.post('/check-slip', json={'text': 'Denver ML', 'stake_amount': 100}).json()

    shared_keys = {'ok', 'legs', 'parsed_legs', 'parse_warning', 'grading_warning', 'parlay_result', 'parse_confidence'}
    for key in shared_keys:
        assert with_stake_no_odds[key] == base[key]
    assert with_stake_no_odds['message'] == base['message']


def test_check_with_stake_and_odds_keeps_full_payload_and_adds_payout(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 100})
    assert res.status_code == 200
    body = res.json()

    assert body['ok'] is True
    assert body['message']
    assert body['parsed_legs'] == ['Denver ML']
    assert body['legs']
    assert 'parse_confidence' in body
    assert body['stake_amount'] == 100.0
    assert body['estimated_profit'] == 150.0
    assert body['estimated_payout'] == 250.0
    assert body['american_odds_used'] == [150]
    assert body['decimal_odds_used'] == 2.5


def test_check_with_multi_leg_odds_multiplies_parlay_payout(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    text = 'Draymond Green Over 5.5 Assists +500\nQuentin Grimes Over 22.5 Pts + Ast +250'
    res = client.post('/check-slip', json={'text': text, 'stake_amount': 100})
    assert res.status_code == 200
    body = res.json()

    assert body['ok'] is True
    assert body['parsed_legs'] == ['Draymond Green Over 5.5 Assists', 'Quentin Grimes Over 22.5 Pts + Ast']
    assert body['american_odds_used'] == [500, 250]
    assert body['decimal_odds_used'] == 21.0
    assert body['estimated_payout'] == 2100.0
    assert body['estimated_profit'] == 2000.0


def test_check_with_mixed_leg_odds_uses_ticket_level_odds(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    text = 'Denver ML +150\nNikola Jokic Over 24.5 Points'
    res = client.post('/check-slip', json={'text': text, 'stake_amount': 50})
    assert res.status_code == 200
    body = res.json()

    assert body['ok'] is True
    assert body['estimated_profit'] == 75.0
    assert body['estimated_payout'] == 125.0
    assert body['american_odds_used'] == 150

def test_check_empty_slip_after_previous_result_returns_reset_payload(monkeypatch):
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)

    first = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    assert first['ok'] is True
    assert first['legs']

    second_resp = client.post('/check-slip', json={'text': '   '})
    assert second_resp.status_code == 200
    second = second_resp.json()
    assert second['ok'] is False
    assert second['legs'] == []
    assert second['parsed_legs'] == []
    assert second['parlay_result'] == 'needs_review'
    assert second['message'] == 'Paste at least one leg first.'


def test_check_unresolved_player_includes_did_you_mean_suggestion(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Shai Gilly-Alexander O5.5 AST',
            sport='NBA',
            market_type='player_assists',
            player='Shai Gilly-Alexander',
            direction='over',
            line=5.5,
            confidence=0.9,
            candidate_players=['Shai Gilgeous-Alexander'],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player not found in sport directory')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Shai Gilly-Alexander O5.5 AST'}).json()
    assert body['ok'] is True
    assert body['legs'][0]['did_you_mean'] == 'Did you mean: Shai Gilgeous-Alexander?'
    assert body['legs'][0]['result'] == 'review'


def test_check_mixed_valid_and_invalid_legs_keeps_partial_results(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        good = Leg(raw_text='Denver ML', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95)
        bad = Leg(raw_text='Typo Name O5.5 AST', sport='NBA', market_type='player_assists', player='Typo Name', direction='over', line=5.5, confidence=0.92)
        return GradeResponse(
            overall='needs_review',
            legs=[
                GradedLeg(leg=good, settlement='win', reason='ok'),
                GradedLeg(leg=bad, settlement='unmatched', reason='x', review_reason='player not found in sport directory', candidate_players=['Tyus Jones']),
            ],
        )

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Denver ML\nTypo Name O5.5 AST'}).json()
    assert body['ok'] is True
    assert len(body['legs']) == 2
    assert body['legs'][0]['result'] == 'win'
    assert body['legs'][1]['result'] == 'review'
    assert body['grading_warning'] == '1 leg(s) need manual review.'


def test_check_review_leg_includes_structured_review_metadata(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Jamal Murray over 2.5 threes',
            sport='NBA',
            market_type='player_threes',
            player='Jamal Murray',
            direction='over',
            line=2.5,
            confidence=0.9,
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            candidate_players=['Jamal Murray'],
            event_candidates=[
                {'event_id': 'evt1', 'event_label': 'A @ B'},
                {'event_id': 'evt2', 'event_label': 'C @ D'},
            ],
            notes=['Multiple possible games. Add bet date to narrow results.'],
        )
        graded = GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')
        return GradeResponse(overall='needs_review', legs=[graded])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jamal Murray over 2.5 threes'}).json()
    details = body['legs'][0]['review_details']
    assert details['player_resolution_status'] == 'ambiguous'
    assert details['player_resolution_method'] == 'manual_review'
    assert details['player_resolution_explanation'] == 'player identity ambiguous'
    assert details['candidate_count'] == 1
    assert details['matched_event_count'] == 0
    assert details['event_resolution_source'] == 'player'
    assert details['review_reason_code'] == 'PLAYER_AMBIGUOUS'
    assert details['review_reason_text']


def test_check_review_typo_leg_keeps_did_you_mean_in_structured_metadata(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Shai Gilly-Alexander O5.5 AST',
            sport='NBA',
            market_type='player_assists',
            player='Shai Gilly-Alexander',
            direction='over',
            line=5.5,
            confidence=0.9,
            candidate_players=['Shai Gilgeous-Alexander'],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player not found in sport directory')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Shai Gilly-Alexander O5.5 AST'}).json()
    assert body['legs'][0]['review_details']['did_you_mean'] == 'Did you mean: Shai Gilgeous-Alexander?'
    assert body['legs'][0]['review_details']['review_reason_code'] == 'PLAYER_UNRESOLVED'


def test_check_multiple_event_candidates_maps_multiple_games_reason_code(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Denver ML',
            sport='NBA',
            market_type='moneyline',
            team='Denver Nuggets',
            confidence=0.9,
            event_candidates=[
                {'event_id': 'evt1', 'event_label': 'A @ B'},
                {'event_id': 'evt2', 'event_label': 'C @ D'},
            ],
            notes=['Multiple possible games. Add bet date to narrow results.'],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='event unresolved')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    assert body['legs'][0]['review_details']['review_reason_code'] == 'MULTIPLE_GAMES_MATCHED'




def test_check_unsupported_market_review_uses_unsupported_reason_code(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg, SettlementExplanation

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Race to 10 points - Denver Nuggets',
            sport='NBA',
            market_type='moneyline',
            team='Denver Nuggets',
            confidence=0.86,
            notes=['Unsupported market -> safe review preserve']
        )
        explanation = SettlementExplanation(
            raw_leg_text=leg.raw_text,
            settlement_reason_code='unsupported_market',
            settlement_reason='Unsupported market',
            settlement_reason_text='Special market support is limited for this leg.',
            result='unmatched',
            grading_confidence=0.21,
        )
        graded = GradedLeg(
            leg=leg,
            settlement='unmatched',
            reason='x',
            review_reason='unsupported market',
            settlement_explanation=explanation,
            settlement_diagnostics={'unmatched_reason_code': 'unsupported_market'},
        )
        return GradeResponse(overall='needs_review', legs=[graded])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    details = body['legs'][0]['review_details']
    assert body['legs'][0]['result'] == 'review'
    assert details['review_reason_code'] == 'UNSUPPORTED_MARKET'
    assert 'Recognized but not fully supported yet' in details['review_reason_text']
def test_check_valid_leg_does_not_include_review_details(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(raw_text='Denver ML', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, event_id='evt1', event_label='A @ B')
        return GradeResponse(overall='cashed', legs=[GradedLeg(leg=leg, settlement='win', reason='ok')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    assert body['legs'][0]['result'] == 'win'
    assert body['legs'][0]['review_details'] is None
    assert body['legs'][0]['player_resolution_status'] == 'exact'
    assert body['legs'][0]['player_resolution_method'] == 'exact'


def test_check_single_strong_candidate_leg_includes_player_resolution_metadata(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Shai Gilly Alexander O5.5 AST',
            sport='NBA',
            market_type='player_assists',
            player='Shai Gilly Alexander',
            resolved_player_name='Shai Gilgeous-Alexander',
            resolved_player_id='nba:1628983',
            identity_match_method='single_strong_candidate',
            identity_match_confidence='MEDIUM',
            resolution_confidence=0.74,
            direction='over',
            line=5.5,
            confidence=0.9,
        )
        return GradeResponse(overall='pending', legs=[GradedLeg(leg=leg, settlement='pending', reason='ok')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Shai Gilly Alexander O5.5 AST'}).json()
    leg = body['legs'][0]
    assert leg['player_resolution_status'] == 'fuzzy_resolved'
    assert leg['player_resolution_method'] == 'single_strong_candidate'
    assert leg['player_resolution_confidence'] == 'medium'
    assert leg['resolution_details']['canonical_matched_player_name'] == 'Shai Gilgeous-Alexander'


def test_check_ambiguous_unresolved_leg_includes_specific_explanation(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Jalen over 20.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalen',
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            resolution_ambiguity_reason='Multiple close player candidates found for "Jalen".',
            candidate_players=['Jalen Brunson', 'Jalen Green'],
            direction='over',
            line=20.5,
            confidence=0.9,
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jalen over 20.5 points'}).json()
    details = body['legs'][0]['review_details']
    assert details['player_resolution_status'] == 'ambiguous'
    assert details['player_resolution_explanation'] == 'Multiple close player candidates found for "Jalen".'


def test_check_ambiguous_shorthand_stays_review_without_autocorrect(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Jalen over 20.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalen',
            parsed_player_name='Jalen',
            direction='over',
            line=20.5,
            confidence=0.9,
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            candidate_players=['Jalen Brunson', 'Jalen Green'],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jalen over 20.5 points'}).json()
    leg = body['legs'][0]
    assert leg['result'] == 'review'
    assert leg['review_details']['player_resolution_status'] == 'ambiguous'
    assert leg['parsed_player_name'] == 'Jalen'
    assert leg['resolved_player_name'] is None


def test_check_unresolved_typo_returns_candidate_player_objects(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Shai Gilly-Alexander O5.5 AST',
            sport='NBA',
            market_type='player_assists',
            player='Shai Gilly-Alexander',
            direction='over',
            line=5.5,
            confidence=0.9,
            candidate_players=['Shai Gilgeous-Alexander'],
            candidate_player_details=[
                {
                    'player_name': 'Shai Gilgeous-Alexander',
                    'team_name': 'Oklahoma City Thunder',
                    'player_id': 'nba-shai-gilgeous-alexander',
                    'match_confidence': 0.85,
                    'rank': 1,
                    'reason': 'close typo match',
                }
            ],
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player not found in sport directory')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Shai Gilly-Alexander O5.5 AST'}).json()
    candidate = body['legs'][0]['candidate_players'][0]
    assert candidate['player_name'] == 'Shai Gilgeous-Alexander'
    assert candidate['team_name'] == 'Oklahoma City Thunder'
    assert candidate['player_id'] == 'nba-shai-gilgeous-alexander'
    assert candidate['match_confidence'] == 0.85
    assert candidate['reason'] == 'close typo match'


def test_check_ambiguous_name_returns_multiple_candidate_players(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Jalen over 20.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalen',
            direction='over',
            line=20.5,
            confidence=0.9,
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            candidate_players=['Jalen Brunson', 'Jalen Green'],
            candidate_player_details=[
                {'player_name': 'Jalen Brunson', 'team_name': 'New York Knicks', 'player_id': 'nba-jalen-brunson', 'match_confidence': 0.79, 'rank': 1, 'reason': 'ambiguous first/last name'},
                {'player_name': 'Jalen Green', 'team_name': 'Houston Rockets', 'player_id': 'nba-jalen-green', 'match_confidence': 0.78, 'rank': 2, 'reason': 'ambiguous first/last name'},
            ],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jalen over 20.5 points'}).json()
    candidates = body['legs'][0]['candidate_players']
    assert len(candidates) == 2
    assert [item['player_name'] for item in candidates] == ['Jalen Brunson', 'Jalen Green']
    assert body['legs'][0]['review_details']['player_resolution_status'] == 'ambiguous'


def test_check_selected_candidate_reruns_grading_and_preserves_original_leg_text(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    captured_kwargs = {}

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        captured_kwargs.clear()
        captured_kwargs.update(kwargs)
        selected = (kwargs.get('selected_player_by_leg_id') or {}).get('0')
        if selected == 'nba-shai-gilgeous-alexander':
            leg = Leg(
                raw_text='Shai Gilly-Alexander O5.5 AST',
                sport='NBA',
                market_type='player_assists',
                player='Shai Gilly-Alexander',
                parsed_player_name='Shai Gilly-Alexander',
                resolved_player_name='Shai Gilgeous-Alexander',
                resolved_player_id='nba-shai-gilgeous-alexander',
                selected_player_name='Shai Gilgeous-Alexander',
                selected_player_id='nba-shai-gilgeous-alexander',
                selection_source='user_selected',
                selection_explanation='Used user-selected player: Shai Gilgeous-Alexander',
                canonical_player_name='Shai Gilgeous-Alexander',
                event_id='evt-1',
                event_label='OKC @ LAL',
                confidence=0.9,
                identity_match_method='manual_selection',
                identity_match_confidence='HIGH',
                override_used_for_grading=True,
            )
            return GradeResponse(overall='pending', legs=[GradedLeg(leg=leg, settlement='pending', reason='ok')])

        leg = Leg(
            raw_text='Shai Gilly-Alexander O5.5 AST',
            sport='NBA',
            market_type='player_assists',
            player='Shai Gilly-Alexander',
            confidence=0.9,
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            candidate_players=['Shai Gilgeous-Alexander'],
            candidate_player_details=[{'player_name': 'Shai Gilgeous-Alexander', 'player_id': 'nba-shai-gilgeous-alexander', 'team_name': 'Oklahoma City Thunder', 'match_confidence': 0.85, 'rank': 1, 'reason': 'close typo match'}],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player not found in sport directory')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    first = client.post('/check-slip', json={'text': 'Shai Gilly-Alexander O5.5 AST'}).json()
    assert first['legs'][0]['result'] == 'review'

    second = client.post('/check-slip', json={'text': 'Shai Gilly-Alexander O5.5 AST', 'selected_player_by_leg_id': {'0': 'nba-shai-gilgeous-alexander'}}).json()
    assert second['legs'][0]['result'] == 'pending'
    assert second['legs'][0]['leg'] == 'Shai Gilly-Alexander O5.5 AST'
    assert second['legs'][0]['resolved_player_name'] == 'Shai Gilgeous-Alexander'
    assert second['legs'][0]['player_selection_applied'] is True
    assert second['legs'][0]['selection_source'] == 'user_selected'
    assert second['legs'][0]['selected_player_name'] == 'Shai Gilgeous-Alexander'
    assert second['legs'][0]['selected_player_id'] == 'nba-shai-gilgeous-alexander'
    assert second['legs'][0]['canonical_player_name'] == 'Shai Gilgeous-Alexander'
    assert second['legs'][0]['selection_explanation'] == 'Used user-selected player: Shai Gilgeous-Alexander'
    assert second['legs'][0]['override_used_for_grading'] is True
    assert second['legs'][0]['candidate_players'] == []
    assert second['legs'][0]['review_details'] is None
    assert captured_kwargs['selected_player_by_leg_id'] == {'0': 'nba-shai-gilgeous-alexander'}


def test_check_no_automatic_correction_without_player_selection(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        assert kwargs.get('selected_player_by_leg_id') in (None, {})
        leg = Leg(
            raw_text='Jalyen Wiliams over 18.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalyen Wiliams',
            confidence=0.9,
            identity_match_method='ambiguous',
            identity_match_confidence='LOW',
            candidate_players=['Jalen Williams'],
            candidate_player_details=[{'player_name': 'Jalen Williams', 'team_name': 'Oklahoma City Thunder', 'player_id': 'nba-jalen-williams', 'match_confidence': 0.83, 'rank': 1, 'reason': 'close typo match'}],
        )
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jalyen Wiliams over 18.5 points'}).json()
    assert body['legs'][0]['result'] == 'review'
    assert body['legs'][0]['resolved_player_name'] is None
    assert body['legs'][0]['review_details']['player_resolution_status'] == 'ambiguous'


def test_check_slip_public_page_retains_manual_selection_context(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        selected = (kwargs.get('selected_player_by_leg_id') or {}).get('0')
        leg = Leg(
            raw_text='Jalen over 20.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalen',
            parsed_player_name='Jalen',
            resolved_player_name='Jalen Brunson' if selected else None,
            resolved_player_id='nba-jalen-brunson' if selected else None,
            selected_player_name='Jalen Brunson' if selected else None,
            selected_player_id='nba-jalen-brunson' if selected else None,
            selection_source='user_selected' if selected else None,
            selection_explanation='Used user-selected player: Jalen Brunson' if selected else None,
            canonical_player_name='Jalen Brunson' if selected else None,
            confidence=0.9,
            identity_match_method='manual_selection' if selected else 'ambiguous',
            identity_match_confidence='HIGH' if selected else 'LOW',
            candidate_players=[] if selected else ['Jalen Brunson', 'Jalen Green'],
            candidate_player_details=[] if selected else [
                {'player_name': 'Jalen Brunson', 'team_name': 'New York Knicks', 'player_id': 'nba-jalen-brunson', 'match_confidence': 0.8, 'rank': 1, 'reason': 'ambiguous first/last name'},
                {'player_name': 'Jalen Green', 'team_name': 'Houston Rockets', 'player_id': 'nba-jalen-green', 'match_confidence': 0.79, 'rank': 2, 'reason': 'ambiguous first/last name'},
            ],
        )
        settlement='pending' if selected else 'unmatched'
        return GradeResponse(overall='pending' if selected else 'needs_review', legs=[GradedLeg(leg=leg, settlement=settlement, reason='ok', review_reason='player identity ambiguous' if not selected else None)])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Jalen over 20.5 points', 'selected_player_by_leg_id': {'0': 'nba-jalen-brunson'}}).json()
    assert body['legs'][0]['selection_source'] == 'user_selected'
    assert body['legs'][0]['selected_player_name'] == 'Jalen Brunson'
    assert body['public_url']

    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'Selected player:' in page.text
    assert 'Jalen Brunson' in page.text


def test_check_selected_player_leg_id_keys_are_normalized_to_strings(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    captured = {}

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        captured.update(kwargs)
        leg = Leg(raw_text='LeBron over 25.5 points', sport='NBA', market_type='player_points', player='LeBron', confidence=0.9)
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='player identity ambiguous')])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    res = client.post('/check-slip', json={'text': 'LeBron over 25.5 points', 'selected_player_by_leg_id': {0: 'nba-espn-123'}})
    assert res.status_code == 200
    assert captured['selected_player_by_leg_id'] == {'0': 'nba-espn-123'}


def test_resolve_leg_events_invalid_selected_player_id_is_non_fatal(monkeypatch):
    from app.models import Leg
    from app.identity_resolution import PlayerResolutionResult
    from app.resolver import resolve_leg_events

    class _Provider:
        pass

    monkeypatch.setattr('app.resolver.get_canonical_player_identity', lambda player_id, sport='NBA': None)
    monkeypatch.setattr('app.resolver.resolve_player_identity', lambda player_name, sport='NBA': PlayerResolutionResult(
        sport=sport,
        resolved_player_name=None,
        resolved_player_id=None,
        resolved_team=None,
        confidence=0.0,
        ambiguity_reason='player identity ambiguous',
        confidence_level='LOW',
    ))
    monkeypatch.setattr('app.resolver._resolve_player_team', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.resolver._player_candidates', lambda *args, **kwargs: [])

    leg = Leg(raw_text='Christian Braunn over 10.5 points', sport='NBA', market_type='player_points', player='Christian Braunn', confidence=0.95)
    resolved = resolve_leg_events([leg], _Provider(), posted_at=None, selected_player_by_leg_id={'0': 'nba-espn-4431767'})

    assert len(resolved) == 1
    assert resolved[0].raw_text == 'Christian Braunn over 10.5 points'
    assert resolved[0].selection_applied is False
    assert resolved[0].selection_error_code == 'INVALID_SELECTED_PLAYER_ID'


def test_check_invalid_selected_player_id_returns_review_code(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Christian Braunn over 10.5 points',
            sport='NBA',
            market_type='player_points',
            player='Christian Braunn',
            confidence=0.95,
            selection_source='user_selected',
            selection_error_code='INVALID_SELECTED_PLAYER_ID',
            selection_applied=False,
            selection_explanation='Selected player could not be applied because the player ID was not found in the active directory.',
        )
        graded = GradedLeg(
            leg=leg,
            settlement='unmatched',
            reason='Selected player override is invalid',
            review_reason='Selected player could not be applied because the player ID was not found in the active directory.',
            review_reason_text='Selected player could not be applied because the player ID was not found in the active directory.',
            selection_error_code='INVALID_SELECTED_PLAYER_ID',
        )
        return GradeResponse(overall='needs_review', legs=[graded])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Christian Braunn over 10.5 points', 'selected_player_by_leg_id': {'0': 'nba-espn-4431767'}}).json()
    assert body['ok'] is True
    assert body['legs'][0]['result'] == 'review'
    assert body['legs'][0]['review_details']['review_reason_code'] == 'INVALID_SELECTED_PLAYER_ID'
    assert 'could not be applied' in body['legs'][0]['review_reason_text'].lower()


def test_check_review_reason_text_uses_specific_message_not_generic(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(raw_text='Lebrun over 25.5 points', sport='NBA', market_type='player_points', player='Lebrun', confidence=0.95)
        graded = GradedLeg(
            leg=leg,
            settlement='unmatched',
            reason='Low-confidence identity match requires review',
            review_reason='player identity ambiguous',
            review_reason_text='Review: player/event validation failed',
            identity_match_confidence='LOW',
            identity_match_method='ambiguous',
        )
        return GradeResponse(overall='needs_review', legs=[graded])

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Lebrun over 25.5 points'}).json()
    reason = body['legs'][0]['review_reason_text']
    assert reason == 'Multiple plausible player matches found; select the correct player.'
    assert reason != 'Review: player/event validation failed'


def test_check_slip_public_page_persists_override_player_and_event_state(monkeypatch):
    from app.db.session import SessionLocal
    from app.models import GradeResponse, GradedLeg, Leg
    from app.services.repository import get_public_slip_result

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        selected_player = (kwargs.get('selected_player_by_leg_id') or {}).get('0')
        selected_event = (kwargs.get('selected_event_by_leg_id') or {}).get('0')
        leg = Leg(
            raw_text='Jalen over 20.5 points',
            sport='NBA',
            market_type='player_points',
            player='Jalen',
            selected_player_name='Jalen Brunson' if selected_player else None,
            selected_player_id='nba-jalen-brunson' if selected_player else None,
            selection_source='user_selected' if selected_player else None,
            selection_explanation='Used user-selected player: Jalen Brunson' if selected_player else None,
            event_selection_applied=bool(selected_event),
            selected_event_id='evt-123' if selected_event else None,
            selected_event_label='Knicks @ Celtics' if selected_event else None,
            override_used_for_grading=bool(selected_player or selected_event),
            event_review_reason_text='Multiple possible games matched this leg' if not selected_event else None,
            confidence=0.9,
        )
        return GradeResponse(
            overall='pending',
            legs=[
                GradedLeg(
                    leg=leg,
                    settlement='pending',
                    reason='ok',
                    selection_applied=bool(selected_player),
                    event_selection_applied=bool(selected_event),
                    selected_player_name='Jalen Brunson' if selected_player else None,
                    selected_player_id='nba-jalen-brunson' if selected_player else None,
                    selected_event_id='evt-123' if selected_event else None,
                    selected_event_label='Knicks @ Celtics' if selected_event else None,
                    override_used_for_grading=bool(selected_player or selected_event),
                )
            ],
        )

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={
        'text': 'Jalen over 20.5 points',
        'selected_player_by_leg_id': {'0': 'nba-jalen-brunson'},
        'selected_event_by_leg_id': {'0': 'evt-123'},
    }).json()

    assert body['legs'][0]['override_used_for_grading'] is True
    assert body['legs'][0]['override_grading_explanation'] == 'Used selected player and selected game for grading.'

    db = SessionLocal()
    try:
        saved = get_public_slip_result(db, body['public_id'])
        assert saved is not None
        persisted_leg = json.loads(saved.legs_json)[0]
    finally:
        db.close()

    assert persisted_leg['selected_player_name'] == 'Jalen Brunson'
    assert persisted_leg['selected_player_id'] == 'nba-jalen-brunson'
    assert persisted_leg['player_selection_applied'] is True
    assert persisted_leg['selected_event_id'] == 'evt-123'
    assert persisted_leg['selected_event_label'] == 'Knicks @ Celtics'
    assert persisted_leg['event_selection_applied'] is True
    assert persisted_leg['override_used_for_grading'] is True
    assert persisted_leg['override_grading_explanation'] == 'Used selected player and selected game for grading.'
    assert persisted_leg['selection_source'] == 'user_selected'
    assert persisted_leg['selection_explanation'] == 'Used user-selected player: Jalen Brunson'

    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'Used selected player and selected game for grading.' in page.text
    assert 'Selected player:' in page.text
    assert 'Selected game:' in page.text


def test_check_slip_public_page_preserves_specific_review_reason_on_reopen(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None, **kwargs):
        leg = Leg(
            raw_text='Denver ML',
            sport='NBA',
            market_type='moneyline',
            team='Denver Nuggets',
            confidence=0.9,
            event_review_reason_text='No games found for the selected date window',
        )
        return GradeResponse(
            overall='needs_review',
            legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x', review_reason='No games found for the selected date window')],
        )

    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    monkeypatch.setattr('app.main.grade_text', _grade)

    body = client.post('/check-slip', json={'text': 'Denver ML'}).json()
    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'No games found for the selected date window' in page.text
    assert 'needs manual review' not in page.text.lower()

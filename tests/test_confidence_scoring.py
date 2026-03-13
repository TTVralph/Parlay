from app.models import Leg
from app.services.confidence_scoring import confidence_recommendation, score_leg_confidence


def _base_leg() -> Leg:
    return Leg(
        raw_text='Nikola Jokic over 24.5 points',
        sport='NBA',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.98,
        parse_confidence=0.98,
        identity_match_confidence='HIGH',
        event_resolution_confidence='high',
        event_id='evt-1',
        event_candidates=[{'id': 'evt-1'}],
    )


def test_perfect_ocr_and_exact_match_confidence_is_high() -> None:
    leg = _base_leg()
    scored = score_leg_confidence(leg, input_source_path='screenshot')
    assert scored.confidence_score > 0.9


def test_ocr_noise_but_correct_match_confidence_is_medium_high() -> None:
    leg = _base_leg().model_copy(update={'parse_confidence': 0.72, 'confidence': 0.7, 'event_resolution_confidence': 'medium'})
    scored = score_leg_confidence(leg, input_source_path='screenshot')
    assert 0.75 <= scored.confidence_score <= 0.85


def test_ambiguous_events_confidence_drops_below_threshold() -> None:
    leg = _base_leg().model_copy(
        update={
            'event_resolution_confidence': 'medium',
            'event_candidates': [{'id': 'evt-1'}, {'id': 'evt-2'}],
            'event_review_reason_code': 'ambiguous_event_match',
            'parse_confidence': 0.6,
            'confidence': 0.6,
        }
    )
    scored = score_leg_confidence(leg, input_source_path='screenshot')
    assert scored.confidence_score < 0.7


def test_incorrect_player_confidence_is_low() -> None:
    leg = _base_leg().model_copy(
        update={
            'identity_match_confidence': 'LOW',
            'resolution_confidence': 0.2,
            'parse_confidence': 0.9,
            'event_resolution_confidence': 'low',
            'event_id': None,
            'event_candidates': [{'id': 'evt-1'}, {'id': 'evt-2'}],
        }
    )
    scored = score_leg_confidence(leg, input_source_path='manual_text')
    assert scored.confidence_score < 0.5


def test_manual_event_selection_forces_max_event_match_score() -> None:
    leg = _base_leg().model_copy(
        update={
            'event_selection_source': 'user_selected',
            'event_selection_applied': True,
            'event_resolution_confidence': 'low',
            'event_candidates': [{'id': 'evt-1'}, {'id': 'evt-2'}],
        }
    )
    scored = score_leg_confidence(leg, input_source_path='manual_text')
    assert scored.event_match_score == 1.0


def test_confidence_recommendation_thresholds() -> None:
    assert confidence_recommendation(0.9) == ('high', 'auto_grade')
    assert confidence_recommendation(0.8) == ('medium', 'verify_recommended')
    assert confidence_recommendation(0.59) == ('low', 'needs_review')

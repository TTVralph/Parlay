from __future__ import annotations

from datetime import datetime, timezone

from app.grader import settle_leg
from app.models import Leg
from app.providers.base import EventInfo
from app.services.market_registry import MARKET_REGISTRY
from app.services.provider_router import ProviderRouter


class _BoxScoreProvider:
    def __init__(self) -> None:
        self._event = EventInfo(
            event_id='evt-1',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime.now(timezone.utc),
        )

    def get_event_info(self, event_id: str):
        return self._event

    def is_player_on_event_roster(self, player: str, event_id: str | None = None):
        return True

    def get_event_status(self, event_id: str):
        return 'final'

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        if market_type == 'player_points':
            return 27.0
        return None


class _PlayByPlayProvider:
    def __init__(self, events):
        self.events = events

    def get_normalized_events(self, event_id: str):
        return self.events


class _Evt:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _base_leg(market_type: str, raw_text: str) -> Leg:
    return Leg(
        raw_text=raw_text,
        sport='NBA',
        market_type=market_type,
        player='Nikola Jokic',
        direction='yes',
        line=1.0,
        confidence=0.95,
        event_id='evt-1',
        event_label='Boston Celtics @ Denver Nuggets',
        resolved_team='Denver Nuggets',
        resolved_player_name='Nikola Jokic',
    )


def test_existing_box_score_market_routes_to_box_provider() -> None:
    router = ProviderRouter(box_score_provider=_BoxScoreProvider(), play_by_play_provider=_PlayByPlayProvider([]))
    route = router.route('player_points')
    assert route.data_source == 'box_score'


def test_new_play_by_play_market_routes_to_play_by_play_provider() -> None:
    router = ProviderRouter(box_score_provider=_BoxScoreProvider(), play_by_play_provider=_PlayByPlayProvider([]))
    route = router.route('player_first_basket')
    assert route.data_source == 'play_by_play'


def test_first_basket_settles_from_play_by_play_events() -> None:
    pbp = _PlayByPlayProvider([
        _Evt(is_made_shot=True, primary_player='Nikola Jokic', is_three_pointer_made=False, is_rebound=False, is_assist=False, is_steal=False, is_block=False, assist_player=None, steal_player=None, block_player=None),
    ])
    graded = settle_leg(_base_leg('player_first_basket', 'Jokic first basket'), _BoxScoreProvider(), play_by_play_provider=pbp)
    assert graded.settlement == 'win'


def test_first_rebound_settles_from_play_by_play_events() -> None:
    pbp = _PlayByPlayProvider([
        _Evt(is_made_shot=False, primary_player='Nikola Jokic', is_three_pointer_made=False, is_rebound=True, is_assist=False, is_steal=False, is_block=False, assist_player=None, steal_player=None, block_player=None),
    ])
    graded = settle_leg(_base_leg('player_first_rebound', 'Jokic first rebound'), _BoxScoreProvider(), play_by_play_provider=pbp)
    assert graded.settlement == 'win'


def test_first_assist_settles_from_play_by_play_events() -> None:
    pbp = _PlayByPlayProvider([
        _Evt(is_made_shot=True, primary_player='Jamal Murray', is_three_pointer_made=False, is_rebound=False, is_assist=True, is_steal=False, is_block=False, assist_player='Nikola Jokic', steal_player=None, block_player=None),
    ])
    graded = settle_leg(_base_leg('player_first_assist', 'Jokic first assist'), _BoxScoreProvider(), play_by_play_provider=pbp)
    assert graded.settlement == 'win'


def test_first_three_settles_from_play_by_play_events() -> None:
    pbp = _PlayByPlayProvider([
        _Evt(is_made_shot=True, primary_player='Nikola Jokic', is_three_pointer_made=True, is_rebound=False, is_assist=False, is_steal=False, is_block=False, assist_player=None, steal_player=None, block_player=None),
    ])
    graded = settle_leg(_base_leg('player_first_three', 'Jokic first 3 pointer'), _BoxScoreProvider(), play_by_play_provider=pbp)
    assert graded.settlement == 'win'


def test_last_basket_settles_from_play_by_play_events() -> None:
    pbp = _PlayByPlayProvider([
        _Evt(is_made_shot=True, primary_player='Jamal Murray', is_three_pointer_made=False, is_rebound=False, is_assist=False, is_steal=False, is_block=False, assist_player=None, steal_player=None, block_player=None),
        _Evt(is_made_shot=True, primary_player='Nikola Jokic', is_three_pointer_made=False, is_rebound=False, is_assist=False, is_steal=False, is_block=False, assist_player=None, steal_player=None, block_player=None),
    ])
    graded = settle_leg(_base_leg('player_last_basket', 'Jokic last basket'), _BoxScoreProvider(), play_by_play_provider=pbp)
    assert graded.settlement == 'win'


def test_missing_play_by_play_payload_returns_unmatched() -> None:
    graded = settle_leg(_base_leg('player_first_basket', 'Jokic first basket'), _BoxScoreProvider(), play_by_play_provider=_PlayByPlayProvider(None))
    assert graded.settlement == 'unmatched'


def test_registry_declares_data_sources() -> None:
    assert MARKET_REGISTRY['points']['required_data_source'] == 'box_score'
    assert MARKET_REGISTRY['first_basket']['required_data_source'] == 'play_by_play'

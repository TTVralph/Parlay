from datetime import date, datetime

from app.identity_resolution import get_sport_adapters, resolve_player_identity
from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events


class DirectoryPipelineProvider:
    def __init__(self) -> None:
        self.event = EventInfo(
            event_id='nba-evt-mem-lac',
            sport='NBA',
            home_team='Memphis Grizzlies',
            away_team='LA Clippers',
            start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
        )

    def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
        if team == 'Memphis Grizzlies':
            return [self.event]
        return []

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [
            self.event,
            EventInfo(
                event_id='noise-event',
                sport='NBA',
                home_team='Milwaukee Bucks',
                away_team='Utah Jazz',
                start_time=datetime.fromisoformat('2026-03-08T01:00:00+00:00'),
            ),
        ]

    def get_team_result(self, team: str, event_id: str | None = None):
        return None

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
        return None


def test_cross_sport_adapter_registry_exists() -> None:
    adapters = get_sport_adapters()
    assert {'NBA', 'NFL', 'MLB'}.issubset(adapters.keys())


def test_initials_and_punctuation_alias_resolve() -> None:
    og = resolve_player_identity('O.G. Anunoby', sport='NBA')
    assert og.resolved_player_name == 'OG Anunoby'




def test_initials_player_variant_resolves() -> None:
    aj = resolve_player_identity('A.J. Green', sport='NBA')
    assert aj.resolved_player_name == 'AJ Green'
    assert aj.resolved_team == 'Milwaukee Bucks'


def test_nba_directory_contains_expected_active_players() -> None:
    adapter = get_sport_adapters()['NBA']
    names = {p.full_name for p in adapter.load_players()}
    assert 'AJ Green' in names
    assert 'Jaren Jackson Jr.' in names

def test_unambiguous_nba_player_resolution() -> None:
    jokic = resolve_player_identity('Nikola Jokic', sport='NBA')
    assert jokic.resolved_player_id == 'nba-nikola-jokic'
    assert jokic.resolved_team == 'Denver Nuggets'
    assert jokic.confidence == 1.0


def test_team_resolution_comes_from_player_identity() -> None:
    provider = DirectoryPipelineProvider()
    leg = Leg(
        raw_text='Scotty Pippen Jr. over 5.5 assists',
        sport='NBA',
        market_type='player_assists',
        player='Scotty Pippen Jr.',
        direction='over',
        line=5.5,
        confidence=0.9,
    )
    resolved = resolve_leg_events([leg], provider, posted_at=date.fromisoformat('2026-03-07'), include_historical=True)
    assert resolved[0].resolved_team == 'Memphis Grizzlies'
    assert resolved[0].event_id == 'nba-evt-mem-lac'


def test_unknown_player_surfaces_directory_reason() -> None:
    leg = Leg(
        raw_text='Random Guy over 4.5 assists',
        sport='NBA',
        market_type='player_assists',
        player='Random Guy',
        direction='over',
        line=4.5,
        confidence=0.9,
    )
    provider = DirectoryPipelineProvider()
    resolved = resolve_leg_events([leg], provider, posted_at=date.fromisoformat('2026-03-07'), include_historical=True)
    assert 'player not found in sport directory' in resolved[0].notes

from datetime import datetime

from fastapi.testclient import TestClient

from app.grader import grade_text
from app.main import app
from app.parser import parse_text

client = TestClient(app)


def test_parser_handles_spread_and_total():
    legs = parse_text('Chiefs -3.5\nOver 48.5', sport_hint='NFL')
    assert legs[0].market_type == 'spread'
    assert legs[0].team == 'Kansas City Chiefs'
    assert legs[0].line == -3.5
    assert legs[1].market_type == 'game_total'
    assert legs[1].direction == 'over'
    assert legs[1].line == 48.5


def test_grader_settles_spread_and_total_across_sports():
    nfl = grade_text('Chiefs -3.5\nOver 48.5', posted_at=datetime.fromisoformat('2026-03-07T14:00:00'))
    assert nfl.overall == 'cashed'
    assert [leg.settlement for leg in nfl.legs] == ['win', 'win']

    mlb = grade_text('Yankees -1.5\nOver 8.5', posted_at=datetime.fromisoformat('2026-03-07T12:00:00'))
    assert mlb.overall == 'cashed'
    assert [leg.settlement for leg in mlb.legs] == ['win', 'win']



def test_odds_match_endpoint_matches_bookmaker_snapshot():
    resp = client.post('/odds/match', json={'text': 'Denver ML\nJokic over 24.5 points', 'bookmaker': 'draftkings', 'posted_at': '2026-03-07T18:00:00'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['matched_count'] == 2
    assert all(item['matched'] for item in data['matched_legs'])



def test_public_capper_profile_endpoint():
    save_resp = client.post(
        '/ingest/tweet/grade-and-save',
        json={
            'tweet_id': '111',
            'username': 'endgamepicks',
            'text': 'Chiefs -3.5\nOver 48.5\nStake 20\nOdds +210',
            'posted_at': '2026-03-07T14:00:00',
        },
    )
    assert save_resp.status_code == 200

    resp = client.get('/public/cappers/endgamepicks')
    assert resp.status_code == 200
    data = resp.json()
    assert data['username'] == 'endgamepicks'
    assert data['summary']['total_tickets'] >= 1
    assert len(data['recent_tickets']) >= 1

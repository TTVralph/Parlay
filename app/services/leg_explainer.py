from __future__ import annotations

from app.models import GradeResponse, GradedLeg, Leg, SoldLegExplanation
from app.services.event_snapshot import EventSnapshot
from app.services.kill_moment_explainer import explain_kill_moment
from app.services.play_by_play_provider import PlayByPlayEvent

_SUPPORTED_MARKETS = {
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_threes',
    'player_pr',
    'player_pa',
    'player_ra',
    'player_pra',
    'moneyline',
    'spread',
    'game_total',
}

_PLAYER_MARKET_TO_STAT_KEY = {
    'player_points': 'PTS',
    'player_rebounds': 'REB',
    'player_assists': 'AST',
    'player_threes': '3PM',
}

_COMBO_COMPONENTS = {
    'player_pr': ('PTS', 'REB'),
    'player_pa': ('PTS', 'AST'),
    'player_ra': ('REB', 'AST'),
    'player_pra': ('PTS', 'REB', 'AST'),
}


def _fmt_num(value: float | None) -> str:
    if value is None:
        return 'unknown'
    return f'{value:g}'


def _player_label(leg: Leg) -> str:
    return leg.resolved_player_name or leg.player or 'Player'


def _team_label(leg: Leg, snapshot: EventSnapshot | None) -> str:
    if leg.team:
        return leg.team
    if snapshot is None:
        return 'Team'
    return str((snapshot.home_team or {}).get('name') or (snapshot.away_team or {}).get('name') or 'Team')


def _stat_from_snapshot(snapshot: EventSnapshot, player_name: str, stat_key: str) -> float | None:
    stat_aliases = {
        'PTS': {'PTS', 'points'},
        'REB': {'REB', 'rebounds'},
        'AST': {'AST', 'assists'},
        '3PM': {'3PM', '3PTM', 'threes', 'threes made'},
    }
    for entry in snapshot.normalized_player_stats.values():
        display_name = str(entry.get('display_name') or '').strip()
        if display_name.lower() != player_name.lower():
            continue
        stats = entry.get('stats') or {}
        for alias in stat_aliases.get(stat_key, {stat_key}):
            value = stats.get(alias)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def get_last_relevant_play_context(leg: Leg, snapshot: EventSnapshot | None) -> str | None:
    if snapshot is None or not snapshot.normalized_play_by_play:
        return None
    player = _player_label(leg)
    events = snapshot.normalized_play_by_play

    def _is_relevant(event: PlayByPlayEvent) -> bool:
        if leg.market_type == 'player_assists':
            return event.is_assist and str(event.assist_player or '').lower() == player.lower()
        if leg.market_type == 'player_rebounds':
            return event.is_rebound and str(event.primary_player or '').lower() == player.lower()
        if leg.market_type == 'player_points':
            return event.is_made_shot and str(event.primary_player or '').lower() == player.lower()
        if leg.market_type == 'player_threes':
            return event.is_three_pointer_made and str(event.primary_player or '').lower() == player.lower()
        if leg.market_type in _COMBO_COMPONENTS:
            return (
                (event.is_made_shot and str(event.primary_player or '').lower() == player.lower())
                or (event.is_rebound and str(event.primary_player or '').lower() == player.lower())
                or (event.is_assist and str(event.assist_player or '').lower() == player.lower())
            )
        return False

    for event in reversed(events):
        if _is_relevant(event):
            period = f'Q{event.period}' if event.period else 'game'
            clock = event.clock or 'unknown clock'
            return f"Last relevant play: {event.description} ({clock} in {period})."
    return None


def explain_leg_result(leg: GradedLeg, snapshot: EventSnapshot | None, settlement_result: str | None = None) -> SoldLegExplanation | None:
    if leg.leg.market_type not in _SUPPORTED_MARKETS:
        return None

    outcome = settlement_result or leg.settlement
    if outcome != 'loss':
        return None

    final_value = leg.actual_value
    miss_by: float | None = None
    target_line = leg.line if leg.line is not None else leg.leg.line
    play_context = get_last_relevant_play_context(leg.leg, snapshot)
    kill_moment = explain_kill_moment(leg, snapshot, settlement_result)
    source = 'snapshot_plus_pbp' if play_context else 'snapshot_only'
    if kill_moment is not None:
        source = kill_moment.explanation_source  # type: ignore[assignment]

    if target_line is not None and final_value is not None:
        if leg.leg.direction == 'over':
            miss_by = round(target_line - final_value, 2)
        elif leg.leg.direction == 'under':
            miss_by = round(final_value - target_line, 2)

    player_or_team = _player_label(leg.leg) if leg.leg.player else _team_label(leg.leg, snapshot)

    if leg.leg.market_type in _PLAYER_MARKET_TO_STAT_KEY:
        stat_label = leg.normalized_market or leg.leg.market_type
        short_reason = f"{player_or_team} {leg.leg.direction} {_fmt_num(target_line)} lost"
        detailed = (
            f"{player_or_team} {leg.leg.direction} {_fmt_num(target_line)} {stat_label} lost. "
            f"Finished with {_fmt_num(final_value)}, missing by {_fmt_num(miss_by)}."
        )
    elif leg.leg.market_type in _COMBO_COMPONENTS:
        components: list[str] = []
        for key in _COMBO_COMPONENTS[leg.leg.market_type]:
            value = None
            if isinstance(leg.component_values, dict):
                value = leg.component_values.get(key)
            if value is None and snapshot is not None:
                value = _stat_from_snapshot(snapshot, _player_label(leg.leg), key)
            if value is not None:
                components.append(f"{_fmt_num(float(value))} {key}")
        comp_text = f" ({', '.join(components)})" if components else ''
        short_reason = f"{player_or_team} combo line missed by {_fmt_num(miss_by)}"
        detailed = (
            f"{player_or_team} {leg.leg.market_type.replace('player_', '').upper()} finished at {_fmt_num(final_value)}{comp_text}, "
            f"missing {_fmt_num(target_line)} by {_fmt_num(miss_by)}."
        )
    elif leg.leg.market_type == 'moneyline':
        home = str((snapshot.home_team or {}).get('name') or 'Home') if snapshot else 'Home'
        away = str((snapshot.away_team or {}).get('name') or 'Away') if snapshot else 'Away'
        home_score = (snapshot.normalized_event_result or {}).get('home_score') if snapshot else None
        away_score = (snapshot.normalized_event_result or {}).get('away_score') if snapshot else None
        score_text = f"{away} {_fmt_num(float(away_score) if away_score is not None else None)} - {home} {_fmt_num(float(home_score) if home_score is not None else None)}"
        short_reason = f"{player_or_team} moneyline lost"
        detailed = f"{player_or_team} moneyline lost. Final score: {score_text}."
    elif leg.leg.market_type == 'spread':
        short_reason = f"{player_or_team} spread lost"
        detailed = (
            f"{player_or_team} spread {_fmt_num(target_line)} lost. Final margin was {_fmt_num(final_value)}, "
            f"missing cover by {_fmt_num(miss_by)}."
        )
    else:
        short_reason = f"Game total {leg.leg.direction} {_fmt_num(target_line)} lost"
        detailed = (
            f"Game total {leg.leg.direction} {_fmt_num(target_line)} lost. Final total was {_fmt_num(final_value)}, "
            f"missing by {_fmt_num(miss_by)}."
        )

    if kill_moment is not None and kill_moment.kill_moment_summary:
        detailed = f"{detailed} {kill_moment.kill_moment_summary}"
    elif play_context:
        detailed = f"{detailed} {play_context}"

    return SoldLegExplanation(
        is_sold_leg=True,
        market_type=leg.leg.market_type,
        player_or_team=player_or_team,
        target_line=target_line,
        final_value=final_value,
        miss_by=miss_by,
        outcome=outcome,
        short_reason=short_reason,
        detailed_reason=detailed,
        event_id=leg.leg.event_id,
        play_by_play_supported=bool(snapshot and snapshot.normalized_play_by_play),
        last_relevant_context=kill_moment.last_relevant_play_text if kill_moment is not None else play_context,
        kill_moment_supported=kill_moment.kill_moment_supported if kill_moment is not None else False,
        kill_moment_summary=kill_moment.kill_moment_summary if kill_moment is not None else None,
        last_relevant_play_text=kill_moment.last_relevant_play_text if kill_moment is not None else None,
        last_relevant_period=kill_moment.last_relevant_period if kill_moment is not None else None,
        last_relevant_clock=kill_moment.last_relevant_clock if kill_moment is not None else None,
        explanation_source=source,  # type: ignore[arg-type]
    )


def explain_sold_legs(
    grading_result: GradeResponse,
    snapshots_by_event_id: dict[str, EventSnapshot] | None = None,
) -> list[SoldLegExplanation]:
    explanations: list[SoldLegExplanation] = []
    snapshot_map = snapshots_by_event_id or {}
    for graded_leg in grading_result.legs:
        try:
            explanation = explain_leg_result(
                graded_leg,
                snapshot_map.get(graded_leg.leg.event_id or ''),
                graded_leg.settlement,
            )
        except Exception:
            explanation = None
        if explanation is None:
            continue
        explanations.append(explanation)
    return explanations

from __future__ import annotations

from dataclasses import dataclass, replace
from app.models import GradedLeg, Leg
from app.services.espn_plays_provider import ESPNPlaysProvider
from app.services.event_snapshot import EventSnapshot
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


@dataclass
class KillMomentExplanation:
    kill_moment_supported: bool
    explanation_source: str
    kill_moment_summary: str
    last_relevant_play_text: str | None = None
    last_relevant_period: str | None = None
    last_relevant_clock: str | None = None


_STAT_ALIASES = {
    'PTS': {'PTS', 'points'},
    'REB': {'REB', 'rebounds'},
    'AST': {'AST', 'assists'},
    '3PM': {'3PM', '3PTM', 'threes', 'threes made'},
}

_DEFAULT_PLAYS_PROVIDER = ESPNPlaysProvider()


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


def _period_label(event: PlayByPlayEvent) -> str | None:
    if event.period is None:
        return None
    return f'Q{event.period}'


def _stat_from_snapshot(snapshot: EventSnapshot, player_name: str, stat_key: str) -> float | None:
    for entry in snapshot.normalized_player_stats.values():
        display_name = str(entry.get('display_name') or '').strip()
        if display_name.lower() != player_name.lower():
            continue
        stats = entry.get('stats') or {}
        for alias in _STAT_ALIASES.get(stat_key, {stat_key}):
            value = stats.get(alias)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def get_last_relevant_stat_play(
    *,
    leg: Leg,
    snapshot: EventSnapshot | None,
    stat_keys: tuple[str, ...],
) -> tuple[PlayByPlayEvent | None, str | None]:
    if snapshot is None or not snapshot.normalized_play_by_play:
        return None, None
    player = _player_label(leg).lower()

    for event in reversed(snapshot.normalized_play_by_play):
        if 'PTS' in stat_keys and event.is_made_shot and str(event.primary_player or '').lower() == player:
            return event, 'PTS'
        if '3PM' in stat_keys and event.is_three_pointer_made and str(event.primary_player or '').lower() == player:
            return event, '3PM'
        if 'REB' in stat_keys and event.is_rebound and str(event.primary_player or '').lower() == player:
            return event, 'REB'
        if 'AST' in stat_keys and event.is_assist and str(event.assist_player or '').lower() == player:
            return event, 'AST'
    return None, None


def get_last_relevant_team_swing_play(
    *,
    leg: Leg,
    snapshot: EventSnapshot | None,
) -> PlayByPlayEvent | None:
    if snapshot is None or not snapshot.normalized_play_by_play:
        return None

    team_name = str(leg.team or '').strip().lower()
    scoring_events = [event for event in snapshot.normalized_play_by_play if event.is_scoring_play]
    if not scoring_events:
        return None

    if leg.market_type == 'moneyline' and team_name:
        for event in reversed(scoring_events):
            if str(event.team or '').strip().lower() != team_name:
                return event
        return scoring_events[-1]

    return scoring_events[-1]


def _build_player_summary(*, leg: Leg, final_value: float | None, stat_label: str, last_event: PlayByPlayEvent | None) -> str:
    player = _player_label(leg)
    if last_event is not None:
        clock = last_event.clock or 'unknown clock'
        period = _period_label(last_event) or 'game'
        if stat_label == 'REB':
            return f"{player}'s final rebound came with {clock} left in {period}. He finished with {_fmt_num(final_value)} rebounds."
        if stat_label == 'AST':
            return f"{player}'s final assist came with {clock} left in {period}. He finished with {_fmt_num(final_value)} assists."
        if stat_label == '3PM':
            return f"{player}'s final made three came with {clock} left in {period}. He finished with {_fmt_num(final_value)} threes."
        return f"{player}'s last PTS play came with {clock} left in {period}. He finished with {_fmt_num(final_value)} PTS and did not add more."

    if stat_label == 'AST' and (final_value or 0.0) <= 0:
        return f"{player}'s last recorded assist opportunity never materialized; he finished with 0 assists."
    return f'{player} finished with {_fmt_num(final_value)} {stat_label}. No play-by-play kill moment was available.'


def _build_combo_summary(
    *,
    leg: Leg,
    final_value: float | None,
    component_values: dict[str, float | None],
    component_changed: str | None,
    last_event: PlayByPlayEvent | None,
) -> str:
    player = _player_label(leg)
    comp_order = _COMBO_COMPONENTS.get(leg.market_type, ())
    comp_text = ', '.join(f"{_fmt_num(component_values.get(key))} {key}" for key in comp_order)
    base = f'{player} finished at {_fmt_num(final_value)} {leg.market_type.replace("player_", "").upper()} ({comp_text}).'
    if last_event is None or component_changed is None:
        return f'{base} No play-by-play kill moment was available.'
    clock = last_event.clock or 'unknown clock'
    period = _period_label(last_event) or 'game'
    return f'{base} The last {component_changed} play that changed the total came with {clock} left in {period}.'


def _build_team_summary(*, leg: Leg, snapshot: EventSnapshot | None, last_event: PlayByPlayEvent | None) -> str:
    final_result = snapshot.normalized_event_result if snapshot else {}
    team = _team_label(leg, snapshot)
    home = str((snapshot.home_team or {}).get('name') or 'Home') if snapshot else 'Home'
    away = str((snapshot.away_team or {}).get('name') or 'Away') if snapshot else 'Away'
    home_score = final_result.get('home_score')
    away_score = final_result.get('away_score')
    margin = final_result.get('margin')
    combined_total = final_result.get('combined_total')

    if leg.market_type == 'moneyline':
        if last_event is not None:
            clock = last_event.clock or 'unknown clock'
            period = _period_label(last_event) or 'game'
            return f"The decisive scoring swing against {team} came with {clock} left in {period}: {last_event.description}. Final score was {away} {_fmt_num(float(away_score) if away_score is not None else None)} - {home} {_fmt_num(float(home_score) if home_score is not None else None)}."
        return f"{team} lost the moneyline. Final score was {away} {_fmt_num(float(away_score) if away_score is not None else None)} - {home} {_fmt_num(float(home_score) if home_score is not None else None)}."

    if leg.market_type == 'spread':
        line = leg.line
        if last_event is not None:
            clock = last_event.clock or 'unknown clock'
            period = _period_label(last_event) or 'game'
            return f"{team} failed to cover {_fmt_num(line)} after the late scoring swing with {clock} left in {period}: {last_event.description}. Final margin was {_fmt_num(float(margin) if margin is not None else None)}."
        return f"{team} failed to cover {_fmt_num(line)}. Final margin was {_fmt_num(float(margin) if margin is not None else None)}."

    if last_event is not None:
        clock = last_event.clock or 'unknown clock'
        period = _period_label(last_event) or 'game'
        return f"The final scoring swing that put the total out of reach came with {clock} left in {period}: {last_event.description}. Final total was {_fmt_num(float(combined_total) if combined_total is not None else None)}."
    return f"The game total finished at {_fmt_num(float(combined_total) if combined_total is not None else None)}."


def _with_effective_play_by_play(
    *,
    leg: Leg,
    snapshot: EventSnapshot | None,
    plays_provider: ESPNPlaysProvider,
) -> tuple[EventSnapshot | None, str | None]:
    if snapshot is not None and snapshot.normalized_play_by_play:
        return snapshot, 'snapshot_plus_pbp'

    event_id = str(leg.event_id or '').strip()
    if not event_id:
        return snapshot, None

    feed = plays_provider.get_best_play_feed(event_id)
    if feed is None or not feed.plays:
        return snapshot, None

    if snapshot is None:
        return EventSnapshot(event_id=event_id, normalized_play_by_play=feed.plays), feed.source
    return replace(snapshot, normalized_play_by_play=feed.plays), feed.source


def explain_kill_moment(
    leg: GradedLeg,
    snapshot: EventSnapshot | None,
    settlement_result: str | None,
    plays_provider: ESPNPlaysProvider | None = None,
) -> KillMomentExplanation | None:
    if leg.leg.market_type not in _SUPPORTED_MARKETS:
        return None
    outcome = settlement_result or leg.settlement
    if outcome != 'loss' or outcome in {'live', 'review'}:
        return None

    market_type = leg.leg.market_type
    provider = plays_provider or _DEFAULT_PLAYS_PROVIDER
    effective_snapshot, source = _with_effective_play_by_play(leg=leg.leg, snapshot=snapshot, plays_provider=provider)

    if market_type in _PLAYER_MARKET_TO_STAT_KEY:
        stat_key = _PLAYER_MARKET_TO_STAT_KEY[market_type]
        final_value = leg.actual_value
        if final_value is None and snapshot is not None:
            final_value = _stat_from_snapshot(snapshot, _player_label(leg.leg), stat_key)
        last_event, _ = get_last_relevant_stat_play(leg=leg.leg, snapshot=effective_snapshot, stat_keys=(stat_key,))
        return KillMomentExplanation(
            kill_moment_supported=True,
            explanation_source=source if last_event is not None and source is not None else 'snapshot_only',
            kill_moment_summary=_build_player_summary(leg=leg.leg, final_value=final_value, stat_label=stat_key, last_event=last_event),
            last_relevant_play_text=last_event.description if last_event is not None else None,
            last_relevant_period=_period_label(last_event) if last_event is not None else None,
            last_relevant_clock=last_event.clock if last_event is not None else None,
        )

    if market_type in _COMBO_COMPONENTS:
        component_values: dict[str, float | None] = {}
        for key in _COMBO_COMPONENTS[market_type]:
            value = None
            if isinstance(leg.component_values, dict):
                raw_value = leg.component_values.get(key)
                if raw_value is not None:
                    value = float(raw_value)
            if value is None and snapshot is not None:
                value = _stat_from_snapshot(snapshot, _player_label(leg.leg), key)
            component_values[key] = value

        last_event, component_changed = get_last_relevant_stat_play(
            leg=leg.leg,
            snapshot=effective_snapshot,
            stat_keys=_COMBO_COMPONENTS[market_type],
        )
        return KillMomentExplanation(
            kill_moment_supported=True,
            explanation_source=source if last_event is not None and source is not None else 'snapshot_only',
            kill_moment_summary=_build_combo_summary(
                leg=leg.leg,
                final_value=leg.actual_value,
                component_values=component_values,
                component_changed=component_changed,
                last_event=last_event,
            ),
            last_relevant_play_text=last_event.description if last_event is not None else None,
            last_relevant_period=_period_label(last_event) if last_event is not None else None,
            last_relevant_clock=last_event.clock if last_event is not None else None,
        )

    last_team_event = get_last_relevant_team_swing_play(leg=leg.leg, snapshot=effective_snapshot)
    return KillMomentExplanation(
        kill_moment_supported=True,
        explanation_source=source if last_team_event is not None and source is not None else 'snapshot_only',
        kill_moment_summary=_build_team_summary(leg=leg.leg, snapshot=snapshot, last_event=last_team_event),
        last_relevant_play_text=last_team_event.description if last_team_event is not None else None,
        last_relevant_period=_period_label(last_team_event) if last_team_event is not None else None,
        last_relevant_clock=last_team_event.clock if last_team_event is not None else None,
    )

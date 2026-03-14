from app.rules.base import StatRule
from app.rules.helpers import get_player_stat


def _total_bases(snapshot, player_id, player_name):
    explicit = get_player_stat(snapshot, player_id, 'TB', player_name=player_name)
    if explicit is not None:
        return explicit
    singles = get_player_stat(snapshot, player_id, '1B', player_name=player_name)
    doubles = get_player_stat(snapshot, player_id, '2B', player_name=player_name)
    triples = get_player_stat(snapshot, player_id, '3B', player_name=player_name)
    home_runs = get_player_stat(snapshot, player_id, 'HR', player_name=player_name)
    if None in {singles, doubles, triples, home_runs}:
        return None
    return float(singles + (2 * doubles) + (3 * triples) + (4 * home_runs))


MLB_RULES = {
    'player_hits': StatRule('MLB', 'player_hits', ('H',), lambda s, pid, pname: get_player_stat(s, pid, 'H', player_name=pname), display_name='Hits', supports_kill_moment=True),
    'player_strikeouts': StatRule('MLB', 'player_strikeouts', ('SO',), lambda s, pid, pname: get_player_stat(s, pid, 'SO', player_name=pname), display_name='Strikeouts', supports_kill_moment=True),
    'player_total_bases': StatRule('MLB', 'player_total_bases', ('TB', '1B', '2B', '3B', 'HR'), _total_bases, display_name='Total Bases', supports_kill_moment=True),
    'player_runs': StatRule('MLB', 'player_runs', ('R',), lambda s, pid, pname: get_player_stat(s, pid, 'R', player_name=pname), display_name='Runs', supports_kill_moment=True),
    'player_rbis': StatRule('MLB', 'player_rbis', ('RBI',), lambda s, pid, pname: get_player_stat(s, pid, 'RBI', player_name=pname), display_name='RBIs', supports_kill_moment=True),
    'player_home_runs': StatRule('MLB', 'player_home_runs', ('HR',), lambda s, pid, pname: get_player_stat(s, pid, 'HR', player_name=pname), display_name='Home Runs', supports_kill_moment=True),
}

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

ALLOWED_LEG_RESULTS = {'win', 'loss', 'push', 'void', 'live', 'review', 'pending', 'unmatched'}
PARLAY_RESULT_ALLOWED = {'cashed', 'lost', 'still_live', 'needs_review'}


@dataclass(frozen=True)
class Player:
    name: str
    team: str


@dataclass(frozen=True)
class Market:
    key: str
    full: str
    short: str
    threshold_range: tuple[float, float]
    supports_alt_plus: bool = True


@dataclass
class GeneratedLeg:
    player: Player
    market: Market
    selection: str
    threshold: float
    text: str


@dataclass
class FuzzCase:
    case_id: str
    mode: str
    text: str
    bet_date: str
    expected_legs: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FuzzIssue:
    seed: int
    case_id: str
    mode: str
    input_text: str
    bet_date: str
    issue_type: str
    details: dict[str, Any]
    response_snapshot: dict[str, Any] | None


@dataclass
class FuzzOutcome:
    case: FuzzCase
    status_code: int
    response: dict[str, Any] | None
    hard_failure: bool = False
    issues: list[FuzzIssue] = field(default_factory=list)


class PlayerPool:
    def __init__(self) -> None:
        self.players = [
            Player('LeBron James', 'LAL'),
            Player('Nikola Jokic', 'DEN'),
            Player('Jayson Tatum', 'BOS'),
            Player('Josh Giddey', 'CHI'),
            Player('Christian Braun', 'DEN'),
            Player('Wendell Carter Jr.', 'ORL'),
            Player('Jalen Williams', 'OKC'),
            Player('Jaylin Williams', 'OKC'),
            Player('Kevin Porter Jr.', 'LAC'),
            Player('Dyson Daniels', 'ATL'),
            Player('Onyeka Okongwu', 'ATL'),
            Player('Stephen Curry', 'GSW'),
            Player('Anthony Davis', 'LAL'),
            Player('Trae Young', 'ATL'),
            Player('Jaylen Brown', 'BOS'),
        ]

    def pick(self, rng: random.Random) -> Player:
        return rng.choice(self.players)


class MarketGenerator:
    def __init__(self) -> None:
        self.markets = [
            Market('player_points', 'Points', 'PTS', (0.5, 40.5)),
            Market('player_rebounds', 'Rebounds', 'REB', (0.5, 18.5)),
            Market('player_assists', 'Assists', 'AST', (0.5, 14.5)),
            Market('player_pra', 'PRA', 'PRA', (8.5, 58.5)),
            Market('player_pa', 'PA', 'PA', (5.5, 50.5)),
            Market('player_pr', 'PR', 'PR', (5.5, 48.5)),
            Market('player_ra', 'RA', 'RA', (4.5, 35.5)),
            Market('player_threes', '3PM', '3PM', (0.5, 7.5)),
        ]

    def pick(self, rng: random.Random) -> Market:
        return rng.choice(self.markets)

    def threshold(self, rng: random.Random, market: Market) -> float:
        if rng.random() < 0.2:
            return rng.choice([0.5, 1.5, 20.5])
        lo, hi = market.threshold_range
        raw = rng.uniform(lo, hi)
        if rng.random() < 0.35:
            return round(raw)
        return round(raw * 2) / 2


class FormattingMutator:
    _headers = ['SGP', 'Same Game Parlay', 'Draft Slip', 'NBA Props']

    def build_leg_text(self, rng: random.Random, leg: GeneratedLeg, mode: str) -> str:
        player_name = leg.player.name
        if mode == 'ambiguity' and rng.random() < 0.45:
            player_name = self._ambiguous_name(rng, leg.player.name)

        over_token = rng.choice(['Over', 'over', 'O', 'o'])
        threshold_token = self._threshold_token(rng, leg.threshold, leg.market)

        templates = [
            '{player} {sel} {line} {market}',
            '{player} {sel}{line} {short}',
            '{player} {line}+ {market}',
            '{player} {sel} {line} {short} (+120)',
            '{player} - {sel} {line} {market}',
        ]
        template = rng.choice(templates)
        line = template.format(
            player=player_name,
            sel=over_token,
            line=threshold_token,
            market=leg.market.full,
            short=leg.market.short,
        )

        if rng.random() < 0.15:
            line = line.upper()
        if rng.random() < 0.2:
            line = re.sub(r'\s+', '  ', line)
        return line.strip()

    def add_slip_noise(self, rng: random.Random, lines: list[str], ugliness: float) -> str:
        out = list(lines)
        if rng.random() < ugliness:
            out.insert(0, rng.choice(self._headers))
        if rng.random() < ugliness:
            out.append(rng.choice(['Odds +120', 'Boost token', 'Placed: 2026-03-12']))
        if rng.random() < ugliness:
            out.insert(rng.randrange(0, len(out) + 1), '')
        joined = '\n'.join(out)
        if rng.random() < ugliness:
            joined = '\n' + joined + '\n'
        if rng.random() < ugliness / 2:
            joined = joined.replace(' ', '\t', 1)
        return joined

    def _threshold_token(self, rng: random.Random, threshold: float, market: Market) -> str:
        if market.supports_alt_plus and rng.random() < 0.25:
            return f'{int(threshold)}+'
        if float(threshold).is_integer():
            return str(int(threshold))
        return f'{threshold:.1f}'

    def _ambiguous_name(self, rng: random.Random, full_name: str) -> str:
        tokens = full_name.replace('.', '').split()
        if not tokens:
            return full_name
        if len(tokens) >= 2:
            first = tokens[0]
            last = tokens[-1]
            return rng.choice([f'{first[0]} {last}', f'{first[0]}. {last}', last, f'{last} Jr'])
        return tokens[0]


class SlipAssembler:
    def __init__(self) -> None:
        self.players = PlayerPool()
        self.markets = MarketGenerator()
        self.mutator = FormattingMutator()

    def make_case(self, rng: random.Random, case_id: str, mode: str, min_legs: int, max_legs: int) -> FuzzCase:
        leg_count = self._choose_leg_count(rng, min_legs=min_legs, max_legs=max_legs)
        legs: list[GeneratedLeg] = []
        for _ in range(leg_count):
            player = self.players.pick(rng)
            market = self.markets.pick(rng)
            threshold = self.markets.threshold(rng, market)
            leg = GeneratedLeg(player=player, market=market, selection='over', threshold=threshold, text='')
            leg.text = self.mutator.build_leg_text(rng, leg, mode=mode)
            legs.append(leg)

        noise_profile = self._noise_profile(rng, mode)
        body = self.mutator.add_slip_noise(rng, [leg.text for leg in legs], ugliness=noise_profile)

        bet_date = (date(2026, 3, 15) - timedelta(days=rng.randint(0, 7))).isoformat()
        return FuzzCase(
            case_id=case_id,
            mode=mode,
            text=body,
            bet_date=bet_date,
            expected_legs=leg_count,
            metadata={
                'noise_profile': noise_profile,
                'leg_markets': [leg.market.key for leg in legs],
                'players': [leg.player.name for leg in legs],
            },
        )

    def _noise_profile(self, rng: random.Random, mode: str) -> float:
        if mode == 'parser':
            return rng.choice([0.25, 0.35, 0.5, 0.7])
        if mode == 'ambiguity':
            return rng.choice([0.15, 0.25, 0.35])
        if mode == 'settlement':
            return rng.choice([0.02, 0.1, 0.15])
        weighted = rng.random()
        if weighted < 0.6:
            return 0.08
        if weighted < 0.85:
            return 0.25
        if weighted < 0.95:
            return 0.4
        return 0.75

    def _choose_leg_count(self, rng: random.Random, min_legs: int, max_legs: int) -> int:
        options = [1, 2, 3, 5, 8, 10, 12]
        options = [count for count in options if min_legs <= count <= max_legs] or [min_legs]
        return rng.choice(options)


class InvariantChecker:
    def evaluate(self, *, seed: int, case: FuzzCase, status_code: int, response: dict[str, Any] | None) -> list[FuzzIssue]:
        issues: list[FuzzIssue] = []
        if status_code != 200:
            issues.append(self._issue(seed, case, 'http_status', {'status_code': status_code}, response))
            return issues

        if not isinstance(response, dict):
            return [self._issue(seed, case, 'malformed_response', {'reason': 'response not dict'}, response)]

        legs = response.get('legs')
        if not isinstance(legs, list):
            issues.append(self._issue(seed, case, 'missing_legs', {'legs_type': type(legs).__name__}, response))
            return issues

        if response.get('parlay_result') not in PARLAY_RESULT_ALLOWED:
            issues.append(self._issue(seed, case, 'invalid_parlay_result', {'value': response.get('parlay_result')}, response))

        if legs and len(legs) < max(1, min(case.expected_legs, 2)):
            issues.append(self._issue(seed, case, 'too_few_legs_parsed', {'expected_at_least': min(case.expected_legs, 2), 'actual': len(legs)}, response))

        normalized = []
        for idx, leg in enumerate(legs):
            if not isinstance(leg, dict):
                issues.append(self._issue(seed, case, 'leg_not_object', {'index': idx}, response))
                continue
            result = str(leg.get('result', '')).lower()
            normalized.append(result)
            if result not in ALLOWED_LEG_RESULTS:
                issues.append(self._issue(seed, case, 'invalid_leg_result', {'index': idx, 'value': result}, response))
            actual = leg.get('actual_value')
            if isinstance(actual, (float, int)) and actual < 0:
                issues.append(self._issue(seed, case, 'negative_actual_value', {'index': idx, 'actual_value': actual}, response))
            if result in {'win', 'loss'} and (leg.get('line') is None or not leg.get('normalized_market')):
                issues.append(self._issue(seed, case, 'missing_core_fields_on_resolved_leg', {'index': idx}, response))
            if result in {'win', 'loss'} and not leg.get('matched_event'):
                issues.append(self._issue(seed, case, 'missing_matched_event', {'index': idx}, response))

        if 'loss' in normalized and response.get('parlay_result') == 'cashed':
            issues.append(self._issue(seed, case, 'parlay_contradiction_loss_but_cashed', {}, response))
        non_void = [item for item in normalized if item not in {'void'}]
        if non_void and all(item == 'win' for item in non_void) and response.get('parlay_result') not in {'cashed', 'still_live'}:
            issues.append(self._issue(seed, case, 'parlay_contradiction_all_wins', {'parlay_result': response.get('parlay_result')}, response))
        if normalized and all(item == 'void' for item in normalized) and response.get('parlay_result') == 'lost':
            issues.append(self._issue(seed, case, 'parlay_contradiction_all_void', {}, response))

        return issues

    def _issue(self, seed: int, case: FuzzCase, issue_type: str, details: dict[str, Any], response: dict[str, Any] | None) -> FuzzIssue:
        snapshot = response if isinstance(response, dict) else {'raw': response}
        return FuzzIssue(
            seed=seed,
            case_id=case.case_id,
            mode=case.mode,
            input_text=case.text,
            bet_date=case.bet_date,
            issue_type=issue_type,
            details=details,
            response_snapshot=snapshot,
        )


class FuzzRunner:
    def __init__(self, *, seed: int, mode: str, min_legs: int = 1, max_legs: int = 12) -> None:
        self.seed = seed
        self.mode = mode
        self.rng = random.Random(seed)
        self.assembler = SlipAssembler()
        self.checker = InvariantChecker()
        self.min_legs = min_legs
        self.max_legs = max_legs

    def generate_case(self, idx: int) -> FuzzCase:
        mode = self.mode
        if mode == 'mixed':
            mode = self.rng.choices(['settlement', 'parser', 'ambiguity'], weights=[0.6, 0.25, 0.15], k=1)[0]
        case_id = f'{mode}_{idx:06d}'
        return self.assembler.make_case(self.rng, case_id=case_id, mode=mode, min_legs=self.min_legs, max_legs=self.max_legs)

    def run_cases(
        self,
        *,
        count: int,
        submitter: Callable[[FuzzCase], tuple[int, dict[str, Any] | None]],
        determinism_checks: int = 0,
    ) -> tuple[list[FuzzOutcome], list[FuzzIssue], list[FuzzIssue]]:
        outcomes: list[FuzzOutcome] = []
        suspicious: list[FuzzIssue] = []
        hard_failures: list[FuzzIssue] = []

        for idx in range(count):
            case = self.generate_case(idx)
            status_code, response = submitter(case)
            outcome = FuzzOutcome(case=case, status_code=status_code, response=response)
            issues = self.checker.evaluate(seed=self.seed, case=case, status_code=status_code, response=response)
            outcome.issues.extend(issues)
            if status_code != 200:
                outcome.hard_failure = True

            if outcome.hard_failure:
                hard_failures.extend(issues or [self.checker._issue(self.seed, case, 'hard_failure', {}, response)])
            else:
                suspicious.extend(issues)
            outcomes.append(outcome)

            if determinism_checks > 0 and status_code == 200:
                hard_failures.extend(self._check_determinism(case, submitter, runs=determinism_checks + 1))

        return outcomes, suspicious, hard_failures

    def _check_determinism(
        self,
        case: FuzzCase,
        submitter: Callable[[FuzzCase], tuple[int, dict[str, Any] | None]],
        runs: int,
    ) -> list[FuzzIssue]:
        observed: list[tuple[int, str, tuple[tuple[str, str], ...]]] = []
        for _ in range(runs):
            status, body = submitter(case)
            if not isinstance(body, dict):
                continue
            parlay = str(body.get('parlay_result'))
            parse_conf = str(body.get('parse_confidence'))
            legs: list[tuple[str, str]] = []
            for item in body.get('legs', []):
                if isinstance(item, dict):
                    legs.append((str(item.get('result')), str(item.get('matched_event'))))
            observed.append((status, f'{parlay}:{parse_conf}', tuple(legs)))

        if not observed:
            return []
        first = observed[0]
        if any(sample != first for sample in observed[1:]):
            return [
                FuzzIssue(
                    seed=self.seed,
                    case_id=case.case_id,
                    mode=case.mode,
                    input_text=case.text,
                    bet_date=case.bet_date,
                    issue_type='nondeterministic_response',
                    details={'observed_runs': len(observed)},
                    response_snapshot={'observed': observed},
                )
            ]
        return []


def write_report(path: str | Path, *, seed: int, mode: str, outcomes: list[FuzzOutcome], suspicious: list[FuzzIssue], hard_failures: list[FuzzIssue]) -> None:
    output = {
        'seed': seed,
        'mode': mode,
        'cases_run': len(outcomes),
        'passed_invariants': len(outcomes) - len(suspicious) - len(hard_failures),
        'flagged_suspicious': len(suspicious),
        'hard_failures': len(hard_failures),
        'issues': [asdict(issue) for issue in [*hard_failures, *suspicious]],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2), encoding='utf-8')


def persist_failure_cases(base_dir: str | Path, issues: list[FuzzIssue]) -> None:
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        path = root / f'{issue.case_id}.json'
        path.write_text(json.dumps(asdict(issue), indent=2), encoding='utf-8')

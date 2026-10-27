"""Generated markets, end to end, compared exactly with the oracle.

Clean logs (no erroneous messages) at a shallow, a typical and a deep target. Each case runs in
process through `cli.run` and in a real subprocess. Expected failures, by what is missing:

  * target 1: dead orders shadow ids re-used after removal (#7);
"""

import re

import pytest
from system_cases import TARGETS, expected, market, market_param, scaled
from system_run import run_in_process, run_subprocess

MESSAGES = scaled(3000)
SEEDS = (1, 2)
# Format only: the sign is allowed because values are checked against the oracle elsewhere
# (today the dead-order bug (#7) can make a total negative).
RESULT_LINE = re.compile(r"[0-9]+ [BS] (-?[0-9]+\.[0-9]{2}|NA)")


@pytest.mark.parametrize("target", [market_param(target) for target in TARGETS])
@pytest.mark.parametrize("seed", SEEDS)
class TestCleanMarkets:
    def test_in_process_matches_oracle(self, seed: int, target: int) -> None:
        result = run_in_process(market(seed, MESSAGES).text, target)
        assert result.stdout == expected(seed, MESSAGES, target).stdout
        assert result.stderr == ""

    def test_subprocess_matches_oracle(self, seed: int, target: int) -> None:
        result = run_subprocess([str(target)], market(seed, MESSAGES).text)
        assert result.returncode == 0
        assert result.stdout == expected(seed, MESSAGES, target).stdout
        assert result.stderr == ""


@pytest.mark.parametrize("target", [market_param(target) for target in TARGETS])
class TestMarketsWithOverReduces:
    """About 3% of the reduces are larger than the order: the spec says that removes it."""

    def test_in_process_matches_oracle(self, target: int) -> None:
        result = run_in_process(market(3, MESSAGES, 0.03).text, target)
        assert result.stdout == expected(3, MESSAGES, target, 0.03).stdout
        assert result.stderr == ""

    def test_subprocess_matches_oracle(self, target: int) -> None:
        result = run_subprocess([str(target)], market(3, MESSAGES, 0.03).text)
        assert (result.returncode, result.stderr) == (0, "")
        assert result.stdout == expected(3, MESSAGES, target, 0.03).stdout


@pytest.mark.parametrize("target", TARGETS)
def test_stdout_carries_only_result_lines(target: int) -> None:
    """Whatever the totals, stdout is a pipeline-friendly stream of `ts B|S total` lines."""
    result = run_in_process(market(1, MESSAGES).text, target)
    lines = result.stdout.splitlines()
    assert lines
    assert all(RESULT_LINE.fullmatch(line) for line in lines)
    assert result.stdout.endswith("\n")
    assert result.returncode == 0


def test_oracle_output_has_no_repeated_line_per_side() -> None:
    """The oracle itself honours "print only when the total changes" (sanity of the oracle)."""
    for target in TARGETS:
        last: dict[str, str] = {}
        for line in expected(1, MESSAGES, target).lines:
            _, side, value = line.split()
            assert last.get(side) != value
            last[side] = value

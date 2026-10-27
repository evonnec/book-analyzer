"""Hand-written scenarios for the known defects, each in process and in a real subprocess.

Every scenario states its expected output literally (the oracle self-tests pin the same
semantics), so a failure reads as a plain diff. Prices here are exactly representable unless
the scenario is about money.
"""

from collections.abc import Callable

import pytest
from system_cases import xfail
from system_oracle import oracle
from system_run import CliResult, mentions_line, run_in_process, run_subprocess


def in_process(log: str, target: int) -> CliResult:
    return run_in_process(log, target)


def subprocess_(log: str, target: int) -> CliResult:
    return run_subprocess([str(target)], log)


Runner = Callable[[str, int], CliResult]


@pytest.fixture(params=[in_process, subprocess_], ids=["in-process", "subprocess"])
def runner(request: pytest.FixtureRequest) -> Runner:
    runner: Runner = request.param
    return runner


DEAD_ORDERS = xfail("#7", "a fully reduced order stays in the book")

OVER_REDUCE_CASES = [
    # An over-reduce used to leave size -2: it offsets the next order instead of vanishing.
    pytest.param(
        "1 A a S 1.00 1\n2 R a 3\n3 A b S 2.00 5\n",
        1,
        "1 B 1.00\n2 B NA\n3 B 2.00\n",
        id="over-reduce-ask",
    ),
    pytest.param(
        "1 A a B 5.00 1\n2 R a 3\n3 A b B 4.00 5\n",
        1,
        "1 S 5.00\n2 S NA\n3 S 4.00\n",
        id="over-reduce-bid",
    ),
    pytest.param(
        "1 A a S 1.00 2\n2 R a 5\n3 A b S 2.00 2\n",
        2,
        "1 B 2.00\n2 B NA\n3 B 4.00\n",
        id="over-reduce-then-fill-whole-target",
    ),
    pytest.param(
        "1 A a S 1.00 3\n2 A b S 2.00 3\n3 R a 10\n",
        3,
        "1 B 3.00\n3 B 6.00\n",
        id="over-reduce-of-the-best-ask",
    ),
    # An id that moved sides: the dead copy on the other side must not catch later reduces.
    pytest.param(
        "1 A a S 1.00 2\n2 R a 2\n3 A a B 2.00 2\n4 R a 2\n5 A a S 3.00 2\n6 R a 1\n",
        2,
        "1 B 2.00\n2 B NA\n3 S 4.00\n4 S NA\n5 B 6.00\n6 B NA\n",
        id="id-changes-sides-twice",
    ),
]


@pytest.mark.parametrize(("log", "target", "expected"), OVER_REDUCE_CASES)
class TestOverReduceAndReuse:
    @DEAD_ORDERS
    def test_over_reduce_removes_the_order(
        self, runner: Runner, log: str, target: int, expected: str
    ) -> None:
        result = runner(log, target)
        assert result.stdout == expected
        assert result.returncode == 0

    def test_expectation_matches_the_oracle(self, log: str, target: int, expected: str) -> None:
        assert oracle(log, target).stdout == expected


@pytest.mark.parametrize(
    ("log", "target", "expected"),
    [
        ("1 A a S 1.00 1\n2 R a 1\n3 A a S 5.00 1\n", 1, "1 B 1.00\n2 B NA\n3 B 5.00\n"),
        ("1 A a S 1.00 1\n2 R a 99\n3 A a S 5.00 1\n", 1, "1 B 1.00\n2 B NA\n3 B 5.00\n"),
        ("1 A a S 1.00 3\n2 R a 1\n3 R a 1\n", 3, "1 B 3.00\n2 B NA\n"),
        ("1 A a B 2.00 1\n2 R a 1\n3 A a B 3.00 1\n", 1, "1 S 2.00\n2 S NA\n3 S 3.00\n"),
    ],
    ids=["reuse-after-removal", "reuse-after-over-reduce", "partial-reduces", "reuse-bid"],
)
def test_behaviour_that_already_works(runner: Runner, log: str, target: int, expected: str) -> None:
    result = runner(log, target)
    assert result.stdout == expected
    assert result.returncode == 0


@xfail("#9 (needs #7)", "a reduce of a removed id crashes or corrupts the book")
def test_reduce_after_removal_is_a_warning(runner: Runner) -> None:
    log = "1 A a S 1.00 5\n2 R a 5\n3 R a 1\n4 A b S 2.00 2\n"
    result = runner(log, 1)
    assert result.stdout == "1 B 1.00\n2 B NA\n4 B 2.00\n"
    assert len(result.warning_lines) == 1
    assert mentions_line(result.warning_lines[0], 3)


class TestExactMoney:
    @xfail("#8", "float sums differ in the last bit and print a repeated line")
    def test_reordered_sum_does_not_repeat_a_line(self, runner: Runner) -> None:
        log = "1 A x0 S 0.10 1\n2 A x1 S 0.70 1\n3 A a S 0.70 1\n4 A b S 0.70 2\n5 R a 1\n"
        result = runner(log, 4)
        assert result.stdout == "4 B 2.20\n"
        assert oracle(log, 4).stdout == "4 B 2.20\n"

    @pytest.mark.parametrize(
        ("size", "total"),
        [
            (10**12, "99999999999990000000000.00"),
            # 31 significant digits: beyond Decimal's default context (28) as well
            (123456789012345678, "12345678901233333232109876543.22"),
        ],
    )
    @xfail("#8", "float totals lose precision")
    def test_large_total_is_exact(self, runner: Runner, size: int, total: str) -> None:
        log = f"1 A a S 99999999999.99 {size}\n"
        assert runner(log, size).stdout == f"1 B {total}\n"

    @xfail("#8", "a size beyond float range raises OverflowError")
    def test_huge_size_does_not_crash(self, runner: Runner) -> None:
        log = f"1 A a S 1.00 {10**400}\n"
        result = runner(log, 10**401)
        assert result.stdout == ""
        assert result.returncode == 0

    @xfail("#8", "totals that print the same are compared by their float values")
    def test_total_changing_only_below_a_cent_prints_nothing(self, runner: Runner) -> None:
        # 1.001 -> 1.002 both print as 1.00: the *printed* value did not change.
        log = "1 A a S 1.001 1\n2 A b S 1.002 1\n3 R a 1\n"
        assert runner(log, 1).stdout == "1 B 1.00\n"

    @pytest.mark.parametrize(
        ("price", "total"), [("0.015", "0.02"), ("0.125", "0.13"), ("1.005", "1.01")]
    )
    @xfail("#8", "totals are rounded as binary floats, not half up")
    def test_half_cents_round_up(self, runner: Runner, price: str, total: str) -> None:
        assert runner(f"9 A a S {price} 1\n", 1).stdout == f"9 B {total}\n"

"""Error-injected logs: bad lines warn on stderr, are skipped, and never change the output.

A whole generated log with every class of erroneous message inserted at known positions needs
the dead-order fix (#7), exact money (#8) and the validation (#9), so it is expected to fail
until #9 lands. The per-class tests isolate each class on a tiny log.
"""

import sys

import pytest
from system_cases import TARGETS, expected, market, scaled, xfail
from system_gen import BAD_LINE_CLASSES, Context, Injected, inject_errors
from system_oracle import oracle
from system_run import CliResult, mentions_line, run_in_process, run_subprocess

BOM = chr(0xFEFF)
MESSAGES = scaled(3000)
FULL_STACK = xfail(
    "#9 (needs #7, #8)", "generated errors need dead-order removal, exact sums, validation"
)


def injected_market(seed: int, target: int) -> Injected:
    del target
    return inject_errors(market(seed, MESSAGES).lines, seed=seed, count=max(40, MESSAGES // 25))


def assert_one_warning_per_bad_line(result: CliResult, injected: Injected) -> None:
    warnings = result.warning_lines
    assert len(warnings) == len(injected.bad_lines)
    for warning, number in zip(warnings, injected.bad_lines, strict=True):
        assert mentions_line(warning, number)


@pytest.mark.parametrize(
    "target", [pytest.param(target, marks=FULL_STACK, id=f"target{target}") for target in TARGETS]
)
class TestInjectedMarkets:
    def test_in_process(self, target: int) -> None:
        injected = injected_market(1, target)
        result = run_in_process(injected.text, target)
        assert result.stdout == expected(1, MESSAGES, target).stdout  # = the clean subset
        assert_one_warning_per_bad_line(result, injected)

    def test_subprocess(self, target: int) -> None:
        injected = injected_market(1, target)
        result = run_subprocess([str(target)], injected.text)
        assert result.returncode == 0
        assert result.stdout == expected(1, MESSAGES, target).stdout
        assert_one_warning_per_bad_line(result, injected)


def test_injected_market_expectation_is_consistent() -> None:
    """The oracle agrees with the injector about what is bad (guards the expectations above)."""
    injected = injected_market(1, 200)
    assert oracle(injected.text, 200).rejected == injected.bad_lines


PRELUDE = ["1 A a S 1.00 5", "2 A r B 2.00 1", "3 R r 1"]  # live: a; removed: r
FOLLOW_UP = "5 A z B 3.00 2"
NEEDS_DEAD_ORDER_REMOVAL = {"reduce of removed id"}


def class_param(name: str) -> object:
    issue = "#9 (needs #7)" if name in NEEDS_DEAD_ORDER_REMOVAL else "#9"
    return pytest.param(name, marks=xfail(issue, f"'{name}' is not validated"), id=name)


@pytest.mark.parametrize("name", [class_param(name) for name in BAD_LINE_CLASSES])
class TestEachClassOfErrorIsSkipped:
    def log(self, name: str) -> str:
        context = Context(timestamp="3", live={"a": "S"}, removed=["r"])
        bad = BAD_LINE_CLASSES[name](context)
        assert bad is not None
        return "".join(f"{line}\n" for line in [*PRELUDE, bad, FOLLOW_UP])

    def test_in_process(self, name: str) -> None:
        log = self.log(name)
        reference = oracle(log, 2)
        assert reference.rejected == [4]
        result = run_in_process(log, 2)
        assert result.stdout == reference.stdout
        assert len(result.warning_lines) == 1
        assert mentions_line(result.warning_lines[0], 4)

    def test_subprocess(self, name: str) -> None:
        log = self.log(name)
        reference = oracle(log, 2)
        result = run_subprocess(["2"], log)
        assert result.returncode == 0
        assert result.stdout == reference.stdout
        assert len(result.warning_lines) == 1
        assert mentions_line(result.warning_lines[0], 4)
        assert "Traceback" not in result.stderr


@xfail("#9", "a UTF-8 BOM is echoed into the first output timestamp")
def test_bom_is_never_echoed() -> None:
    result = run_subprocess(["1"], b"\xef\xbb\xbf1 A a S 1.00 1\n2 A b S 0.50 1\n")
    assert result.returncode == 0
    assert BOM not in result.stdout
    # The BOM is either stripped (both lines processed) or the first line is rejected.
    assert result.stdout in ("1 B 1.00\n2 B 0.50\n", "2 B 0.50\n")
    assert len(result.warning_lines) == (0 if result.stdout.startswith("1 ") else 1)


@xfail("#9", "an undecodable byte aborts the run when UTF-8 mode is off")
def test_undecodable_bytes_are_a_warning_not_a_crash() -> None:
    locale = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    env = {"PYTHONUTF8": "0", "LC_ALL": locale}
    stdin = b"1 A a S 1.00 1\n2 A b S \xff 1\n3 A c S 0.50 1\n"
    result = run_subprocess(["1"], stdin, env=env)
    assert result.returncode == 0
    assert result.stdout == "1 B 1.00\n3 B 0.50\n"
    assert len(result.warning_lines) == 1
    assert mentions_line(result.warning_lines[0], 2)
    assert "Traceback" not in result.stderr

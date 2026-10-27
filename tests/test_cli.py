"""Tests for the command line layer: parsing, formatting and the run loop.

Prices and totals go through `price` and `shown` and the run loop through `run_in_process`
(see tests/system/system_api.py), so these tests hold before and after #8 (integer money) and
#9 (`MessageError`, an error stream for `run`).
"""

from collections.abc import Iterator
from io import StringIO
from typing import TextIO, cast

import pytest
from system_api import call_run, price, rejects, shown
from system_run import CliResult, run_in_process

from book_analyzer import AddMessage, ReduceMessage, Side, Update
from book_analyzer.cli import format_update, parse_line, parse_price


def run_log(log: str, target_size: int = 200) -> CliResult:
    return run_in_process(log, target_size)


def without_warnings(output: str) -> str:
    """Drop warning lines, so tests do not depend on which stream they are written to."""
    return "".join(line for line in output.splitlines(keepends=True) if "arning" not in line)


def warnings(result: CliResult) -> list[str]:
    """Warning lines from either stream, so a warning on the wrong stream is still counted."""
    return [line for line in (result.stdout + result.stderr).splitlines() if "arning" in line]


class TestParseLine:
    def test_add(self) -> None:
        assert parse_line("28800538 A b S 44.26 100") == AddMessage(
            timestamp="28800538", order_id="b", side=Side.SELL, price=price("44.26"), size=100
        )
        assert shown(price("44.26")) == "44.26"

    def test_add_bid(self) -> None:
        message = parse_line("1 A x B 10 3")
        assert message == AddMessage("1", "x", Side.BUY, price("10"), 3)
        assert shown(price("10")) == "10.00"

    def test_reduce(self) -> None:
        assert parse_line("28800744 R b 100") == ReduceMessage(
            timestamp="28800744", order_id="b", size=100
        )

    @pytest.mark.parametrize("suffix", ["", "\n", "\r\n", " ", "  \n", "\t\n"])
    def test_trailing_whitespace_is_ignored(self, suffix: str) -> None:
        assert parse_line("5 R b 7" + suffix) == ReduceMessage("5", "b", 7)
        assert parse_line("5 A b S 1.5 7" + suffix) == AddMessage(
            "5", "b", Side.SELL, price("1.5"), 7
        )

    def test_leading_whitespace_is_ignored(self) -> None:
        assert parse_line("  5 R b 7") == ReduceMessage("5", "b", 7)

    @pytest.mark.parametrize("line", ["", "\n", "   ", "\r\n"])
    def test_blank_line_is_invalid(self, line: str) -> None:
        assert rejects(line)

    @pytest.mark.parametrize(
        "line",
        ["1", "1 A", "1 A a", "1 R b 5 6", "1 A a S 1.00", "1 A a S 1.00 1 extra"],
    )
    def test_wrong_field_count_is_invalid(self, line: str) -> None:
        assert rejects(line)

    @pytest.mark.parametrize(
        "line",
        [
            "1 A a S cheap 1",
            "1 A a S 1.00 many",
            "1 R a many",
            "1 A a X 1.00 1",
            "1 A a 4",
            "1 X a 4",
            "1 R a S 1.00 1",
            "1 X a S 1.00 1",
        ],
    )
    def test_malformed_content_is_invalid(self, line: str) -> None:
        assert rejects(line)


class TestFormatUpdate:
    def test_na(self) -> None:
        assert format_update(Update("100", Side.BUY, None)) == "100 B NA\n"
        assert format_update(Update("100", Side.SELL, None)) == "100 S NA\n"

    @pytest.mark.parametrize(
        ("total", "text"),
        [("3", "3.00"), ("44.1", "44.10"), ("8832.56", "8832.56"), ("1.234", "1.23")],
    )
    def test_two_decimals(self, total: str, text: str) -> None:
        assert format_update(Update("7", Side.SELL, price(total))) == f"7 S {text}\n"

    def test_zero(self) -> None:
        assert format_update(Update("7", Side.SELL, price("1") * 0)) == "7 S 0.00\n"

    def test_ends_with_single_newline(self) -> None:
        assert format_update(Update("7", Side.BUY, price("1"))).endswith("B 1.00\n")


class TestSpecificationSample:
    def test_sample(self, sample_input: str, sample_expected: str) -> None:
        # The sample starts with a blank line, which produces a warning on stdout.
        assert run_log(sample_input).stdout == sample_expected

    def test_sample_without_blank_line(self, sample_input_clean: str, sample_expected: str) -> None:
        assert run_log(sample_input_clean) == CliResult(0, sample_expected, "")

    def test_sample_ignoring_warnings(self, sample_input: str, sample_expected: str) -> None:
        result = run_log(sample_input)
        assert without_warnings(result.stdout) == sample_expected
        assert len(warnings(result)) == 1

    def test_sample_with_crlf_line_endings(
        self, sample_input_clean: str, sample_expected: str
    ) -> None:
        result = run_log(sample_input_clean.replace("\n", "\r\n"))
        assert result == CliResult(0, sample_expected, "")


class TestRun:
    def test_empty_input(self) -> None:
        assert run_log("") == CliResult(0, "", "")

    def test_missing_final_newline(self) -> None:
        assert run_log("1 A a S 1.00 1", target_size=1).stdout == "1 B 1.00\n"

    def test_buy_and_sell_lines(self) -> None:
        log = "1 A a S 2.00 1\n2 A b B 1.50 1\n3 R a 1\n"
        assert run_log(log, target_size=1).stdout == "1 B 2.00\n2 S 1.50\n3 B NA\n"

    def test_unchanged_total_prints_nothing(self) -> None:
        log = "1 A a S 1.00 1\n2 A b S 2.00 1\n3 A c B 1.00 5\n3 A d B 0.50 5\n"
        assert run_log(log, target_size=1).stdout == "1 B 1.00\n3 S 1.00\n"

    def test_wrong_field_count_warns_and_continues(self) -> None:
        log = "1 A a S 1.00 1\n2 A a\n3 A b S 0.50 1\n"
        result = run_log(log, target_size=1)
        assert without_warnings(result.stdout) == "1 B 1.00\n3 B 0.50\n"
        assert len(warnings(result)) == 1
        assert "line 2" in warnings(result)[0]

    @pytest.mark.parametrize("bad_line", ["", "2 A a", "2 A a S 1.00 1 extra"])
    def test_warning_goes_to_stderr(self, bad_line: str) -> None:
        result = run_log(f"1 A a S 1.00 1\n{bad_line}\n", target_size=1)
        assert "warning" in result.stderr.lower()
        assert result.stdout == "1 B 1.00\n"


VALID_ASK = "1 A a S 1.00 5"  # target 2: "1 B 2.00"
VALID_BID = "3 A z B 3.00 2"  # target 2: "3 S 6.00"
EXPECTED_VALID_ONLY = "1 B 2.00\n3 S 6.00\n"


class TestMalformedMessagesAreSkipped:
    """Per the specification a bad message warns on stderr and processing continues."""

    @pytest.mark.parametrize(
        "bad_line",
        [
            "",
            "   ",
            "2 A a",
            "2 R a 1 1",
            "2 A q S cheap 1",
            "2 A q S 1.00 many",
            "2 R a many",
            "2 A q X 1.00 1",
            "2 R nope 1",
            "2 A a S 5.00 5",
            "2 X a 4",
            "2 R q S 0.50 1",
        ],
    )
    def test_bad_line_is_skipped_and_processing_continues(self, bad_line: str) -> None:
        result = run_log(f"{VALID_ASK}\n{bad_line}\n{VALID_BID}\n", target_size=2)
        assert without_warnings(result.stdout) == EXPECTED_VALID_ONLY
        assert len(warnings(result)) == 1
        assert "line 2" in warnings(result)[0]


class TestParsePrice:
    @pytest.mark.parametrize(
        ("text", "units"),
        [
            ("44.26", 44_260_000),
            ("1", 1_000_000),
            ("0.5", 500_000),
            ("2.675", 2_675_000),
            ("0.000001", 1),
            ("007.10", 7_100_000),
        ],
    )
    def test_exact_units(self, text: str, units: int) -> None:
        assert parse_price(text) == units

    @pytest.mark.parametrize(
        "text",
        ["1.0000001", "1e2", "+1", "-1.00", ".5", "5.", "1_0.00", "nan", "", "\u0661.\u0660\u0660"],
    )
    def test_rejects_anything_outside_the_grammar(self, text: str) -> None:
        with pytest.raises(ValueError, match="invalid price"):
            parse_price(text)


class TestExactMoney:
    def test_reordered_sum_does_not_repeat_a_line(self) -> None:
        # Message 5 removes order "a" (the fill is still 0.10 + 0.70 + 0.70 + 0.70), but the
        # float sum is evaluated over different terms and differs in the last bit.
        log = "1 A x0 S 0.10 1\n2 A x1 S 0.70 1\n3 A a S 0.70 1\n4 A b S 0.70 2\n5 R a 1\n"
        assert run_log(log, target_size=4).stdout == "4 B 2.20\n"

    @pytest.mark.parametrize(
        ("ask", "total"),
        [
            ("0.015", "0.02"),
            ("0.125", "0.13"),
            ("1.005", "1.01"),
            ("2.675", "2.68"),
            ("0.014", "0.01"),
            ("0.016", "0.02"),
        ],
    )
    def test_half_cent_totals_round_half_up(self, ask: str, total: str) -> None:
        # Exact decimal arithmetic on the input price, rounded half up to 2 places.
        assert run_log(f"9 A a S {ask} 1\n", target_size=1).stdout == f"9 B {total}\n"


class LazyInput:
    """A text stream that records the output written so far each time a line is requested."""

    def __init__(self, lines: list[str], output: StringIO) -> None:
        self._lines = iter(lines)
        self._output = output
        self.output_seen_at_request: list[str] = []

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        self.output_seen_at_request.append(self._output.getvalue())
        return next(self._lines)

    def readline(self) -> str:
        try:
            return next(self)
        except StopIteration:
            return ""

    def readlines(self) -> list[str]:
        return list(self)


class TestStreaming:
    @pytest.mark.xfail(
        strict=True, reason="#12: stdin is consumed with readlines() before any output is written"
    )
    def test_output_is_written_before_input_is_exhausted(self) -> None:
        output = StringIO()
        lazy = LazyInput(["1 A a S 1.00 1\n", "2 A b S 0.50 1\n", "3 A c S 0.25 1\n"], output)
        call_run(cast(TextIO, lazy), output, StringIO(), target_size=1)
        assert output.getvalue() == "1 B 1.00\n2 B 0.50\n3 B 0.25\n"
        # When the third line is requested the first two results must already be out.
        assert lazy.output_seen_at_request[2] == "1 B 1.00\n2 B 0.50\n"

"""Tests for the command line layer: parsing, formatting and the run loop."""

from collections.abc import Iterator
from io import StringIO
from typing import TextIO, cast

import pytest

from book_analyzer import AddMessage, ReduceMessage, Side, Update
from book_analyzer.cli import format_update, parse_line, run


def run_log(log: str, target_size: int = 200) -> str:
    output_file = StringIO()
    run(input_file=StringIO(log), output_file=output_file, target_size=target_size)
    return output_file.getvalue()


def without_warnings(output: str) -> str:
    """Drop warning lines, so tests do not depend on which stream they are written to."""
    return "".join(line for line in output.splitlines(keepends=True) if "arning" not in line)


class TestParseLine:
    def test_add(self) -> None:
        assert parse_line("28800538 A b S 44.26 100") == AddMessage(
            timestamp="28800538", order_id="b", side=Side.SELL, price=44.26, size=100
        )

    def test_add_bid(self) -> None:
        message = parse_line("1 A x B 10 3")
        assert message == AddMessage("1", "x", Side.BUY, 10.0, 3)

    def test_reduce(self) -> None:
        assert parse_line("28800744 R b 100") == ReduceMessage(
            timestamp="28800744", order_id="b", size=100
        )

    @pytest.mark.parametrize("suffix", ["", "\n", "\r\n", " ", "  \n", "\t\n"])
    def test_trailing_whitespace_is_ignored(self, suffix: str) -> None:
        assert parse_line("5 R b 7" + suffix) == ReduceMessage("5", "b", 7)
        assert parse_line("5 A b S 1.5 7" + suffix) == AddMessage("5", "b", Side.SELL, 1.5, 7)

    def test_leading_whitespace_is_ignored(self) -> None:
        assert parse_line("  5 R b 7") == ReduceMessage("5", "b", 7)

    @pytest.mark.parametrize("line", ["", "\n", "   ", "\r\n"])
    def test_blank_line_is_invalid(self, line: str) -> None:
        assert parse_line(line) is None

    @pytest.mark.parametrize(
        "line",
        ["1", "1 A", "1 A a", "1 R b 5 6", "1 A a S 1.00", "1 A a S 1.00 1 extra"],
    )
    def test_wrong_field_count_is_invalid(self, line: str) -> None:
        assert parse_line(line) is None

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param(
                "1 A a S cheap 1",
                marks=pytest.mark.xfail(strict=True, reason="non-numeric price raises ValueError"),
            ),
            pytest.param(
                "1 A a S 1.00 many",
                marks=pytest.mark.xfail(
                    strict=True, reason="non-numeric add size raises ValueError"
                ),
            ),
            pytest.param(
                "1 R a many",
                marks=pytest.mark.xfail(
                    strict=True, reason="non-numeric reduce size raises ValueError"
                ),
            ),
            pytest.param(
                "1 A a X 1.00 1",
                marks=pytest.mark.xfail(strict=True, reason="unknown side raises ValueError"),
            ),
            pytest.param(
                "1 A a 4",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 4 fields parse as a reduce"
                ),
            ),
            pytest.param(
                "1 X a 4",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 4 fields parse as a reduce"
                ),
            ),
            pytest.param(
                "1 R a S 1.00 1",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 6 fields parse as an add"
                ),
            ),
            pytest.param(
                "1 X a S 1.00 1",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 6 fields parse as an add"
                ),
            ),
        ],
    )
    def test_malformed_content_is_invalid(self, line: str) -> None:
        assert parse_line(line) is None


class TestFormatUpdate:
    def test_na(self) -> None:
        assert format_update(Update("100", Side.BUY, None)) == "100 B NA\n"
        assert format_update(Update("100", Side.SELL, None)) == "100 S NA\n"

    @pytest.mark.parametrize(
        ("total", "text"),
        [(3.0, "3.00"), (0.0, "0.00"), (44.1, "44.10"), (8832.56, "8832.56"), (1.234, "1.23")],
    )
    def test_two_decimals(self, total: float, text: str) -> None:
        assert format_update(Update("7", Side.SELL, total)) == f"7 S {text}\n"

    def test_ends_with_single_newline(self) -> None:
        assert format_update(Update("7", Side.BUY, 1.0)).endswith("B 1.00\n")


class TestSpecificationSample:
    @pytest.mark.xfail(strict=True, reason="warnings are written to stdout instead of stderr")
    def test_sample(self, sample_input: str, sample_expected: str) -> None:
        # The sample starts with a blank line, which produces a warning on stdout.
        assert run_log(sample_input) == sample_expected

    def test_sample_without_blank_line(self, sample_input_clean: str, sample_expected: str) -> None:
        assert run_log(sample_input_clean) == sample_expected

    def test_sample_ignoring_warnings(self, sample_input: str, sample_expected: str) -> None:
        assert without_warnings(run_log(sample_input)) == sample_expected

    def test_sample_with_crlf_line_endings(
        self, sample_input_clean: str, sample_expected: str
    ) -> None:
        assert run_log(sample_input_clean.replace("\n", "\r\n")) == sample_expected


class TestRun:
    def test_empty_input(self) -> None:
        assert run_log("") == ""

    def test_missing_final_newline(self) -> None:
        assert run_log("1 A a S 1.00 1", target_size=1) == "1 B 1.00\n"

    def test_buy_and_sell_lines(self) -> None:
        log = "1 A a S 2.00 1\n2 A b B 1.50 1\n3 R a 1\n"
        assert run_log(log, target_size=1) == "1 B 2.00\n2 S 1.50\n3 B NA\n"

    def test_unchanged_total_prints_nothing(self) -> None:
        log = "1 A a S 1.00 1\n2 A b S 2.00 1\n3 A c B 1.00 5\n3 A d B 0.50 5\n"
        assert run_log(log, target_size=1) == "1 B 1.00\n3 S 1.00\n"

    def test_wrong_field_count_warns_and_continues(self) -> None:
        log = "1 A a S 1.00 1\n2 A a\n3 A b S 0.50 1\n"
        output = run_log(log, target_size=1)
        assert without_warnings(output) == "1 B 1.00\n3 B 0.50\n"
        assert output.count("Warning") == 1
        assert "line 2" in output

    @pytest.mark.xfail(strict=True, reason="warnings are written to stdout instead of stderr")
    @pytest.mark.parametrize("bad_line", ["", "2 A a", "2 A a S 1.00 1 extra"])
    def test_warning_goes_to_stderr(
        self, bad_line: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = run_log(f"1 A a S 1.00 1\n{bad_line}\n", target_size=1)
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()
        assert "arning" not in output
        assert output == "1 B 1.00\n"


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
            pytest.param(
                "2 A q S cheap 1",
                marks=pytest.mark.xfail(strict=True, reason="non-numeric price raises ValueError"),
            ),
            pytest.param(
                "2 A q S 1.00 many",
                marks=pytest.mark.xfail(strict=True, reason="non-numeric size raises ValueError"),
            ),
            pytest.param(
                "2 R a many",
                marks=pytest.mark.xfail(strict=True, reason="non-numeric size raises ValueError"),
            ),
            pytest.param(
                "2 A q X 1.00 1",
                marks=pytest.mark.xfail(strict=True, reason="unknown side raises ValueError"),
            ),
            pytest.param(
                "2 R nope 1",
                marks=pytest.mark.xfail(strict=True, reason="reduce of unknown id raises KeyError"),
            ),
            pytest.param(
                "2 A a S 5.00 5",
                marks=pytest.mark.xfail(
                    strict=True, reason="duplicate add silently replaces the existing order"
                ),
            ),
            pytest.param(
                "2 X a 4",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 4 fields apply as a reduce"
                ),
            ),
            pytest.param(
                "2 R q S 0.50 1",
                marks=pytest.mark.xfail(
                    strict=True, reason="message type is ignored: 6 fields apply as an add"
                ),
            ),
        ],
    )
    def test_bad_line_is_skipped_and_processing_continues(self, bad_line: str) -> None:
        output = run_log(f"{VALID_ASK}\n{bad_line}\n{VALID_BID}\n", target_size=2)
        assert without_warnings(output) == EXPECTED_VALID_ONLY


class TestKnownNumericDefects:
    @pytest.mark.xfail(
        strict=True,
        reason="totals are float sums compared with !=, so float noise prints a duplicate line",
    )
    def test_reordered_sum_does_not_repeat_a_line(self) -> None:
        # Message 5 removes order "a" (the fill is still 0.10 + 0.70 + 0.70 + 0.70), but the
        # float sum is evaluated over different terms and differs in the last bit.
        log = "1 A x0 S 0.10 1\n2 A x1 S 0.70 1\n3 A a S 0.70 1\n4 A b S 0.70 2\n5 R a 1\n"
        assert run_log(log, target_size=4) == "4 B 2.20\n"

    @pytest.mark.parametrize(
        ("price", "total"),
        [
            pytest.param(
                "0.015",
                "0.02",
                marks=pytest.mark.xfail(
                    strict=True, reason="float formatting rounds 0.015 down instead of half up"
                ),
            ),
            pytest.param(
                "0.125",
                "0.13",
                marks=pytest.mark.xfail(
                    strict=True, reason="float formatting rounds exact ties half to even"
                ),
            ),
            pytest.param(
                "1.005",
                "1.01",
                marks=pytest.mark.xfail(
                    strict=True, reason="float formatting rounds 1.005 down instead of half up"
                ),
            ),
            pytest.param(
                "2.675",
                "2.68",
                marks=pytest.mark.xfail(
                    strict=True, reason="float formatting rounds 2.675 down instead of half up"
                ),
            ),
            ("0.014", "0.01"),
            ("0.016", "0.02"),
        ],
    )
    def test_half_cent_totals_round_half_up(self, price: str, total: str) -> None:
        # Exact decimal arithmetic on the input price, rounded half up to 2 places.
        assert run_log(f"9 A a S {price} 1\n", target_size=1) == f"9 B {total}\n"


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
        strict=True, reason="stdin is consumed with readlines() before any output is written"
    )
    def test_output_is_written_before_input_is_exhausted(self) -> None:
        output = StringIO()
        lazy = LazyInput(["1 A a S 1.00 1\n", "2 A b S 0.50 1\n", "3 A c S 0.25 1\n"], output)
        run(input_file=cast(TextIO, lazy), output_file=output, target_size=1)
        assert output.getvalue() == "1 B 1.00\n2 B 0.50\n3 B 0.25\n"
        # When the third line is requested the first two results must already be out.
        assert lazy.output_seen_at_request[2] == "1 B 1.00\n2 B 0.50\n"

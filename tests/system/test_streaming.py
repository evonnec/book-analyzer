"""A live feed gets its answers while the feed is still open (a long-running pipeline)."""

import sys

import pytest
from system_cases import xfail
from system_run import Child

TIMEOUT = 15.0


@xfail("#12", "stdin is read to EOF first, and stdout is block-buffered")
@pytest.mark.skipif(sys.platform == "win32", reason="select() on pipes is POSIX only")
def test_results_arrive_before_stdin_is_closed() -> None:
    """With `--line-buffered`, one message in gives one result line out, with stdin still open."""
    child = Child(["--line-buffered", "1"])
    try:
        child.send("1 A a S 1.00 1\n")
        assert child.read_line(TIMEOUT) == "1 B 1.00\n"
        child.send("2 A b S 0.50 1\n")
        assert child.read_line(TIMEOUT) == "2 B 0.50\n"
        result = child.finish()
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    finally:
        child.kill()


@pytest.mark.skipif(sys.platform == "win32", reason="select() on pipes is POSIX only")
def test_output_arrives_at_end_of_input_without_the_flag() -> None:
    """The default (block-buffered, no flag needed) still delivers everything at EOF."""
    child = Child(["1"])
    try:
        child.send("1 A a S 1.00 1\n2 A b S 0.50 1\n")
        result = child.finish()
        assert (result.returncode, result.stdout, result.stderr) == (
            0,
            "1 B 1.00\n2 B 0.50\n",
            "",
        )
    finally:
        child.kill()

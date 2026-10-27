"""The command line contract as a pipeline tool: arguments, exit statuses, quiet shutdown.

All of these run the real program in a subprocess.
"""

import os
import re
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
from system_cases import xfail
from system_gen import cents
from system_run import SRC, Child, child_env, run_subprocess

ROOT = Path(__file__).resolve().parents[2]
ONE_ORDER = "1 A a S 1.00 5\n"


def usage_error(args: list[str], why: str) -> object:
    return pytest.param(args, marks=xfail("#11", why), id="-".join(args) or "no-args")


class TestArgumentMatrix:
    @pytest.mark.parametrize(
        "args",
        [
            usage_error([], "a missing TARGET_SIZE is an IndexError traceback"),
            usage_error(["abc"], "a non-integer TARGET_SIZE is a ValueError traceback"),
            usage_error(["1.5"], "a non-integer TARGET_SIZE is a ValueError traceback"),
            usage_error(["0"], "a zero TARGET_SIZE is accepted"),
            usage_error(["-5"], "a negative TARGET_SIZE is accepted"),
            usage_error(["+5"], "int() accepts a plus sign"),
            usage_error(["5_0"], "int() accepts underscores"),
            usage_error([" 5"], "int() accepts whitespace"),
            usage_error([""], "an empty TARGET_SIZE is a ValueError traceback"),
            usage_error([chr(0x665)], "int() accepts non-ASCII digits"),
        ],
    )
    def test_bad_target_size_is_a_usage_error(self, args: list[str]) -> None:
        result = run_subprocess(args, ONE_ORDER)
        assert result.returncode == 2
        assert "usage" in result.stderr.lower()
        assert "Traceback" not in result.stderr
        assert result.stdout == ""

    @pytest.mark.parametrize(
        ("args", "stdout"), [(["1"], "1 B 1.00\n"), (["5"], "1 B 5.00\n"), (["6"], "")]
    )
    def test_valid_target_size(self, args: list[str], stdout: str) -> None:
        result = run_subprocess(args, ONE_ORDER)
        assert (result.returncode, result.stdout, result.stderr) == (0, stdout, "")

    @xfail("#11", "there is no --help")
    def test_help_exits_zero_with_usage_on_stdout(self) -> None:
        result = run_subprocess(["--help"])
        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "target" in result.stdout.lower()
        assert result.stderr == ""

    def test_empty_input_is_not_an_error(self) -> None:
        assert run_subprocess(["1"], "").returncode == 0


def long_log(pairs: int) -> str:
    """Add then remove an order at a changing price: every message prints a line at target 1."""
    lines = []
    for i in range(pairs):
        lines.append(f"{2 * i + 1} A o{i} S {cents(100 + (i * 37) % 90)} 1")
        lines.append(f"{2 * i + 2} R o{i} 1")
    return "\n".join(lines) + "\n"


class TestQuietShutdown:
    @xfail("#11", "a closed stdout pipe gives a BrokenPipeError traceback and exit status 120")
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipe semantics")
    def test_closed_stdout_pipe_is_quiet(self) -> None:
        """Like `book-analyzer 1 < log | head -1` after the reader has gone away."""
        read_end, write_end = os.pipe()
        os.close(read_end)  # the consumer exited: every write to stdout hits a closed pipe
        try:
            # communicate() ignores a broken stdin pipe if the program stops reading early
            completed = subprocess.run(
                [sys.executable, "-m", "book_analyzer", "1"],
                input=long_log(1500).encode(),
                stdout=write_end,
                stderr=subprocess.PIPE,
                env=child_env(),
                timeout=60,
                check=False,
            )
        finally:
            os.close(write_end)
        stderr = completed.stderr.decode()
        assert "Traceback" not in stderr
        assert "BrokenPipeError" not in stderr
        assert stderr == ""
        # 141 = 128 + SIGPIPE, as #11 asks; dying of SIGPIPE looks the same to a shell.
        assert completed.returncode in (141, -signal.SIGPIPE)

    @xfail("#11", "Ctrl-C prints a KeyboardInterrupt traceback")
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
    def test_sigint_is_quiet(self) -> None:
        # A launcher imports the package first and announces readiness, so the signal cannot
        # arrive during interpreter start-up (where no program could handle it).
        launcher = (
            "import runpy, signal, sys\n"
            "signal.signal(signal.SIGINT, signal.default_int_handler)\n"
            "import book_analyzer.__main__\n"
            "sys.argv = ['book-analyzer', '1']\n"
            "print('ready', flush=True)\n"
            "runpy.run_module('book_analyzer', run_name='__main__')\n"
        )
        child = Child([], code=launcher)
        try:
            assert child.read_line(timeout=30) == "ready\n"
            time.sleep(0.5)  # let the program reach its read loop (stdin stays open)
            child.process.send_signal(signal.SIGINT)
            returncode = child.process.wait(timeout=30)
            assert child.process.stderr is not None
            stderr = child.process.stderr.read().decode()
        finally:
            child.kill()
        assert "Traceback" not in stderr
        assert "KeyboardInterrupt" not in stderr
        # 130 = 128 + SIGINT, as #11 asks; dying of SIGINT looks the same to a shell.
        assert returncode in (130, -signal.SIGINT)


class TestRejectedMessageReporting:
    BAD_LOG = "bad\nworse\n1 A a S 1.00 1\n"

    @xfail("#14", "no summary of rejected messages")
    def test_summary_counts_rejected_messages(self) -> None:
        result = run_subprocess(["1"], self.BAD_LOG)
        assert result.returncode == 0
        assert result.stdout == "1 B 1.00\n"
        # #14 leaves the wording open ("for example `rejected 3 of N messages`"): require only
        # a last stderr line that mentions rejection and the count.
        summary = result.stderr.splitlines()[-1]
        assert re.search(r"reject", summary, re.IGNORECASE)
        assert re.search(r"\b2\b", summary)
        assert len(result.warning_lines) == 2  # the summary itself names no line number

    def test_no_summary_on_clean_input(self) -> None:
        result = run_subprocess(["1"], ONE_ORDER)
        assert result.stderr == ""

    @xfail("#14", "there is no --strict")
    def test_strict_exits_one_after_processing_everything(self) -> None:
        result = run_subprocess(["--strict", "1"], self.BAD_LOG)
        assert result.returncode == 1
        assert result.stdout == "1 B 1.00\n"

    @xfail("#14", "there is no --strict")
    def test_strict_on_clean_input_exits_zero(self) -> None:
        result = run_subprocess(["--strict", "1"], ONE_ORDER)
        assert (result.returncode, result.stdout, result.stderr) == (0, "1 B 1.00\n", "")


class TestCommandNames:
    def test_module_entry_point_is_declared(self) -> None:
        scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
        assert scripts["book-analyzer"] == "book_analyzer.__main__:entry"

    def test_specification_command_name_is_declared(self) -> None:
        scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
        assert scripts["BookAnalyzer"] == "book_analyzer.__main__:entry"

    @pytest.mark.parametrize("name", ["book-analyzer", "BookAnalyzer"])
    def test_installed_script_prints_the_total(self, name: str) -> None:
        script = Path(sys.executable).parent / name
        if not script.is_file():
            pytest.skip(f"{name} is not installed in this environment")
        env = {**os.environ, "PYTHONPATH": SRC}
        completed = subprocess.run(
            [str(script), "1"],
            input=ONE_ORDER,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        assert (completed.returncode, completed.stdout, completed.stderr) == (0, "1 B 1.00\n", "")

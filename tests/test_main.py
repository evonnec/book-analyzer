"""Tests for the program entry point, in process and as a real subprocess."""

import os
import subprocess
import sys
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path

import pytest

from book_analyzer.__main__ import entry

SRC = str(Path(__file__).resolve().parent.parent / "src")


def run_module(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": SRC}
    return subprocess.run(
        [sys.executable, "-m", "book_analyzer", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def stdin_of(text: str) -> TextIOWrapper:
    """A text stream like the real `sys.stdin` (so `reconfigure`, which #9 may call, works)."""
    return TextIOWrapper(BytesIO(text.encode()), encoding="utf-8")


class TestEntryInProcess:
    def test_explicit_argv(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_input_clean: str,
        sample_expected: str,
    ) -> None:
        stdout = StringIO()
        monkeypatch.setattr(sys, "stdin", stdin_of(sample_input_clean))
        monkeypatch.setattr(sys, "stdout", stdout)
        entry(["200"])
        assert stdout.getvalue() == sample_expected

    def test_default_argv_is_sys_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout = StringIO()
        monkeypatch.setattr(sys, "argv", ["book-analyzer", "2"])
        monkeypatch.setattr(sys, "stdin", stdin_of("1 A a S 1.50 2\n"))
        monkeypatch.setattr(sys, "stdout", stdout)
        entry()
        assert stdout.getvalue() == "1 B 3.00\n"

    def test_positive_int_valid(self) -> None:
        from book_analyzer.__main__ import positive_int

        assert positive_int("1") == 1
        assert positive_int("200") == 200

    def test_positive_int_invalid(self) -> None:
        import argparse

        from book_analyzer.__main__ import positive_int

        with pytest.raises(argparse.ArgumentTypeError):
            positive_int("abc")
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int("0")
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int("-5")

    def test_main_usage_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from book_analyzer.__main__ import main

        monkeypatch.setattr(sys, "stderr", StringIO())
        assert main(["abc"]) == 2

    def test_main_keyboard_interrupt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import book_analyzer.__main__ as main_mod

        def raise_sigint(**kwargs: object) -> None:
            raise KeyboardInterrupt()

        monkeypatch.setattr(main_mod, "run", raise_sigint)
        assert main_mod.main(["1"]) == 130

    def test_entry_exits_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stderr", StringIO())
        with pytest.raises(SystemExit) as exc:
            entry(["abc"])
        assert exc.value.code == 2


class TestSubprocess:
    def test_sample(self, sample_input_clean: str, sample_expected: str) -> None:
        result = run_module("200", stdin=sample_input_clean)
        assert result.returncode == 0
        assert result.stdout == sample_expected
        assert result.stderr == ""

    def test_empty_stdin(self) -> None:
        result = run_module("1")
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")

    def test_na_output(self) -> None:
        result = run_module("5", stdin="1 A a S 1.00 1\n")
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")

    def test_warning_is_on_stderr(self) -> None:
        result = run_module("1", stdin="1 A a S 1.00 1\nbad\n")
        assert result.returncode == 0
        assert result.stdout == "1 B 1.00\n"
        assert "warning" in result.stderr.lower()

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["abc"],
            ["1.5"],
            ["0"],
            ["-5"],
            ["+5"],
            ["5_0"],
        ],
    )
    def test_invalid_target_size_is_a_usage_error(self, args: list[str]) -> None:
        result = run_module(*args)
        assert result.returncode == 2
        assert "usage" in result.stderr.lower()
        assert "Traceback" not in result.stderr
        assert result.stdout == ""

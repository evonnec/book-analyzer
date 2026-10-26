"""Ways to run the program under test: in a real subprocess, and in process via `cli.run`."""

import contextlib
import inspect
import os
import select
import subprocess
import sys
from collections.abc import Callable, Mapping
from contextlib import redirect_stderr
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import cast

from book_analyzer import cli

SRC = str(Path(__file__).resolve().parents[2] / "src")


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def warning_lines(self) -> list[str]:
        return [line for line in self.stderr.splitlines() if line.strip()]


def child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": SRC}
    env.update(extra or {})
    return env


def run_subprocess(
    args: list[str],
    stdin: str | bytes = "",
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = 120,
) -> CliResult:
    """Run `python -m book_analyzer ARGS` with `stdin` piped in and capture everything."""
    data = stdin.encode() if isinstance(stdin, str) else stdin
    completed = subprocess.run(
        [sys.executable, "-m", "book_analyzer", *args],
        input=data,
        capture_output=True,
        env=child_env(env),
        timeout=timeout,
        check=False,
    )
    return CliResult(
        completed.returncode, completed.stdout.decode("utf-8"), completed.stderr.decode("utf-8")
    )


def run_in_process(text: str, target_size: int) -> CliResult:
    """Run `book_analyzer.cli.run` on `text`.

    The error stream is passed by keyword if `run` accepts one (its name contains "err" or
    "warn"); otherwise `sys.stderr` is redirected, so the helper works before and after the
    error-handling change.
    """
    output, errors = StringIO(), StringIO()
    kwargs: dict[str, object] = {
        "input_file": StringIO(text),
        "output_file": output,
        "target_size": target_size,
    }
    error_parameter = next(
        (name for name in inspect.signature(cli.run).parameters if "err" in name or "warn" in name),
        None,
    )
    run = cast(Callable[..., None], cli.run)
    if error_parameter is None:
        with redirect_stderr(errors):
            run(**kwargs)
    else:
        run(**kwargs, **{error_parameter: errors})
    return CliResult(0, output.getvalue(), errors.getvalue())


class Child:
    """A running child process with pipes, for tests that interact with it while it runs."""

    def __init__(self, args: list[str], *, code: str | None = None) -> None:
        command = [sys.executable, *(["-c", code] if code else ["-m", "book_analyzer"]), *args]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env(),
        )

    def send(self, text: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(text.encode())
        self.process.stdin.flush()

    def read_line(self, timeout: float) -> str | None:
        """Return one stdout line, "" on EOF, or None if nothing arrived within `timeout`."""
        assert self.process.stdout is not None
        fd = self.process.stdout.fileno()
        line = bytearray()
        while not line.endswith(b"\n"):
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                return None
            chunk = os.read(fd, 1)
            if not chunk:
                break
            line += chunk
        return line.decode()

    def finish(self, timeout: float = 30) -> CliResult:
        """Close stdin, wait for exit and return everything that is left."""
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        with contextlib.suppress(BrokenPipeError):  # the child may already have exited
            self.process.stdin.close()
        returncode = self.process.wait(timeout=timeout)
        result = CliResult(
            returncode,
            self.process.stdout.read().decode(),
            self.process.stderr.read().decode(),
        )
        self.process.stdout.close()
        self.process.stderr.close()
        return result

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                with contextlib.suppress(BrokenPipeError):
                    stream.close()

"""Ways to run the program under test: in a real subprocess, and in process via `cli.run`."""

import contextlib
import os
import re
import select
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from system_api import call_run

SRC = str(Path(__file__).resolve().parents[2] / "src")
LINE_NUMBER = re.compile(r"\bline [0-9]+\b", re.IGNORECASE)


def mentions_line(warning: str, number: int) -> bool:
    """Whether `warning` names line `number` (and not, say, line 40 for line 4)."""
    return re.search(rf"\bline {number}\b", warning, re.IGNORECASE) is not None


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def warning_lines(self) -> list[str]:
        """The stderr lines that name an input line number: the per-message warnings (#9).

        A summary line without a line number (#14 proposes one at EOF) is not counted. A
        traceback is (its frames name source lines), so a crash still breaks a warning count.
        """
        return [line for line in self.stderr.splitlines() if LINE_NUMBER.search(line)]


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
    """Run `book_analyzer.cli.run` on `text`, before or after #9 adds its error stream."""
    output, errors = StringIO(), StringIO()
    call_run(StringIO(text), output, errors, target_size)
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

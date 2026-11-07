"""Run the book analyzer: `python -m book_analyzer TARGET_SIZE < messages`."""

import argparse
import io
import os
import sys
from collections.abc import Sequence

from book_analyzer.cli import run


def positive_int(value: str) -> int:
    """Parse a strictly positive integer composed of ASCII digits only."""
    if not value.isascii() or not value.isdigit():
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid positive integer")
    val = int(value)
    if val < 1:
        raise argparse.ArgumentTypeError(f"{val} must be at least 1")
    return val


def main(argv: Sequence[str] | None = None) -> int:
    """Parse TARGET_SIZE and run the book analyzer on stdin.

    Returns exit code (0 on success, 2 on usage error, 141 on broken pipe, 130 on SIGINT).
    """
    args_list = sys.argv[1:] if argv is None else list(argv)

    if isinstance(sys.stdin, io.TextIOWrapper):
        # Undecodable bytes become per-line warnings instead of aborting the run.
        sys.stdin.reconfigure(errors="surrogateescape")
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(newline="\n")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(newline="\n")

    parser = argparse.ArgumentParser(
        prog="book-analyzer",
        description="Replay a limit order book and track expense/income for TARGET_SIZE shares.",
    )
    parser.add_argument(
        "TARGET_SIZE",
        type=positive_int,
        help="positive integer number of shares to track",
    )

    try:
        parsed = parser.parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    try:
        run(
            input_file=sys.stdin,
            output_file=sys.stdout,
            error_file=sys.stderr,
            target_size=parsed.TARGET_SIZE,
        )
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
        except OSError, io.UnsupportedOperation, AttributeError:
            pass
        return 141
    except KeyboardInterrupt:
        return 130

    return 0


def entry(argv: Sequence[str] | None = None) -> None:
    """Parse the target size from argv (default: sys.argv[1:]) and process stdin."""
    code = main(argv)
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    sys.exit(main())

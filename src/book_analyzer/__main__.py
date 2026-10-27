"""Run the book analyzer: `python -m book_analyzer TARGET_SIZE < messages`."""

import io
import sys
from collections.abc import Sequence

from book_analyzer.cli import run


def entry(argv: Sequence[str] | None = None) -> None:
    """Parse the target size from argv (default: sys.argv[1:]) and process stdin."""
    args = sys.argv[1:] if argv is None else argv
    if isinstance(sys.stdin, io.TextIOWrapper):
        # Undecodable bytes become per-line warnings instead of aborting the run.
        sys.stdin.reconfigure(errors="surrogateescape")
    run(
        input_file=sys.stdin,
        output_file=sys.stdout,
        error_file=sys.stderr,
        target_size=int(args[0]),
    )


if __name__ == "__main__":
    entry()

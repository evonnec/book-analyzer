"""Opt-in test against reference data kept outside the repository.

Set BOOK_ANALYZER_DATA to a directory holding `book_analyzer.in` and
`book_analyzer.out.{1,200,10000}`. Set BOOK_ANALYZER_DATA_LINES=N to use only the first N input
lines (extended to the end of that line's timestamp); the default is the whole file, which the
current implementation needs hours to process.
"""

import os
from io import StringIO
from pathlib import Path

import pytest

from book_analyzer.cli import run

DATA_DIR = os.environ.get("BOOK_ANALYZER_DATA")
LINE_LIMIT = os.environ.get("BOOK_ANALYZER_DATA_LINES")
INPUT_NAME = "book_analyzer.in"
TARGET_SIZES = (1, 200, 10000)


def _data_dir() -> Path | None:
    if not DATA_DIR:
        return None
    path = Path(DATA_DIR)
    names = [INPUT_NAME, *(f"book_analyzer.out.{size}" for size in TARGET_SIZES)]
    return path if all((path / name).is_file() for name in names) else None


pytestmark = pytest.mark.skipif(
    _data_dir() is None,
    reason="set BOOK_ANALYZER_DATA to a directory with the reference input and outputs",
)


def timestamp_of(line: str) -> int:
    return int(line.split(" ", 1)[0])


def read_input(path: Path, limit: int | None) -> tuple[list[str], int | None]:
    """Return the first `limit` lines plus the rest of the last timestamp, and that timestamp."""
    lines: list[str] = []
    last_timestamp: int | None = None
    with path.open(encoding="ascii") as handle:
        for line in handle:
            if limit is not None and len(lines) >= limit and timestamp_of(line) != last_timestamp:
                break
            lines.append(line)
            last_timestamp = timestamp_of(line)
    return lines, last_timestamp


@pytest.mark.parametrize("target_size", TARGET_SIZES)
def test_matches_reference_output(target_size: int) -> None:
    data = _data_dir()
    assert data is not None
    limit = int(LINE_LIMIT) if LINE_LIMIT else None
    lines, last_timestamp = read_input(data / INPUT_NAME, limit)
    expected = [
        line
        for line in (data / f"book_analyzer.out.{target_size}")
        .read_text(encoding="ascii")
        .splitlines(keepends=True)
        if last_timestamp is None or timestamp_of(line) <= last_timestamp
    ]
    output = StringIO()
    run(input_file=StringIO("".join(lines)), output_file=output, target_size=target_size)
    assert output.getvalue().splitlines(keepends=True) == expected

"""Command line layer: parse the message log from a stream and print the core's updates."""

from typing import TextIO

from book_analyzer.book import AddMessage, Book, Message, ReduceMessage, Side, Update

__all__ = ["format_update", "parse_line", "run"]


def parse_line(line: str) -> Message | None:
    """Parse one log line, returning None when it does not have 4 or 6 fields."""
    match line.strip().split(" "):
        case [timestamp, _, order_id, size]:
            return ReduceMessage(timestamp=timestamp, order_id=order_id, size=int(size))
        case [timestamp, _, order_id, side, price, size]:
            return AddMessage(
                timestamp=timestamp,
                order_id=order_id,
                price=float(price),
                side=Side(side),
                size=int(size),
            )
        case _:
            return None


def format_update(update: Update) -> str:
    """Format an update as `timestamp side total` with a trailing newline."""
    total = "NA" if update.total is None else f"{update.total:.2f}"
    return f"{update.timestamp} {update.side} {total}\n"


def run(input_file: TextIO, output_file: TextIO, target_size: int) -> None:
    """Read messages from input_file and write changed totals to output_file."""
    book = Book(target_size=target_size)
    for line_number, line in enumerate(input_file.readlines(), start=1):
        message = parse_line(line)
        if message is None:
            output_file.write(
                f"Warning: Invalid line (line {line_number}), see documentation for format\n"
            )
            continue
        for update in book.apply(message):
            output_file.write(format_update(update))

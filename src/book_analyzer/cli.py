"""Command line layer: parse the message log from a stream and print the core's updates."""

import re
from typing import TextIO

from book_analyzer.book import (
    PRICE_DECIMALS,
    PRICE_SCALE,
    AddMessage,
    Book,
    Message,
    ReduceMessage,
    Side,
    Update,
    cents,
)

__all__ = ["format_update", "parse_line", "parse_price", "run"]

_PRICE = re.compile(rf"([0-9]+)(?:\.([0-9]{{1,{PRICE_DECIMALS}}}))?")


def parse_price(text: str) -> int:
    """Parse an ASCII decimal price exactly into integer price units (never via float)."""
    match = _PRICE.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid price {text!r}")
    whole, fraction = match.group(1), match.group(2) or ""
    return int(whole) * PRICE_SCALE + int(fraction.ljust(PRICE_DECIMALS, "0"))


def parse_line(line: str) -> Message | None:
    """Parse one log line, returning None when it does not have 4 or 6 fields."""
    match line.strip().split(" "):
        case [timestamp, _, order_id, size]:
            return ReduceMessage(timestamp=timestamp, order_id=order_id, size=int(size))
        case [timestamp, _, order_id, side, price, size]:
            return AddMessage(
                timestamp=timestamp,
                order_id=order_id,
                price=parse_price(price),
                side=Side(side),
                size=int(size),
            )
        case _:
            return None


def format_total(total: int | None) -> str:
    """`NA`, or the total rounded half up to cents with exactly two decimals."""
    if total is None:
        return "NA"
    rounded = cents(total)
    return f"{rounded // 100}.{rounded % 100:02d}"


def format_update(update: Update) -> str:
    """Format an update as `timestamp side total` with a trailing newline."""
    return f"{update.timestamp} {update.side} {format_total(update.total)}\n"


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

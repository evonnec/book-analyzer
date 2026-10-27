"""Command line layer: parse the message log from a stream and print the core's updates."""

import re
from typing import TextIO

from book_analyzer.book import (
    PRICE_DECIMALS,
    PRICE_SCALE,
    AddMessage,
    Book,
    Message,
    MessageError,
    ReduceMessage,
    Side,
    Update,
    cents,
)

__all__ = ["MessageError", "format_update", "parse_line", "parse_price", "run"]

_DIGITS = re.compile(r"[0-9]+")
_PRICE = re.compile(rf"([0-9]+)(?:\.([0-9]{{1,{PRICE_DECIMALS}}}))?")
_BOM = "\ufeff"


def parse_price(text: str) -> int:
    """Parse an ASCII decimal price exactly into integer price units (never via float)."""
    match = _PRICE.fullmatch(text)
    if match is None:
        raise MessageError(f"invalid price {text!r}")
    whole, fraction = match.group(1), match.group(2) or ""
    price = int(whole) * PRICE_SCALE + int(fraction.ljust(PRICE_DECIMALS, "0"))
    if price <= 0:
        raise MessageError(f"price must be positive: {text!r}")
    return price


def _size(text: str) -> int:
    if not _DIGITS.fullmatch(text) or int(text) <= 0:
        raise MessageError(f"invalid size {text!r}")
    return int(text)


def parse_line(line: str) -> Message:
    """Parse one log line; raise MessageError when it is not a valid message."""
    fields = line.split()
    if not fields:
        raise MessageError("blank line")
    if not _DIGITS.fullmatch(fields[0]):
        raise MessageError(f"invalid timestamp {fields[0]!r}")
    match fields:
        case [timestamp, "R", order_id, size]:
            return ReduceMessage(timestamp=timestamp, order_id=order_id, size=_size(size))
        case [timestamp, "A", order_id, side, price, size]:
            if side not in ("B", "S"):
                raise MessageError(f"invalid side {side!r}")
            return AddMessage(
                timestamp=timestamp,
                order_id=order_id,
                price=parse_price(price),
                side=Side(side),
                size=_size(size),
            )
        case _:
            raise MessageError("expected `ts A id side price size` or `ts R id size`")


def format_total(total: int | None) -> str:
    """`NA`, or the total rounded half up to cents with exactly two decimals."""
    if total is None:
        return "NA"
    rounded = cents(total)
    return f"{rounded // 100}.{rounded % 100:02d}"


def format_update(update: Update) -> str:
    """Format an update as `timestamp side total` with a trailing newline."""
    return f"{update.timestamp} {update.side} {format_total(update.total)}\n"


def run(input_file: TextIO, output_file: TextIO, error_file: TextIO, target_size: int) -> None:
    """Process input_file: changed totals go to output_file, warnings to error_file."""
    book = Book(target_size=target_size)
    for line_number, line in enumerate(input_file.readlines(), start=1):
        text = line.removeprefix(_BOM) if line_number == 1 else line
        try:
            updates = book.apply(parse_line(text))
        except MessageError as error:
            error_file.write(f"warning: line {line_number}: {error}: {line.rstrip(chr(10))!r}\n")
            continue
        for update in updates:
            output_file.write(format_update(update))

"""An independent, brute-force reference implementation of the specification.

It shares no code with `book_analyzer`. Money is exact (`decimal.Decimal`), the book is a plain
dict that is fully re-sorted for every total, and a message is validated against a strict ASCII
grammar before it touches any state. It is deliberately slow and obviously correct.

Policy implemented (the one the error-handling issue proposes):
  * fields are separated by runs of spaces or tabs; a trailing CR and a BOM on line 1 are ignored;
  * `A` takes exactly 6 fields, `R` exactly 4; timestamp, size are `[0-9]+`; size > 0;
  * side is `B` or `S`; price is `[0-9]+(\\.[0-9]+)?` and > 0;
  * a reduce of an unknown (or already removed) id and an add of a live id are rejected;
  * a reduce >= the remaining size removes the order; ids can be re-used after removal;
  * a total "changes" when its printed (rounded half up to 2 places) value differs.
Rejected messages produce one warning (their 1-based line number) and change nothing.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

BOM = chr(0xFEFF)  # a UTF-8 byte order mark, decoded
DIGITS = re.compile(r"[0-9]+")
PRICE = re.compile(r"[0-9]+(\.[0-9]+)?")


@dataclass
class Held:
    side: str
    price: Decimal
    size: int


@dataclass(frozen=True)
class OracleResult:
    lines: list[str]  # result lines, without newlines
    rejected: list[int]  # 1-based line numbers of rejected messages

    @property
    def stdout(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


def _positive_int(token: str) -> int | None:
    if DIGITS.fullmatch(token) and int(token) > 0:
        return int(token)
    return None


def _format(total: Decimal | None) -> str:
    if total is None:
        return "NA"
    with localcontext() as context:
        context.prec = 200
        return format(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _fill(orders: list[tuple[Decimal, int]], target: int, *, highest_first: bool) -> Decimal | None:
    if sum(size for _, size in orders) < target:
        return None
    remaining = target
    total = Decimal(0)
    for price, size in sorted(orders, key=lambda order: order[0], reverse=highest_first):
        take = min(size, remaining)
        total += price * take
        remaining -= take
        if remaining == 0:
            break
    return total


def oracle(text: str, target: int) -> OracleResult:
    """Run the specification over `text` for `target` shares."""
    raw_lines = text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    book: dict[str, Held] = {}
    printed = {"B": "NA", "S": "NA"}
    output: list[str] = []
    rejected: list[int] = []
    for number, raw in enumerate(raw_lines, start=1):
        line = raw.removeprefix(BOM) if number == 1 else raw
        fields = re.split(r"[ \t]+", line.strip(" \t\r"))
        timestamp = fields[0]
        if not DIGITS.fullmatch(timestamp):
            rejected.append(number)
            continue
        if len(fields) == 6 and fields[1] == "A":
            _, _, order_id, side, price_text, size_text = fields
            size = _positive_int(size_text)
            if (
                side not in ("B", "S")
                or size is None
                or not PRICE.fullmatch(price_text)
                or Decimal(price_text) <= 0
                or order_id in book
            ):
                rejected.append(number)
                continue
            book[order_id] = Held(side, Decimal(price_text), size)
        elif len(fields) == 4 and fields[1] == "R":
            _, _, order_id, size_text = fields
            size = _positive_int(size_text)
            if size is None or order_id not in book:
                rejected.append(number)
                continue
            order = book[order_id]
            if size >= order.size:
                del book[order_id]
            else:
                order.size -= size
        else:
            rejected.append(number)
            continue
        output.extend(_changes(book, target, printed, timestamp))
    return OracleResult(lines=output, rejected=rejected)


def _changes(
    book: dict[str, Held], target: int, printed: dict[str, str], timestamp: str
) -> list[str]:
    asks: list[tuple[Decimal, int]] = []
    bids: list[tuple[Decimal, int]] = []
    for held in book.values():
        (asks if held.side == "S" else bids).append((held.price, held.size))
    now = {
        "B": _format(_fill(asks, target, highest_first=False)),
        "S": _format(_fill(bids, target, highest_first=True)),
    }
    lines = []
    for side in ("B", "S"):
        if now[side] != printed[side]:
            printed[side] = now[side]
            lines.append(f"{timestamp} {side} {now[side]}")
    return lines

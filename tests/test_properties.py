"""Property tests against a brute-force oracle written in integer cents.

Prices are generated as whole cents and compared in integer cents, read back from how the
total prints. The stream property requires exact equality: no repeated lines.
"""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from system_api import price, shown
from system_run import run_in_process

from book_analyzer import Book, Side, Total

settings.register_profile("default", max_examples=100, deadline=None)
settings.load_profile("default")

cent_prices = st.integers(min_value=1, max_value=2000)
sizes = st.integers(min_value=1, max_value=10)
targets = st.integers(min_value=1, max_value=40)
sides = st.sampled_from([Side.BUY, Side.SELL])

type Orders = dict[str, tuple[Side, int, int]]  # id -> (side, price in cents, size)


def oracle(orders: Orders, side: Side, target: int) -> int | None:
    """Cents to buy (asks, ascending) or earned selling (bids, descending), None if short."""
    levels = sorted(
        (cents, size) for order_side, cents, size in orders.values() if order_side == side
    )
    if side == Side.BUY:
        levels.reverse()
    remaining, total = target, 0
    for cents, size in levels:
        take = min(size, remaining)
        total += take * cents
        remaining -= take
    return None if remaining else total


def book_cents(total: Total) -> int | None:
    """A book total in integer cents, read from how it prints."""
    text = shown(total)
    return None if text == "NA" else int(text.replace(".", ""))


def decimal_text(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def build(orders: Orders, target: int) -> Book:
    book = Book(target_size=target)
    for order_id, (side, cents, size) in orders.items():
        book.create_add_order(
            order_id=order_id, price=price(decimal_text(cents)), side=side, size=size
        )
    return book


@st.composite
def static_books(draw: st.DrawFn) -> Orders:
    entries = draw(st.lists(st.tuples(sides, cent_prices, sizes), max_size=12))
    return {f"o{i}": entry for i, entry in enumerate(entries)}


@given(static_books(), targets)
def test_totals_match_oracle_and_na_iff_short(orders: Orders, target: int) -> None:
    book = build(orders, target)
    ask_shares = sum(size for side, _, size in orders.values() if side == Side.SELL)
    bid_shares = sum(size for side, _, size in orders.values() if side == Side.BUY)
    expense, income = book.get_expense(), book.get_income()
    assert (expense is None) == (ask_shares < target)
    assert (income is None) == (bid_shares < target)
    assert book_cents(expense) == oracle(orders, Side.SELL, target)
    assert book_cents(income) == oracle(orders, Side.BUY, target)


@given(static_books(), targets, targets)
def test_totals_are_non_decreasing_in_target_size(orders: Orders, first: int, second: int) -> None:
    small, large = sorted((first, second))
    for read in (Book.get_expense, Book.get_income):
        low = book_cents(read(build(orders, small)))
        high = book_cents(read(build(orders, large)))
        if high is not None:
            assert low is not None
            assert low <= high  # prices are positive, so more shares never cost less


@given(static_books(), targets)
def test_uncrossed_book_income_is_at_most_expense(orders: Orders, target: int) -> None:
    asks = [cents for side, cents, _ in orders.values() if side == Side.SELL]
    bids = [cents for side, cents, _ in orders.values() if side == Side.BUY]
    if asks and bids and max(bids) >= min(asks):
        return  # crossed book: selling can beat buying, so the property does not apply
    book = build(orders, target)
    expense, income = book_cents(book.get_expense()), book_cents(book.get_income())
    if expense is not None and income is not None:
        assert income <= expense


@st.composite
def message_streams(draw: st.DrawFn) -> list[str]:
    """Valid log lines only: unique ids, reduces target live orders by at most their size."""
    live: dict[str, int] = {}
    lines: list[str] = []
    for step in range(draw(st.integers(min_value=0, max_value=30))):
        timestamp = str(1000 + step)
        reduce_next: bool = draw(st.booleans())
        if live and reduce_next:
            order_id = draw(st.sampled_from(sorted(live)))
            size = draw(st.integers(min_value=1, max_value=live[order_id]))
            lines.append(f"{timestamp} R {order_id} {size}")
            live[order_id] -= size
            if live[order_id] == 0:
                del live[order_id]
        else:
            order_id = f"id{step}"
            size = draw(sizes)
            cents = draw(st.integers(min_value=1, max_value=12))  # few prices, many ties
            side = draw(sides)
            lines.append(f"{timestamp} A {order_id} {side} {decimal_text(cents)} {size}")
            live[order_id] = size
    return lines


def format_cents(total: int | None) -> str:
    return "NA" if total is None else f"{Decimal(total).scaleb(-2):.2f}"


@given(message_streams(), targets)
def test_stream_output_matches_oracle(lines: list[str], target: int) -> None:
    orders: Orders = {}
    last: dict[Side, int | None] = {Side.BUY: None, Side.SELL: None}
    expected: list[str] = []
    for line in lines:
        match line.split():
            case [timestamp, "A", order_id, side, price_text, size]:
                cents = int(price_text.replace(".", ""))
                orders[order_id] = (Side(side), cents, int(size))
            case [timestamp, "R", order_id, size]:
                book_side, cents, remaining = orders[order_id]
                if int(size) >= remaining:
                    del orders[order_id]
                else:
                    orders[order_id] = (book_side, cents, remaining - int(size))
            case _:  # pragma: no cover - message_streams only makes valid lines
                raise AssertionError(line)
        # Update.side BUY reports the expense (asks), SELL the income (bids).
        for report, book_side in ((Side.BUY, Side.SELL), (Side.SELL, Side.BUY)):
            new_total = oracle(orders, book_side, target)
            if new_total != last[report]:
                last[report] = new_total
                expected.append(f"{timestamp} {report} {format_cents(new_total)}")

    result = run_in_process("".join(f"{line}\n" for line in lines), target)
    assert result.stderr == ""

    assert result.stdout.splitlines() == expected

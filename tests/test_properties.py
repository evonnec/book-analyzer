"""Property tests against a brute-force oracle written in integer cents.

Prices are generated as whole cents and compared in integer cents (the float total is rounded to
the nearest cent), which is safe from float noise. The float defects are covered by the
explicit xfail tests in test_cli.py; the stream property below tolerates their one visible
symptom, repeated identical lines, and says so.
"""

from decimal import Decimal
from io import StringIO

from hypothesis import given, settings
from hypothesis import strategies as st

from book_analyzer import AddMessage, Book, Message, ReduceMessage, Side
from book_analyzer.cli import run

settings.register_profile("default", max_examples=100, deadline=None)
settings.load_profile("default")

cents = st.integers(min_value=1, max_value=2000)
sizes = st.integers(min_value=1, max_value=10)
targets = st.integers(min_value=1, max_value=40)
sides = st.sampled_from([Side.BUY, Side.SELL])

type Orders = dict[str, tuple[Side, int, int]]  # id -> (side, price in cents, size)


def oracle(orders: Orders, side: Side, target: int) -> int | None:
    """Cents to buy (asks, ascending) or earned selling (bids, descending), None if short."""
    levels = sorted(
        (price, size) for order_side, price, size in orders.values() if order_side == side
    )
    if side == Side.BUY:
        levels.reverse()
    remaining, total = target, 0
    for price, size in levels:
        take = min(size, remaining)
        total += take * price
        remaining -= take
    return None if remaining else total


def book_cents(total: float | None) -> int | None:
    return None if total is None else round(total * 100)


def build(orders: Orders, target: int) -> Book:
    book = Book(target_size=target)
    for order_id, (side, price, size) in orders.items():
        book.create_add_order(order_id=order_id, price=price / 100, side=side, size=size)
    return book


@st.composite
def static_books(draw: st.DrawFn) -> Orders:
    entries = draw(st.lists(st.tuples(sides, cents, sizes), max_size=12))
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
    asks = [price for side, price, _ in orders.values() if side == Side.SELL]
    bids = [price for side, price, _ in orders.values() if side == Side.BUY]
    if asks and bids and max(bids) >= min(asks):
        return  # crossed book: selling can beat buying, so the property does not apply
    book = build(orders, target)
    expense, income = book_cents(book.get_expense()), book_cents(book.get_income())
    if expense is not None and income is not None:
        assert income <= expense


@st.composite
def message_streams(draw: st.DrawFn) -> list[Message]:
    """Valid messages only: unique ids, reduces target live orders by at most their size."""
    live: dict[str, int] = {}
    messages: list[Message] = []
    for step in range(draw(st.integers(min_value=0, max_value=30))):
        timestamp = str(1000 + step)
        reduce_next: bool = draw(st.booleans())
        if live and reduce_next:
            order_id = draw(st.sampled_from(sorted(live)))
            size = draw(st.integers(min_value=1, max_value=live[order_id]))
            messages.append(ReduceMessage(timestamp, order_id, size))
            live[order_id] -= size
            if live[order_id] == 0:
                del live[order_id]
        else:
            order_id = f"id{step}"
            size = draw(sizes)
            price = draw(st.integers(min_value=1, max_value=12))  # few prices, many ties
            messages.append(AddMessage(timestamp, order_id, draw(sides), price / 100, size))
            live[order_id] = size
    return messages


def format_cents(total: int | None) -> str:
    return "NA" if total is None else f"{Decimal(total).scaleb(-2):.2f}"


def render(message: Message) -> str:
    match message:
        case AddMessage():
            return (
                f"{message.timestamp} A {message.order_id} {message.side} "
                f"{message.price:.2f} {message.size}"
            )
        case ReduceMessage():
            return f"{message.timestamp} R {message.order_id} {message.size}"


@given(message_streams(), targets)
def test_stream_output_matches_oracle(messages: list[Message], target: int) -> None:
    orders: Orders = {}
    last: dict[Side, int | None] = {Side.BUY: None, Side.SELL: None}
    expected: list[str] = []
    for message in messages:
        match message:
            case AddMessage(order_id=order_id, side=side, price=price, size=size):
                orders[order_id] = (side, round(price * 100), size)
            case ReduceMessage(order_id=order_id, size=size):
                side, price, remaining = orders[order_id]
                if size >= remaining:
                    del orders[order_id]
                else:
                    orders[order_id] = (side, price, remaining - size)
        # Update.side BUY reports the expense (asks), SELL the income (bids).
        for report, book_side in ((Side.BUY, Side.SELL), (Side.SELL, Side.BUY)):
            new_total = oracle(orders, book_side, target)
            if new_total != last[report]:
                last[report] = new_total
                expected.append(f"{message.timestamp} {report} {format_cents(new_total)}")

    output = StringIO()
    log = "".join(render(message) + "\n" for message in messages)
    run(input_file=StringIO(log), output_file=output, target_size=target)

    # The float implementation may repeat a line when a sum changes only by noise (known
    # defect), so drop a line that repeats the previous line of the same side before comparing.
    actual: list[str] = []
    previous: dict[str, str] = {}
    for line in output.getvalue().splitlines():
        _, line_side, printed = line.split(" ")
        if previous.get(line_side) != printed:
            actual.append(line)
        previous[line_side] = printed
    assert actual == expected

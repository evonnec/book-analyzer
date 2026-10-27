"""Deterministic complexity checks: count objects and work instead of timing them.

One generated market with about 100 live orders and thousands of messages (so dead orders
would dominate) is replayed through `Book.apply`, once, with two counters:

  * the objects reachable from the `Book` afterwards. This does not depend on how the book is
    built (dicts, price levels, sorted lists), so it survives the #10 rewrite: a book that only
    holds live orders stays within a few objects per live order, one that keeps every order
    ever added grows with the log.
  * the calls to `sorted` made from `book_analyzer.book` (a module global shadows the builtin
    for code in that module), and the elements they sort. If an implementation stops calling
    `sorted` (as the #10 price-level book does) the counts are zero and those checks pass
    trivially: they catch per-message re-sorting while it exists, nothing more.
"""

import builtins
import gc
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import BuiltinFunctionType, FunctionType, ModuleType
from typing import Any

import pytest
from system_cases import xfail
from system_gen import generate_market

from book_analyzer import Book
from book_analyzer import book as book_module
from book_analyzer.cli import parse_line

# Not scaled by BOOK_ANALYZER_SYSTEM_SCALE: dead orders need this many messages to pile up.
MESSAGES = 6000
TARGET = 200
# Sorted elements per message may be at most this many times the peak number of live orders.
# A book that drops dead orders sorts about 2-4 live orders-worth per message (<= ~2 here);
# one that keeps every order ever added grows with the log: ~12 at 6000 messages.
WORK_FACTOR = 5
# Objects reachable from the book per peak live order. Measured: about 3 (dict of orders) to 4
# (price-level book) when dead orders are dropped, about 48 at 6000 messages when they are not.
OBJECTS_PER_LIVE_ORDER = 10
SHARED = (type, ModuleType, FunctionType, BuiltinFunctionType)  # not owned by the book


@dataclass(frozen=True)
class Replay:
    max_live: int
    updates: int
    sort_calls: int
    sorted_elements: int
    reachable_objects: int


def reachable_objects(root: object) -> int:
    """How many objects `root` keeps alive through references (classes, modules, functions
    excluded)."""
    seen = {id(root)}
    stack = [root]
    while stack:
        for referent in gc.get_referents(stack.pop()):
            if not isinstance(referent, SHARED) and id(referent) not in seen:
                seen.add(id(referent))
                stack.append(referent)
    return len(seen)


@pytest.fixture(scope="module")
def replay() -> Replay:
    market = generate_market(5, MESSAGES, live_target=100)
    calls = elements = 0

    def counting_sorted(iterable: Iterable[Any], **kwargs: Any) -> list[Any]:
        nonlocal calls, elements
        items = list(iterable)
        calls += 1
        elements += len(items)
        sort: Callable[..., list[Any]] = builtins.sorted
        return sort(items, **kwargs)

    book = Book(target_size=TARGET)
    updates = 0
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(book_module, "sorted", counting_sorted, raising=False)
        for line in market.lines:
            message = parse_line(line)
            assert message is not None
            updates += len(book.apply(message))
    return Replay(market.max_live, updates, calls, elements, reachable_objects(book))


def test_replay_runs(replay: Replay) -> None:
    """Not an xfail, so a broken replay shows up as an error instead of an expected failure."""
    assert replay.updates > 0
    assert 50 <= replay.max_live <= 200


def test_book_holds_only_live_orders(replay: Replay) -> None:
    assert replay.reachable_objects <= OBJECTS_PER_LIVE_ORDER * replay.max_live


def test_work_per_message_is_bounded_by_live_orders(replay: Replay) -> None:
    assert replay.sorted_elements <= WORK_FACTOR * MESSAGES * replay.max_live


@xfail("#10", "every message recomputes both sides, twice (4 sorts per message)")
def test_only_the_touched_side_is_recomputed(replay: Replay) -> None:
    assert replay.sort_calls <= 2 * MESSAGES

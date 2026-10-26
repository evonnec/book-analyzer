"""Deterministic complexity checks: count the work instead of timing it.

`book_analyzer.book.sorted` is replaced with a counting wrapper (a module global shadows the
builtin for code in that module). If a future implementation stops calling `sorted` the counts
are zero and the tests pass, which is fine: they only fail on too much work.
"""

import builtins
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import pytest
from system_cases import scaled, xfail
from system_gen import Market, generate_market
from system_run import run_in_process

from book_analyzer import book as book_module

MESSAGES = scaled(6000)
TARGET = 200
# Elements sorted per message may be at most this many times the peak number of live orders.
# A book that drops dead orders sorts about 2-4 live orders-worth per message (<= ~2 here);
# one that keeps every order ever added grows with the log: ~12 at 6000 messages.
WORK_FACTOR = 5


@dataclass
class SortCounter:
    calls: int = 0
    elements: int = 0


@pytest.fixture
def sort_counter(monkeypatch: pytest.MonkeyPatch) -> SortCounter:
    counter = SortCounter()

    def counting_sorted(iterable: Iterable[Any], **kwargs: Any) -> list[Any]:
        items = list(iterable)
        counter.calls += 1
        counter.elements += len(items)
        sort: Callable[..., list[Any]] = builtins.sorted
        return sort(items, **kwargs)

    monkeypatch.setattr(book_module, "sorted", counting_sorted, raising=False)
    return counter


@pytest.fixture(scope="module")
def small_book_market() -> Market:
    """A market with about 100 live orders and thousands of messages (so dead orders dominate)."""
    return generate_market(5, MESSAGES, live_target=100)


@xfail("#7", "fully reduced orders stay in the book, so every message sorts the whole history")
def test_work_per_message_is_bounded_by_live_orders(
    sort_counter: SortCounter, small_book_market: Market
) -> None:
    run_in_process(small_book_market.text, TARGET)
    budget = WORK_FACTOR * MESSAGES * small_book_market.max_live
    assert sort_counter.elements <= budget


@xfail("#10", "every message recomputes both sides, twice (4 sorts per message)")
def test_only_the_touched_side_is_recomputed(
    sort_counter: SortCounter, small_book_market: Market
) -> None:
    run_in_process(small_book_market.text, TARGET)
    assert sort_counter.calls <= 2 * MESSAGES

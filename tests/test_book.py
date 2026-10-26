"""Unit tests for the core order book (no I/O)."""

from collections.abc import Iterator

import pytest

from book_analyzer import AddMessage, Book, ReduceMessage, Side, Update

BUY, SELL = Side.BUY, Side.SELL

type OrderSpec = tuple[str, Side, float, int]


def make_book(target_size: int, *orders: OrderSpec) -> Book:
    book = Book(target_size=target_size)
    for order_id, side, price, size in orders:
        book.create_add_order(order_id=order_id, price=price, side=side, size=size)
    return book


class TestEmptyAndOneSided:
    def test_empty_book_is_na_on_both_sides(self) -> None:
        book = Book(target_size=1)
        assert book.get_expense() is None
        assert book.get_income() is None

    def test_bids_do_not_fill_expense(self) -> None:
        book = make_book(1, ("a", BUY, 1, 5))
        assert book.get_expense() is None
        assert book.get_income() == 1

    def test_asks_do_not_fill_income(self) -> None:
        book = make_book(1, ("a", SELL, 3, 5))
        assert book.get_income() is None
        assert book.get_expense() == 3

    def test_not_enough_shares_is_na(self) -> None:
        book = make_book(10, ("a", SELL, 1, 4), ("b", SELL, 2, 5))
        assert book.get_expense() is None


class TestFilling:
    def test_exact_target_fill_single_order(self) -> None:
        assert make_book(2, ("a", SELL, 3, 2)).get_expense() == 6

    def test_exact_target_fill_across_orders(self) -> None:
        book = make_book(3, ("a", SELL, 1, 1), ("b", SELL, 2, 2))
        assert book.get_expense() == 5

    def test_partial_fill_of_last_level(self) -> None:
        book = make_book(3, ("a", SELL, 1, 1), ("b", SELL, 2, 5))
        assert book.get_expense() == 5

    def test_orders_beyond_target_are_ignored(self) -> None:
        book = make_book(2, ("a", SELL, 1, 2), ("b", SELL, 100, 50))
        assert book.get_expense() == 2

    def test_ties_at_same_price(self) -> None:
        book = make_book(3, ("a", SELL, 1.5, 2), ("b", SELL, 1.5, 2))
        assert book.get_expense() == 4.5

    def test_ties_at_same_price_on_bids(self) -> None:
        book = make_book(3, ("a", BUY, 2, 1), ("b", BUY, 2, 1), ("c", BUY, 2, 5))
        assert book.get_income() == 6

    def test_asks_are_taken_lowest_price_first(self) -> None:
        book = make_book(
            5,
            ("a", SELL, 1.50, 2),
            ("b", SELL, 2.50, 2),
            ("c", SELL, 2.25, 2),
            ("d", SELL, 1.75, 2),
        )
        # 2 @ 1.50 + 2 @ 1.75 + 1 @ 2.25
        assert book.get_expense() == 8.75

    def test_bids_are_taken_highest_price_first(self) -> None:
        book = make_book(
            5,
            ("a", BUY, 10, 2),
            ("b", BUY, 12, 2),
            ("c", BUY, 11, 2),
            ("d", BUY, 9, 2),
        )
        # 2 @ 12 + 2 @ 11 + 1 @ 10
        assert book.get_income() == 56

    def test_target_size_one(self) -> None:
        book = make_book(
            1, ("a", SELL, 4, 9), ("b", SELL, 3, 1), ("c", BUY, 2, 1), ("d", BUY, 1, 9)
        )
        assert book.get_expense() == 3
        assert book.get_income() == 2

    def test_large_target_size(self) -> None:
        book = make_book(
            1_000_000,
            ("a", SELL, 2, 600_000),
            ("b", SELL, 3, 600_000),
            ("c", BUY, 1, 1_000_000),
        )
        assert book.get_expense() == 2 * 600_000 + 3 * 400_000
        assert book.get_income() == 1_000_000

    def test_target_larger_than_book_is_na(self) -> None:
        book = make_book(1_000_001, ("a", SELL, 2, 1_000_000), ("b", BUY, 1, 1_000_000))
        assert book.get_expense() is None
        assert book.get_income() is None


class TestReduce:
    def test_partial_reduce_ask(self) -> None:
        book = make_book(1, ("a", SELL, 1, 2))
        book.create_reduce_order(order_id="a", size=1)
        assert book.get_expense() == 1

    def test_partial_reduce_bid(self) -> None:
        book = make_book(2, ("a", BUY, 5, 3))
        book.create_reduce_order(order_id="a", size=1)
        assert book.get_income() == 10
        book.create_reduce_order(order_id="a", size=1)
        assert book.get_income() is None

    def test_partial_reduce_changes_fill(self) -> None:
        book = make_book(3, ("a", SELL, 1, 2), ("b", SELL, 2, 5))
        assert book.get_expense() == 4
        book.create_reduce_order(order_id="a", size=1)
        assert book.get_expense() == 5

    def test_reduce_to_zero_removes_order(self) -> None:
        book = make_book(1, ("a", SELL, 1, 2), ("b", SELL, 2, 2))
        book.create_reduce_order(order_id="a", size=2)
        assert book.get_expense() == 2

    def test_reduce_only_order_to_zero_is_na(self) -> None:
        book = make_book(1, ("a", SELL, 1, 2))
        book.create_reduce_order(order_id="a", size=2)
        assert book.get_expense() is None

    def test_over_reduce_only_order_is_na(self) -> None:
        book = make_book(1, ("a", BUY, 1, 2))
        book.create_reduce_order(order_id="a", size=5)
        assert book.get_income() is None

    @pytest.mark.xfail(
        strict=True,
        reason="orders reduced to <= 0 stay in the book, so a negative size offsets other orders",
    )
    def test_over_reduce_does_not_offset_other_orders(self) -> None:
        book = make_book(2, ("a", SELL, 1, 1), ("b", SELL, 2, 5))
        book.create_reduce_order(order_id="a", size=3)
        # "a" is gone: 2 @ 2.00. Today a stays at size -2 and the total is 6.
        assert book.get_expense() == 4


class TestApply:
    def test_add_ask_reports_buy_update(self) -> None:
        book = Book(target_size=2)
        message = AddMessage("10", "a", SELL, 3, 2)
        assert book.apply(message) == (Update("10", BUY, 6),)

    def test_add_bid_reports_sell_update(self) -> None:
        book = Book(target_size=2)
        message = AddMessage("10", "a", BUY, 3, 2)
        assert book.apply(message) == (Update("10", SELL, 6),)

    def test_no_update_when_still_na(self) -> None:
        book = Book(target_size=5)
        assert book.apply(AddMessage("10", "a", SELL, 3, 2)) == ()

    def test_no_update_when_added_order_is_beyond_target(self) -> None:
        book = make_book(2, ("a", SELL, 1, 2))
        assert book.apply(AddMessage("10", "b", SELL, 5, 2)) == ()

    def test_no_update_for_other_side(self) -> None:
        book = make_book(1, ("a", SELL, 1, 1))
        updates = book.apply(AddMessage("10", "b", BUY, 1, 1))
        assert [update.side for update in updates] == [SELL]

    def test_reduce_back_to_na_reports_none_total(self) -> None:
        book = make_book(2, ("a", SELL, 3, 2))
        assert book.apply(ReduceMessage("11", "a", 1)) == (Update("11", BUY, None),)

    def test_reduce_outside_fill_is_silent(self) -> None:
        book = make_book(1, ("a", SELL, 1, 1), ("b", SELL, 9, 5))
        assert book.apply(ReduceMessage("11", "b", 2)) == ()

    def test_updates_are_buy_then_sell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A single message only touches one side, so force both totals to change.
        book = Book(target_size=1)
        expenses: Iterator[float | None] = iter([None, 1.0])
        incomes: Iterator[float | None] = iter([None, 2.0])
        monkeypatch.setattr(book, "get_expense", lambda: next(expenses), raising=False)
        monkeypatch.setattr(book, "get_income", lambda: next(incomes), raising=False)
        updates = book.apply(AddMessage("12", "a", SELL, 1, 1))
        assert updates == (Update("12", BUY, 1.0), Update("12", SELL, 2.0))

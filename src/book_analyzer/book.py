"""Core order book logic: no I/O, no parsing."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "AddMessage",
    "Book",
    "Message",
    "Order",
    "ReduceMessage",
    "Side",
    "Total",
    "Update",
]

type Total = float | None
"""A running total, or None when the book holds fewer shares than the target size."""


class Side(StrEnum):
    """Side of an order, valued by its single-letter code in the message log."""

    BUY = "B"
    SELL = "S"


@dataclass(slots=True)
class Order:
    """A resting order."""

    order_id: str
    price: float
    side: Side
    size: int


@dataclass(slots=True, frozen=True)
class AddMessage:
    """Add an order to the book."""

    timestamp: str
    order_id: str
    side: Side
    price: float
    size: int


@dataclass(slots=True, frozen=True)
class ReduceMessage:
    """Reduce the size of an existing order."""

    timestamp: str
    order_id: str
    size: int


type Message = AddMessage | ReduceMessage


@dataclass(slots=True, frozen=True)
class Update:
    """A changed total: BUY is the expense to buy, SELL the income from selling."""

    timestamp: str
    side: Side
    total: Total


class Book:
    """Running collection of unique orders, kept separately for bids and asks."""

    def __init__(self, target_size: int) -> None:
        self._target_size: Final = target_size
        # Maps order_id to Order
        self._buy_orders: dict[str, Order] = {}
        self._sell_orders: dict[str, Order] = {}

    def get_expense(self) -> Total:
        """Total expense to buy the target size, taking asks lowest price first."""
        return self._fill(self._sell_orders, descending=False)

    def get_income(self) -> Total:
        """Total income from selling the target size, hitting bids highest price first."""
        return self._fill(self._buy_orders, descending=True)

    def _fill(self, orders: dict[str, Order], *, descending: bool) -> Total:
        total: float = 0
        available = 0
        remaining_size = self._target_size

        if descending:
            ordered = sorted(orders.values(), key=lambda order: -order.price)
        else:
            ordered = sorted(orders.values(), key=lambda order: order.price)
        for order in ordered:
            available += order.size

            if order.size <= remaining_size:
                total += order.size * order.price
                remaining_size -= order.size
            else:
                total += remaining_size * order.price
                remaining_size = 0

        if available < self._target_size:
            return None
        return total

    def create_add_order(self, order_id: str, price: float, side: Side, size: int) -> None:
        """Add an order to the book."""
        new_order = Order(order_id=order_id, price=price, side=side, size=size)
        if side == Side.BUY:
            self._buy_orders[order_id] = new_order
        else:
            self._sell_orders[order_id] = new_order

    def create_reduce_order(self, order_id: str, size: int) -> None:
        """Reduce an existing order by size; reducing by its remaining size or more removes it."""
        orders = self._buy_orders if order_id in self._buy_orders else self._sell_orders
        order = orders[order_id]
        order.size -= min(size, order.size)
        if order.size == 0:
            del orders[order_id]

    def apply(self, message: Message) -> tuple[Update, ...]:
        """Apply a message and return the totals it changed (buy first, then sell)."""
        old_expense = self.get_expense()
        old_income = self.get_income()

        match message:
            case AddMessage(order_id=order_id, side=side, price=price, size=size):
                self.create_add_order(order_id=order_id, price=price, side=side, size=size)
            case ReduceMessage(order_id=order_id, size=size):
                self.create_reduce_order(order_id=order_id, size=size)

        updates: list[Update] = []
        new_expense = self.get_expense()
        if new_expense != old_expense:
            updates.append(Update(message.timestamp, Side.BUY, new_expense))
        new_income = self.get_income()
        if new_income != old_income:
            updates.append(Update(message.timestamp, Side.SELL, new_income))
        return tuple(updates)

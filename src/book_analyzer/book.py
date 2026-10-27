"""Core order book logic: no I/O, no parsing.

Money is exact: prices are integers in units of 10**-PRICE_DECIMALS (#8).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "PRICE_DECIMALS",
    "PRICE_SCALE",
    "AddMessage",
    "Book",
    "Message",
    "MessageError",
    "Order",
    "ReduceMessage",
    "Side",
    "Total",
    "Update",
    "cents",
]

PRICE_DECIMALS: Final = 6
PRICE_SCALE: Final = 10**PRICE_DECIMALS
_HALF_CENT: Final = PRICE_SCALE // 200
_CENT: Final = PRICE_SCALE // 100


class MessageError(ValueError):
    """An erroneous message (#9): it is reported and skipped, and changes nothing."""


type Total = int | None
"""A running total in price units, or None when the book holds fewer shares than the target."""


def cents(total: int) -> int:
    """`total` (price units, >= 0) rounded half up to whole cents."""
    return (total + _HALF_CENT) // _CENT


class Side(StrEnum):
    """Side of an order, valued by its single-letter code in the message log."""

    BUY = "B"
    SELL = "S"


@dataclass(slots=True)
class Order:
    """A resting order."""

    order_id: str
    price: int
    side: Side
    size: int


@dataclass(slots=True, frozen=True)
class AddMessage:
    """Add an order to the book."""

    timestamp: str
    order_id: str
    side: Side
    price: int
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


def _printed(total: Total) -> int | None:
    """What a total prints as: the change rule compares this, not the exact total."""
    return None if total is None else cents(total)


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
        total = 0
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

    def create_add_order(self, order_id: str, price: int, side: Side, size: int) -> None:
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
        """Apply a message and return the totals it changed (buy first, then sell).

        Raises MessageError, before changing anything, for a reduce of an unknown id or an
        add of an id that is live.

        A total changes when its printed value (rounded half up to cents) changes.
        """
        match message:
            case AddMessage(order_id=order_id):
                if order_id in self._buy_orders or order_id in self._sell_orders:
                    raise MessageError(f"order id {order_id!r} is already live")
            case ReduceMessage(order_id=order_id):
                if order_id not in self._buy_orders and order_id not in self._sell_orders:
                    raise MessageError(f"unknown order id {order_id!r}")
        old_expense = self.get_expense()
        old_income = self.get_income()

        match message:
            case AddMessage(order_id=order_id, side=side, price=price, size=size):
                self.create_add_order(order_id=order_id, price=price, side=side, size=size)
            case ReduceMessage(order_id=order_id, size=size):
                self.create_reduce_order(order_id=order_id, size=size)

        updates: list[Update] = []
        new_expense = self.get_expense()
        if _printed(new_expense) != _printed(old_expense):
            updates.append(Update(message.timestamp, Side.BUY, new_expense))
        new_income = self.get_income()
        if _printed(new_income) != _printed(old_income):
            updates.append(Update(message.timestamp, Side.SELL, new_income))
        return tuple(updates)

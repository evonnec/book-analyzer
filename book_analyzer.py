from dataclasses import dataclass
from enum import Enum
import sys
from typing import Optional


class Side(Enum):
    BUY = "B"
    SELL = "S"


@dataclass
class Order:
    order_id: str
    price: float
    side: Side
    size: int


class Book:
    def __init__(self, target_size: int) -> None:
        self._target_size = target_size
        # Maps order_id to Order
        self._buy_orders = {}
        self._sell_orders = {}

    def get_expense(self) -> Optional[int]:
        # the total expense you would incur if you bought target-size shares
        # (by taking as many asks as necessary, lowest first)

        total_expense = 0
        total_shares_we_can_buy = 0
        remaining_size = self._target_size
        
        all_orders = list(self._sell_orders.values())
        all_orders.sort(key=lambda order: order.price)
        for order in all_orders:
            total_shares_we_can_buy += order.size

            if order.size <= remaining_size:
                total_expense += order.size * order.price
                remaining_size -= order.size
            else:
                total_expense += remaining_size * order.price
                remaining_size = 0

        if total_shares_we_can_buy < self._target_size:
            return None
        return total_expense

    def get_income(self) -> Optional[int]:
        # the total income you would receive if you sold target-size shares
        # (by hitting as many bids as necessary, highest first)

        total_income = 0
        total_shares_we_can_sell = 0
        remaining_size = self._target_size
        
        all_orders = list(self._buy_orders.values())
        all_orders.sort(key=lambda order: -order.price)
        for order in all_orders:
            total_shares_we_can_sell += order.size

            if order.size <= remaining_size:
                total_income += order.size * order.price
                remaining_size -= order.size
            else:
                total_income += remaining_size * order.price
                remaining_size = 0
    
        if total_shares_we_can_sell < self._target_size:
            return None
        return total_income

    def create_add_order(
        self,
        order_id: str,
        price: float,
        side: Side,
        size: int,
    ) -> None:
        new_order = Order(
            order_id=order_id,
            price=price,
            side=side,
            size=size,
        )
        if side == Side.BUY:
            self._buy_orders[order_id] = new_order
        else:
            self._sell_orders[order_id] = new_order

    def create_reduce_order(self, order_id: str, size: int) -> None:
        if order_id in self._buy_orders:
            old_order = self._buy_orders[order_id]
        else:
            old_order = self._sell_orders[order_id]

        new_order = Order(
            order_id=order_id,
            price=old_order.price,
            side=old_order.side,
            size=old_order.size - size,
        )
        
        # In the future for efficiency maybe we can remove orders with size 0.
        if order_id in self._buy_orders:
            self._buy_orders[order_id] = new_order
        else:
            self._sell_orders[order_id] = new_order


def cli_function(input_file, output_file, target_size: int):
    book = Book(target_size=target_size) 
    for line in input_file.readlines():
        old_expense = book.get_expense()
        old_income = book.get_income()

        split_string = line.strip().split(" ")
        if len(split_string) == 4:
            timestamp, literal_string, order_id, size = split_string
            book.create_reduce_order(order_id=order_id, size=int(size))

        if len(split_string) == 6:
            (
                timestamp,
                literal_string,
                order_id,
                side_string,
                price,
                size,
            ) = split_string
            book.create_add_order(
                order_id=order_id,
                price=float(price),
                side=Side(side_string),
                size=int(size),
            )

        # TODO handle if length is not 4 or 6
        # Parse input:
        # If BookAnalyzer encounters an error in an input message,
        # it prints a warning to standard error and proceeds to the next message.

        new_expense = book.get_expense()
        new_income = book.get_income()
        if new_expense != old_expense:
            if new_expense is None:
                new_expense = 'NA'
            else:
                new_expense = "{:.2f}".format(new_expense)
            message = timestamp + " B " + new_expense + "\n"
            output_file.write(message)

        if new_income != old_income:
            if new_income is None:
                new_income = 'NA'
            else:
                new_income = "{:.2f}".format(new_income)
            message = timestamp + " S " + str(new_income) + "\n"
            output_file.write(message)


# Task list:
#
# * Consider remaining TODOs
# * Add docstrings
# * Explain error input
# * Consider performance / alternative implementations

if __name__ == "__main__":
    target_size = int(sys.argv[1])
    cli_function(
        input_file=sys.stdin,
        output_file=sys.stdout,
        target_size=target_size,
    )

from dataclasses import dataclass
from enum import Enum
import sys
from typing import Optional


class Side(Enum):
    """
    Type Side for Order class
    """
    BUY = "B"
    SELL = "S"


@dataclass
class Order:
    """
    Order data decorator
    """
    order_id: str
    price: float
    side: Side
    size: int


class Book:
    """
    a book keeps a running/current list of unique orders
    divided into two books for bids/offers for performance, but this is likely not optimal.
    """
    def __init__(self, target_size: int) -> None:
        self._target_size = target_size
        # Maps order_id to Order
        self._buy_orders = {}
        self._sell_orders = {}

    def get_expense(self) -> Optional[int]:
        """
        The total expense you would incur if you bought shares up to the target-size
        (by taking as many asks as necessary, lowest first, until target-size is filled)
        """

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
        """
        The total income you would receive if you sold shares up to the target-size 
        (by hitting as many bids as necessary, highest first, until target size is filled).
        """

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
        """
        if readlines length is 6, creates an add order to the book
        """
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
        """
        if readlines length is 4, creates reduce order to the book
        """
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

        # In the future for efficiency reasons, we can remove orders with size 0.
        if order_id in self._buy_orders:
            self._buy_orders[order_id] = new_order
        else:
            self._sell_orders[order_id] = new_order


def cli_function(input_file, output_file, target_size: int):
    """
    makes a book class, iters thru input, determines order type A(dd) or R(emove), 
    runs create_add_order or create_reduce_order function, handles formatting.
    With more time, would split out formatting to it's own function to be called, 
    Also some code duplication here in formatting, with more time, pass Side to determine if it's expense or income.
    would use try-except-finally clause instead of if-then, and give it separate error handling.
    """
    book = Book(target_size=target_size)
    for line_index, line in enumerate(input_file.readlines()):
        old_expense = book.get_expense()
        old_income = book.get_income()

        split_string = line.strip().split(" ")
        if len(split_string) == 4:
            timestamp, literal_string, order_id, size = split_string
            book.create_reduce_order(order_id=order_id, size=int(size))
        elif len(split_string) == 6:
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
        else:
            # if readlines length is not 4 or 6, write error msg to std output with where it's coming from
            output_file.write(
                f"Warning: Invalid line (line {line_index + 1}), "
                "see documentation for format\n"
            )

        new_expense = book.get_expense()
        new_income = book.get_income()
        if new_expense != old_expense:
            if new_expense is None:
                new_expense = "NA"
            else:
                new_expense = "{:.2f}".format(new_expense)
            message = timestamp + " B " + new_expense + "\n"
            output_file.write(message)

        if new_income != old_income:
            if new_income is None:
                new_income = "NA"
            else:
                new_income = "{:.2f}".format(new_income)
            message = timestamp + " S " + str(new_income) + "\n"
            output_file.write(message)

if __name__ == "__main__":
    target_size = int(sys.argv[1])
    cli_function(
        input_file=sys.stdin,
        output_file=sys.stdout,
        target_size=target_size,
    )

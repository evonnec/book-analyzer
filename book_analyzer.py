from dataclasses import dataclass
from enum import Enum
import sys

class Side(Enum):
    BUY = 'B'
    SELL = 'S'


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
        self._orders = {}

    def get_expense(self) -> int:
        # the total expense you would incur if you bought target-size shares
        # (by taking as many asks as necessary, lowest first)
        
        # TODO: Maybe we also need to know
        # how many shares are available and does that >= the target size?

        total = 0
        for order_id, order in self._orders.items():
            if order.side == Side.BUY:
                total += order.price * order.size
        return total

    def get_income(self) -> int:
        # the total income you would receive if you sold target-size shares
        # (by hitting as many bids as necessary, highest first)

        # TODO: Maybe we also need to know
        # how many shares are available and does that >= the target size?
        
        total = 0
        for order_id, order in self._orders.items():
            if order.side == Side.SELL:
                total += order.price * order.size
        return total

    def create_add_order(self, order_id: str, price: float, side: Side, size: int) -> None:
        # TODO handle if the order_id already exists

        new_order = Order(
            order_id=order_id,
            price=price,
            side=side,
            size=size,
        )
        
        self._orders[order_id] = new_order
    
    def create_reduce_order(self, order_id: str, size: int) -> None:
        # TODO handle if we try to reduce the size to below 0
        
        # TODO handle if the order_id does not exist
        # TO DO handle when the size is reduced to zero, to remove the order_id from the book completely
        
        old_order = self._orders[order_id]
        new_order = Order(
            order_id=order_id,
            price=old_order.price,
            side=old_order.side, 
            size=old_order.size - size,
        )
        self._orders[order_id] = new_order
        
        

book = Book(target_size=200) # 200 is given from the user on the CLI

# TODO deal with stdin
# for line in sys.stdin:


def cli_function(input_file, output_file):

    for line in input_file.readlines():
        old_expense = book.get_expense()
        old_income = book.get_income()

        
        split_string = line.strip().split(' ')
        if len(split_string) == 4:
            # If length is 4 it is a Reduce Order
            
            # TODO handle if literal_string is not "R", show an error
            timestamp, literal_string, order_id, size = split_string
            book.create_reduce_order(order_id=order_id, size=int(size))
        
        if len(split_string) == 6:
            # If length is 6 it is an Add Order
            
            # TODO handle if side is not "B" or "S", show an error
            timestamp, literal_string, order_id, side_string, price, size = split_string
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
            # TODO print formatted message
            message = timestamp + ' B ' + str(new_expense) + '\n'
            # breakpoint()
            output_file.write(message)
        
        if new_income != old_income:
            # TODO print formatted message
            message = timestamp + ' S ' + str(new_income) + '\n'
            # breakpoint()
            output_file.write(message)

# Task list:
#
# * Get this working with the tiny sample input data at the bottom of the Google Doc
#    with hand-copied input
# * Get this working with the tiny sample input data in a nice way, reading stdin
# * Get this working with the large sample input
# * Consider remaining TODOs
# * Handle error input
# * Consider performance / alternative implementations

if __name__ == '__main__':
    cli_function(
        input_file=sys.stdin,
        output_file=sys.stdout,
    )
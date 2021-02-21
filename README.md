# book-analyzer  
  
## How to run the CLI

Requires Python 3. 
Target size as an arg.
And input file of a book.

Example, where 200 is the target size:

`python book_analyzer.py 200 < input.txt`

## How to run Tests

`python -m unittest test_book_analyzer.py`

## Errors I considered

I considered the following errors:

* An order is added without S or B as the side
* An order is added with an existing order ID
* An order is reduced but the order ID does not exist
* An order is reduced by more than the available size
* The literal string given is not as expected
* target size is not a positive int, input or output file do not get passed.
* An input line is not of length 4 or 6 as seen in the example input

I implemented error handling for the last error of if an input line does not have a length of 4 or 6, but did not handle the other error types for time purposes.

## Quality

I added tests for enough functionality as specified by the problem, but they are not thorough.
I would add more in production.

I added some comments and docstrings but I would add more in production.

I did not do thorough performance testing for time purposes.

## Possible Next Steps

* Add a __lt__ around market rules such as price first, timestamp second.
* Insert orders in order for bids and offers, to avoid sorting them later which is an expensive task for a large book.
* Or use a data structure that allows for that such as heaps.
* Maintain a data structure of orders that would fill to the target size for both bids and offers, then separate data structures for bids and offers books to fill that primary data structure when there are executions or cancellations (i.e. the order gets removed from the book)
* Maybe use heap data structures or bisect library for ordered orders for the 3 data structures (target size bids/offers, rest of bids, rest of offers) to more quickly pop and push.

## Questions

* How did you choose your implementation language?

I felt that this would be simplest to write in Python.

* How did you arrive at your final implementation? Were there other approaches that you considered or tried first? 

I started by writing the CLI function and calling functions from a Book class and created classes and functions as they were needed.

For storing orders, I tried two approaches:

    1. Storing a dictionary of order IDs mapping to orders
    2. Storing an ordered list of orders

I tested this with a subset of the large input provided and chose the fastest option.

I considered alternatives such as bisect and heapq but I stopped before trying these. 

* How does your implementation scale with respect to the target size?

This scales with the time it takes to sort the orders by price.
With a lower target size, we may exit early but not in the worst case.

* How does your implementation scale with respect to the number of orders in the book? 

As the number of orders in the book increases, our repeated sorting means that it is O(n log n).


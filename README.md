# book-analyzer  
  
## How to run the CLI

Requires Python 3.

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
* An input line is not of length 4 or 6

I implemented error handling for the last error but did not handle the other error types for time purposes.

## Quality

I added tests for enough functionality that I am confident, but they are not thorough.
I would add more in production.

I added a few comments and docstrings but I would add more in production.

I did not do thorough performance testing for time purposes.

## Questions

* How did you choose your implementation language?

I felt that this would be simplest to write in Python of the languages I am familiar with.

* How did you arrive at your final implementation? Were there other approaches that you considered or tried first? 

I started by writing the CLI function and calling functions from a Book class and created classes and functions as they were needed.

For storing orders, I tried two approaches:

    1. Storing a dictionary of order IDs mapping to orders
    2. Storing an ordered list of orders

I tested this with large inputs and chose the fastest option.

I considered alternatives such as binary insert and heaps but I stopped before trying these.

* How does your implementation scale with respect to the target size?

This scales with the time it takes to sort the orders by price.
With a lower target size, we may exit early but not in the worst case.

* How does your implementation scale with respect to the number of orders in the book? 

As the number of orders in the book increases, our repeated sorting means that it is O(n log n).


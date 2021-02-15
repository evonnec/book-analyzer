# book-analyzer  
  
## How to run the CLI

Requires Python 3.

Example, where 200 is the target size:

`python book_analyzer.py 200 < input.txt`

## How to run Tests

`python -m unittest test_book_analyzer.py`

## Questions

* How did you choose your implementation language?

I felt that this would be simplest to write in Python.

* How did you arrive at your final implementation? Were there other approaches that you considered or tried first? 

I started by writing the CLI function and calling functions from a Book class and created classes and functions as they were needed.

I looked at using heapify in order to sort the orders on the book for purchases and sales to quicken the sorting.

* How does your implementation scale with respect to the target size?

This scales with the time it takes to sort the orders by price.
With a lower target size, we may exit early but not in the worst case.

* How does your implementation scale with respect to the number of orders in the book? 

As the number of orders in the book increases, our repeated sorting means that it is O(n log n).


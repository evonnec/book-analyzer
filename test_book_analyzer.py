import unittest
import textwrap
from io import StringIO

from book_analyzer import cli_function, Book, Side


class TestExample(unittest.TestCase):
    def test_example(self):
        target_size = 200
        sample_input = textwrap.dedent(
            """
            28800538 A b S 44.26 100 
            28800562 A c B 44.10 100 
            28800744 R b 100 
            28800758 A d B 44.18 157 
            28800773 A e S 44.38 100 
            28800796 R d 157 
            28800812 A f B 44.18 157 
            28800974 A g S 44.27 100 
            28800975 R e 100 
            28812071 R f 100
            28813129 A h B 43.68 50 
            28813300 R f 57 
            28813830 A i S 44.18 100 
            28814087 A j S 44.18 1000 
            28814834 R c 100 
            28814864 A k B 44.09 100 
            28815774 R k 100 
            28815804 A l B 44.07 175 
            28815937 R j 1000 
            28816245 A m S 44.22 100 
            """
        )

        sample_input_file = StringIO(sample_input)
        test_output_file = StringIO()

        cli_function(
            input_file=sample_input_file,
            output_file=test_output_file,
            target_size=target_size,
        )
        contents = test_output_file.getvalue()

        expected_contents = textwrap.dedent(
            """\
            28800758 S 8832.56
            28800796 S NA
            28800812 S 8832.56
            28800974 B 8865.00
            28800975 B NA
            28812071 S NA
            28813129 S 8806.50
            28813300 S NA
            28813830 B 8845.00
            28814087 B 8836.00
            28815804 S 8804.25
            28815937 B 8845.00
            28816245 B 8840.00
            """
        )
        assert contents == expected_contents


class TestBookExpense(unittest.TestCase):
    def test_default(self):
        book = Book(target_size=1)
        result = book.get_expense()
        assert result is None

    def test_add_sell_order(self):
        book = Book(target_size=1)
        book.create_add_order(
            order_id="abcde",
            price=3,
            side=Side.SELL,
            size=2,
        )
        result = book.get_expense()
        assert result == 3

    def test_add_buy_order(self):
        book = Book(target_size=1)
        book.create_add_order(
            order_id="abcde",
            price=1,
            side=Side.BUY,
            size=2,
        )
        result = book.get_expense()
        assert result is None

    def test_reduce_order(self):
        book = Book(target_size=1)
        book.create_add_order(
            order_id="abcde",
            price=1,
            side=Side.SELL,
            size=2,
        )
        result = book.create_reduce_order(
            order_id="abcde",
            size=1,
        )
        result = book.get_expense()
        assert result == 1

    def test_target_size_gt_available_shares(self):
        book = Book(target_size=10)
        book.create_add_order(
            order_id="abcde",
            price=1,
            side=Side.SELL,
            size=2,
        )
        result = book.get_expense()
        assert result is None

    def test_available_shares_various_prices(self):
        book = Book(target_size=5)
        book.create_add_order(
            order_id="abcde",
            price=1.50,
            side=Side.SELL,
            size=2,
        )
        book.create_add_order(
            order_id="bcdef",
            price=2.10,
            side=Side.SELL,
            size=2,
        )
        book.create_add_order(
            order_id="cdefg",
            price=2.05,
            side=Side.SELL,
            size=2,
        )
        book.create_add_order(
            order_id="defgh",
            price=1.75,
            side=Side.SELL,
            size=2,
        )
        result = book.get_expense()
        assert result == 8.55
import unittest
import textwrap
from io import StringIO

from book_analyzer import cli_function

class TestExample(unittest.TestCase):

    def test_example(self):
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
        # Pretend that standard input is like the sample_input
        # Pass that to our CLI function
        # Check the output
import sys

from book_analyzer.cli import cli_function


def entry() -> None:
    cli_function(input_file=sys.stdin, output_file=sys.stdout, target_size=int(sys.argv[1]))


if __name__ == "__main__":
    entry()

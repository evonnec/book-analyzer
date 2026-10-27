"""Adapters that keep the tests independent of API details the fix issues change.

  * #8 replaces float prices and totals with exact integers in some fixed unit. Tests build
    prices with `price("1.50")` (the package's own representation of that decimal, read back
    through `parse_line`) and compare totals with `price(...)` or by how they print (`shown`).
  * #9 makes `parse_line` raise `MessageError` (a `ValueError`) instead of returning None, and
    adds an error stream to `run`. `rejects` accepts either way of refusing a line, and
    `call_run` passes an error stream only if `run` takes one.

With these, a fix PR only has to remove the `xfail` marks of its issue.
"""

import inspect
from collections.abc import Callable
from contextlib import redirect_stderr
from typing import Any, TextIO, cast

from book_analyzer import AddMessage, Side, Total, Update, cli


def price(text: str) -> Any:
    """The package's representation of the decimal price `text` (a float before #8)."""
    message = cli.parse_line(f"0 A price S {text} 1")
    assert isinstance(message, AddMessage)
    return message.price


def shown(total: Total) -> str:
    """How the program prints `total`: `NA` or a 2-decimal amount."""
    return cli.format_update(Update("0", Side.BUY, total)).split()[2]


def rejects(line: str) -> bool:
    """Whether `parse_line` refuses `line`: by returning None (before #9) or by raising
    `MessageError` (#9). Any other exception propagates, so a crash still fails the test."""
    try:
        return cli.parse_line(line) is None
    except ValueError as error:
        if any(cls.__name__ == "MessageError" for cls in type(error).__mro__):
            return True
        raise


def error_parameter() -> str | None:
    """The name of `run`'s error stream parameter (it contains "err" or "warn"), if any."""
    names = inspect.signature(cli.run).parameters
    return next((name for name in names if "err" in name or "warn" in name), None)


def call_run(input_file: TextIO, output_file: TextIO, error_file: TextIO, target_size: int) -> None:
    """Call `cli.run` by keyword. Before #9 it has no error stream: `sys.stderr` is redirected."""
    run = cast(Callable[..., None], cli.run)
    kwargs: dict[str, object] = {
        "input_file": input_file,
        "output_file": output_file,
        "target_size": target_size,
    }
    name = error_parameter()
    if name is None:
        with redirect_stderr(error_file):
            run(**kwargs)
    else:
        run(**kwargs, **{name: error_file})

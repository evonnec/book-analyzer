# book-analyzer

A small Python command line tool that replays a limit order book message log and reports, each
time it changes, how much it would cost to buy a fixed number of shares and how much selling the
same number would earn.

## Problem

The input is a log of order book messages on standard input, one per line, fields separated by a
single space:

```
timestamp A order-id side price size     add an order (side is B for bid, S for ask)
timestamp R order-id size                reduce an order by size
```

Order ids are unique. A reduce by at least the remaining size removes the order. The program
takes one argument, `TARGET_SIZE`, a positive integer number of shares.

After every message the program works out two totals:

- the expense of buying `TARGET_SIZE` shares, filling from the lowest-priced asks upwards;
- the income from selling `TARGET_SIZE` shares, filling from the highest-priced bids downwards.

If a total differs from its previous value, a line `timestamp B total` (expense) or
`timestamp S total` (income) is printed. Totals have two decimals. When that side of the book
holds fewer than `TARGET_SIZE` shares the total is `NA`. Both totals start out as `NA`, so nothing
is printed until a side first has enough liquidity. Malformed messages should produce a warning
on stderr and be skipped (see Known issues for where that falls short today).

Example with `TARGET_SIZE` 200:

```
28800538 A b S 44.26 100     ask: 100 @ 44.26, not enough for 200
28800562 A c B 44.10 100     bid: 100 @ 44.10, not enough for 200
28800744 R b 100             ask removed
28800758 A d B 44.18 157     bids 157 @ 44.18 + 100 @ 44.10: sells 200 for 8832.56
```

Only the last message changes a total, so the output is:

```
28800758 S 8832.56
```

The full sample and its expected output live in `tests/conftest.py`.

## Install and run

Requires Python 3.15 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run book-analyzer 200 < log
uv run python -m book_analyzer 200 < log
```

To install the built wheel into any environment:

```sh
uv build
pip install dist/book_analyzer-*.whl
book-analyzer 200 < log
BookAnalyzer 200 < log      # same command, alternate name
```

## Design

The code is split into a pure core and a thin I/O layer, under `src/book_analyzer/`.

- `book.py` is the core and does no I/O or parsing. It defines `Side`, `Order`, the messages
  `AddMessage` and `ReduceMessage`, the result `Update`, and `Book`. `Book.apply(message)`
  mutates the book and returns the totals that changed, expense first, as a tuple of `Update`.
- `cli.py` parses lines into messages (`parse_line`), formats updates (`format_update`) and
  drives the loop (`run`) over any text streams. `__main__.py` reads the target size from argv
  and wires up stdin and stdout.

Data model: a `Book` keeps two dicts from order id to `Order`, one for bids and one for asks.
Timestamps and ids are kept as strings and sizes as ints.

Money is exact. A price is an ASCII decimal (`[0-9]+(\.[0-9]{1,6})?`, so up to six decimals; no
sign, exponent, underscores or other digits) parsed straight into an integer number of
millionths, never through a float. Totals are exact integers in the same unit, rounded half up to
cents only when printed (`2.675` prints as `2.68`), so totals of any size stay exact.

Totals: `get_expense` and `get_income` sort the relevant side by price (ascending for asks,
descending for bids) and accumulate `size * price` until `TARGET_SIZE` shares are covered, taking
only part of the last level if needed. `apply` computes both totals before and after the change
and reports a side only if its printed (rounded) total differs. With prices of more than two
decimals two exact totals can round to the same cents; no line is printed for such a change, so
a side never prints the same value twice in a row.

A reduce by at least an order's remaining size deletes the order, so the book holds only resting
orders.

Complexity as currently implemented: each message calls `get_expense` and `get_income` twice
(before and after the change), which is four full sorts of a side per message, so a message costs
O(n log n) in the number of resting orders n and a log of m messages O(m n log n). Running time
grows with book depth, not with the target size beyond the accumulation loop stopping early. On
the 1.19M-message reference log (at most about 230 resting orders) a target size takes roughly a
minute of CPU. Keeping each side ordered by price level and recomputing only the side a message
touches would remove the sorts (#10).

## Known issues

Behavior is deliberately unchanged for now. The test suite pins each of these with a strict
`xfail`, which fails once the defect is fixed so the marker has to be removed. Fixes are tracked
in issues: #9 error handling,
#11 CLI argument handling, #12 streaming.

- Warnings are written to stdout, not stderr. (#9)
- A non-numeric size or price, or an unknown side, raises `ValueError` and aborts the run. (#9)
- Reducing an unknown order id raises `KeyError`. (#9)
- Adding an id that already exists silently replaces the order. (#9)
- The message type field (`A`/`R`) is ignored; messages are classified by field count. (#9)
- A missing, non-integer, zero or negative `TARGET_SIZE` is not rejected with a usage error. (#11)
- All of stdin is read before processing starts, so output is not produced incrementally. (#12)

## Development

```sh
uv sync --locked --all-groups
uv run pytest --cov=book_analyzer --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .      # uv run ruff format . to apply
uv run mypy src tests
uv build
```

These match the CI jobs in `.github/workflows/ci.yml`, which also enforces 100% line coverage of
`src`. `tests/` has no `__init__.py` by design: pytest runs in `importlib` import mode, so test
modules cannot import each other and shared fixtures live in `tests/conftest.py`.

## Testing

- `tests/test_book.py`: unit tests for `Book`.
- `tests/test_cli.py`: parsing, formatting, the run loop, the specification sample and the
  malformed-input behavior.
- `tests/test_main.py`: the entry point in process and as a `python -m book_analyzer` subprocess.
- `tests/test_properties.py`: Hypothesis tests against a brute-force oracle in integer cents.
- `tests/test_benchmark.py`: smoke test of the benchmark generator and runner.
- `tests/test_reference_data.py`: opt-in, see below.

Strict xfails mark the known issues above. Run `uv run pytest -rx` to list them.

### Reference data test

This test compares the output against a large reference log and its expected outputs, which are
not part of the repository. It is skipped unless `BOOK_ANALYZER_DATA` points to a directory with
`book_analyzer.in` and `book_analyzer.out.1`, `.200` and `.10000`:

```sh
BOOK_ANALYZER_DATA=/path/to/data BOOK_ANALYZER_DATA_LINES=10000 uv run pytest tests/test_reference_data.py
```

`BOOK_ANALYZER_DATA_LINES` limits the input to its first N lines, extended to the end of the
last line's timestamp so that no message is split from its timestamp, and compares against the
reference lines up to that timestamp. The default is the whole file (1.19M messages), about a minute of
CPU per target size.

Current status: on the whole file, target sizes 1, 200 and 10000 all match byte for byte, with
nothing written to stderr. The test asserts exact equality and is not marked xfail, since it is
opt-in.

## Benchmark

`benchmarks/bench.py` is a stdlib-only synthetic benchmark. A seeded generator makes a log that
mimics a realistic book (about 200 live orders, 2-decimal prices on a random walk, half adds and
half reduces, almost all reduces removing the order), replays it through the installed package
and prints messages per second and p50/p99/max per-message latency:

```sh
uv run python benchmarks/bench.py                              # 5,000 messages, target 200
uv run python benchmarks/bench.py --messages 100000 --target 10000 --seed 7
```

Numbers depend on the machine, so compare runs on the same one.

## Releasing

See [docs/releasing.md](docs/releasing.md).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).

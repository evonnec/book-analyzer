# book-analyzer

A small Python command line tool that replays a limit order book message log and reports, each
time it changes, how much it would cost to buy a fixed number of shares and how much selling the
same number would earn.

## Problem

### Background

A *limit order* is an offer to trade a number of shares at a stated price or better. A limit
order to buy is a **bid**: the buyer will pay up to its price. A limit order to sell is an
**ask**: the seller will accept at least its price. Orders that haven't traded yet rest in the
**limit order book** ("the book"), and the bids and asks are its two sides.

Someone who wants to trade right away, at whatever the book offers, takes the best prices
first. A buyer starts at the lowest ask and works up. A seller starts at the highest bid and works
down. Each level supplies as many shares as it holds. For example, if the bids are 300 shares at
$9.98, 200 at $10.00 and 100 at $10.01, selling 250 shares right away hits 100 @ 10.01 and 150 @
10.00, for $2,501.00.

A market data feed describes the book as a stream of messages. Each message either adds an order
or reduces the size of an existing one; reducing it to zero removes it. Replaying a recorded log
of these messages rebuilds the book as it was at every moment.

### Task

`book-analyzer TARGET_SIZE` reads such a log on standard input. `TARGET_SIZE` is a positive
integer number of shares. After each message it works out:

- the **expense** of buying `TARGET_SIZE` shares by taking asks, lowest price first;
- the **income** from selling `TARGET_SIZE` shares by hitting bids, highest price first.

Whenever one of them changes, it prints the new value. Both start out as `NA` (not enough
shares), so nothing is printed until a side first holds `TARGET_SIZE` shares.

### Input format

One message per line, terminated by `\n`, fields separated by spaces. The log is sorted by
timestamp.

Add an order: `timestamp A order-id side price size`

| Field | Meaning |
|---|---|
| `timestamp` | When the market generated the message, in milliseconds since midnight |
| `A` | Literal: this message adds an order to the book |
| `order-id` | Unique string that later reduce messages use to refer to this order |
| `side` | `B` for a buy order (bid), `S` for a sell order (ask) |
| `price` | The order's limit price |
| `size` | The order's size in shares when it was sent to the market |

Reduce an order: `timestamp R order-id size`

| Field | Meaning |
|---|---|
| `timestamp` | When the market generated the message, in milliseconds since midnight |
| `R` | Literal: this message reduces an order |
| `order-id` | The order to reduce |
| `size` | How many shares to remove from the order. This is not the new size. Reducing by the remaining size or more removes the order from the book |

### Output format

One line per changed total: `timestamp action total`

| Field | Meaning |
|---|---|
| `timestamp` | The timestamp of the input message that caused the change |
| `action` | `B` if the line carries the new expense to buy `TARGET_SIZE` shares, `S` if it carries the new income from selling them |
| `total` | The expense (`B`) or income (`S`) with exactly two decimals, or `NA` if the relevant side (asks for `B`, bids for `S`) holds fewer than `TARGET_SIZE` shares |

A single message changes only one side of the book, so it produces at most one line. An erroneous
message produces one warning on standard error and is skipped. Processing continues, and standard
output carries only result lines, so the tool works in a shell pipeline. The validation rules are
under [Design](#design).

### Worked example

With `TARGET_SIZE` 200, the book shows bids on the left and asks on the right, best price first:

| # | Message | Output | Book after (bids x asks) | Why |
|---|---|---|---|---|
| 1 | `28800538 A b S 44.26 100` | | — x 100@44.26 | Neither side holds 200 shares |
| 2 | `28800562 A c B 44.10 100` | | 100@44.10 x 100@44.26 | Still not enough on either side |
| 3 | `28800744 R b 100` | | 100@44.10 x — | `b` is removed. Both totals stay `NA`, so nothing changes |
| 4 | `28800758 A d B 44.18 157` | `28800758 S 8832.56` | 157@44.18, 100@44.10 x — | Bids total 257. Selling 200: 157 × 44.18 + 43 × 44.10 = 6936.26 + 1896.30 |
| 5 | `28800773 A e S 44.38 100` | | 157@44.18, 100@44.10 x 100@44.38 | Only 100 shares of asks, so the expense stays `NA` |
| 6 | `28800796 R d 157` | `28800796 S NA` | 100@44.10 x 100@44.38 | Only 100 shares of bids are left |
| 7 | `28800812 A f B 44.18 157` | `28800812 S 8832.56` | 157@44.18, 100@44.10 x 100@44.38 | Bids are back over 200 |
| 8 | `28800974 A g S 44.27 100` | `28800974 B 8865.00` | 157@44.18, 100@44.10 x 100@44.27, 100@44.38 | Asks total exactly 200: 100 × 44.27 + 100 × 44.38 |
| 9 | `28800975 R e 100` | `28800975 B NA` | 157@44.18, 100@44.10 x 100@44.27 | Asks drop below 200 |
| 10 | `28812071 R f 100` | `28812071 S NA` | 57@44.18, 100@44.10 x 100@44.27 | `f` shrinks to 57, leaving 157 shares of bids |
| 11 | `28813129 A h B 43.68 50` | `28813129 S 8806.50` | 57@44.18, 100@44.10, 50@43.68 x 100@44.27 | 57 × 44.18 + 100 × 44.10 + 43 × 43.68 |
| 12 | `28813300 R f 57` | `28813300 S NA` | 100@44.10, 50@43.68 x 100@44.27 | `f` is removed, leaving 150 shares of bids |
| 13 | `28813830 A i S 44.18 100` | `28813830 B 8845.00` | 100@44.10, 50@43.68 x 100@44.18, 100@44.27 | 100 × 44.18 + 100 × 44.27 |
| 14 | `28814087 A j S 44.18 1000` | `28814087 B 8836.00` | 100@44.10, 50@43.68 x 1100@44.18, 100@44.27 | `i` and `j` tie at 44.18, so all 200 shares cost 44.18 |
| 15 | `28814834 R c 100` | | 50@43.68 x 1100@44.18, 100@44.27 | Income was already `NA` and stays `NA` |
| 16 | `28814864 A k B 44.09 100` | | 100@44.09, 50@43.68 x 1100@44.18, 100@44.27 | 150 shares of bids, still `NA` |
| 17 | `28815774 R k 100` | | 50@43.68 x 1100@44.18, 100@44.27 | Back to 50 shares of bids |
| 18 | `28815804 A l B 44.07 175` | `28815804 S 8804.25` | 175@44.07, 50@43.68 x 1100@44.18, 100@44.27 | 175 × 44.07 + 25 × 43.68 |
| 19 | `28815937 R j 1000` | `28815937 B 8845.00` | 175@44.07, 50@43.68 x 100@44.18, 100@44.27 | With `j` gone, half the shares cost 44.27 again |
| 20 | `28816245 A m S 44.22 100` | `28816245 B 8840.00` | 175@44.07, 50@43.68 x 100@44.18, 100@44.22, 100@44.27 | 44.22 beats 44.27: 100 × 44.18 + 100 × 44.22 |

The output is just the Output column, in order. The same sample and its expected output are in
`tests/conftest.py`.

### Goals

In priority order:

- **Correctness.** It comes before everything else. The output must match the reference outputs
  exactly.
- **Clarity.** Another engineer should be able to understand, fix and extend the code without
  extensive comments.
- **Conciseness.** Less code means less to read and maintain.
- **Efficiency.** The tool may run on live data, so time and memory matter. Gratuitous
  inefficiency is a defect.
- **Unix behavior.** It reads standard input and writes standard output, with no prompts mixed
  into the results, so it composes with other tools.
- **Standard library only.** It has no runtime dependencies.

### Test data

A larger log of real market data, 1.19M messages, comes with the reference implementation's
outputs for target sizes 1, 200 and 10000. They aren't in the repository. See
[Reference data test](#reference-data-test) for how to check against them.

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
  It raises `MessageError` (a `ValueError`), before changing anything, for a reduce of an
  unknown id or an add of an id that is still live.
- `cli.py` parses lines into messages (`parse_line`, which raises `MessageError` for an invalid
  line), formats updates (`format_update`) and drives the loop (`run`) over any text streams,
  writing results to one stream and warnings to another. `__main__.py` reads the target size
  from argv and wires up stdin, stdout and stderr.

Input validation. Fields are separated by runs of spaces or tabs; a trailing CR is ignored and a
UTF-8 BOM on the first line is dropped. A message is rejected when:

- the type is not `A` with exactly six fields or `R` with exactly four;
- the timestamp is not ASCII digits, the side is not `B` or `S`, the size is not a positive
  ASCII integer, or the price is not a positive price in the grammar below;
- a reduce names an id that is not live, or an add reuses an id that is still live.

Accepted as valid: a reduce by at least the remaining size (it removes the order), reusing an id
after its order was removed, a crossed book (bid at or above ask; orders are not matched), and
non-increasing timestamps (the input is promised sorted, and rejecting would desynchronize the
book). Undecodable bytes are decoded with `surrogateescape`, so they reject only their own line.
Each rejected line gives exactly one warning on stderr, for example:

```
warning: line 3: unknown order id 'zz': '3 R zz 1'
```

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

### Design questions

**Why Python?** It keeps the code short and readable, and the standard library covers everything
the tool needs. The cost is speed: on the 1.19M-message reference log a target size takes roughly
a minute of CPU. That is fast enough for the provided data, which spans about 12 hours of market
time.

**How was the implementation chosen?** The first version stored each side as a dict from order id
to order, and sorted a side whenever it needed a total. A version that kept a single ordered list
of orders was tried and was slower on a sample of the reference log. `bisect` and `heapq` were
considered but not tried at first. A heap is a poor fit because reduces remove orders from
anywhere in the book, not only the best price. Later changes kept the design and fixed its
defects:

- fully reduced orders are deleted (#7);
- money is exact integers (#8);
- every message is validated (#9).

A profile of the reference log points to the next step: a price-level book that keeps each side's
levels sorted with `bisect` and recomputes only the side a message touches (#10). The profile shows
about 200 live orders, at most 71 bid and 94 ask price levels, and 99.5% of reduces removing their
order.

**How does it scale with the target size?** Only through the accumulation loop, which walks levels
from the best price until `TARGET_SIZE` shares are covered. On the reference log that loop visits
about 1 level on average at target size 1, 1.3 at 200 and 37 at 10000. The sorts below cost the
same at every target size, so they dominate.

**How does it scale with the number of orders?** Each message calls `get_expense` and `get_income`
twice, before and after the change. That is four full sorts of a side per message, so a message
costs O(n log n) in the number of resting orders n, and a log of m messages costs O(m n log n).
Memory is O(n), but the whole input is currently read before processing starts (#12). With a
price-level book (#10) a message would cost O(log L) to find its level among L levels, plus the
levels walked for the touched side.

## Known issues

The test suite pins each of these with a strict `xfail`, which fails once the defect is fixed so
the marker has to be removed. Fixes are tracked in issues #11 (CLI argument handling) and #12
(streaming).

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

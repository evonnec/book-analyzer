# System tests

A fully mocked system/integration suite: no real market data, only seeded synthetic logs and an
independent oracle. It runs the program two ways: in a real subprocess
(`python -m book_analyzer`, pipes, exit status) and in process through `book_analyzer.cli.run`.

## Pieces

- `system_gen.py`: `generate_market(seed, messages, ...)` makes a realistic log (2-decimal
  random-walk prices, about 200 live orders, about half adds and half reduces, most reduces
  remove the order, ids re-used after removal, ties at one price, occasional sweeps and big
  orders; `over_reduce_rate` adds reduces larger than the order). `inject_errors` inserts one
  line of every class in `BAD_LINE_CLASSES` (about 35: bad field counts, bad numbers, unknown
  side or type, zero or negative sizes and prices, `nan`/`inf`, `+1`, `1_0`, non-ASCII digits,
  duplicate live ids, reduces of unknown or removed ids, ...) at known positions.
- `system_oracle.py`: a brute-force reference of the specification with exact `Decimal` money,
  half-up rounding, the warn-and-skip policy, and "a total changes when its printed value
  changes". It shares no code with `src/` and is checked against the specification sample and
  hand-computed cases in `test_harness_selftest.py`.
- `system_run.py`: `run_subprocess`, `run_in_process` (passes an error stream if `run` accepts
  one, otherwise redirects `sys.stderr`, so it works before and after the #9 signature change)
  and `Child` for interactive tests (streaming, SIGINT).
- `system_cases.py`: sizes, cached logs and oracle results, and the `xfail` helper.

The helper modules are importable because `pyproject.toml` puts `tests/system` on pytest's
`pythonpath` (importlib mode and no `__init__.py` mean test modules cannot import each other).

## Running

    uv run pytest tests/system
    BOOK_ANALYZER_SYSTEM_SCALE=5 uv run pytest tests/system   # 5x longer generated logs

The default scale keeps the whole suite under about 15 seconds on the current (quadratic) code.
Work is checked by counting (`test_work_bound.py` wraps `sorted` in `book_analyzer.book`), not by
timing, so nothing here depends on machine speed.

## xfails and issues

Every known defect is a strict xfail whose reason starts with the GitHub issue number, for
example `#9: warnings are written to stdout`. A scenario that needs earlier fixes is tagged with
the last one in the fix order (#7, #8, #9, #10/#11/#12, then #14/#15) and says so:
`#9 (needs #7, #8)`. When a fix lands, its xfails turn into XPASS(strict), which fails the run:
delete the `xfail` marks tagged with that issue and the tests become regular tests.

    uv run pytest -rxX | grep '#7'      # what the dead-order fix should flip

| Issue | What is pinned |
| --- | --- |
| #7 | over-reduce and id re-use scenarios, generated markets at target 1, the sort-work bound |
| #8 | float noise, precision, overflow, sub-cent change rule, generated markets at targets 200 and 5000 |
| #9 | every class of bad line, BOM, undecodable bytes, injected generated logs |
| #10 | at most two sorts per message (only the touched side is recomputed) |
| #11 | argument matrix, `--help`, closed pipe, SIGINT |
| #12 | a result line arrives before stdin is closed (with `--line-buffered`) |
| #14 | rejected-message summary and `--strict` |
| #15 | the `BookAnalyzer` command name |

The #10, #12 and #14 tests assume the names given in the issues (`--line-buffered`, `--strict`,
a `rejected N` summary line on stderr, exit statuses 2, 130 and 141); adjust them if the
implementation settles on something else.

# System tests

A fully mocked system/integration suite: no real market data, only seeded synthetic logs and an
independent oracle. It runs the program two ways: in a real subprocess
(`python -m book_analyzer`, pipes, exit status) and in process through `book_analyzer.cli.run`.

## Pieces

- `system_gen.py`: `generate_market(seed, messages, ...)` makes a realistic log (2-decimal
  random-walk prices, about 200 live orders, about half adds and half reduces, a fifth of the
  messages in bursts at one timestamp, most reduces remove the order, ids re-used after removal
  (often on the other side), ties at one price, occasional sweeps and big orders;
  `over_reduce_rate` adds reduces larger than the order). `inject_errors` inserts one line of
  every class in `BAD_LINE_CLASSES` (about 35: bad field counts, bad numbers, unknown side or
  type, zero or negative sizes and prices, `nan`/`inf`, `+1`, `1_0`, non-ASCII digits,
  duplicate live ids, reduces of unknown or removed ids, ...) at known positions.
- `system_oracle.py`: a brute-force reference of the specification with exact `Decimal` money
  (unbounded precision, `Inexact` trapped), half-up rounding, the warn-and-skip policy, and "a
  total changes when its printed value changes". It shares no code with `src/` and is checked
  against the specification sample and hand-computed cases in `test_harness_selftest.py`. It
  was also checked, outside the repository, against the reference outputs (byte-identical on
  the full 1.19M-line file at targets 1, 200 and 10000) and against a separate stdlib oracle on
  generated and error-injected logs.
- `system_api.py`: adapters for the API details the fix issues change, so a fix PR only removes
  its `xfail` marks. `price("1.50")` is the package's own representation of a price (float
  today, an integer after #8) and `shown(total)` how a total prints; `rejects(line)` accepts
  both `parse_line` styles (None today, `MessageError` after #9); `call_run` passes an error
  stream to `run` only if it takes one (a parameter whose name contains "err" or "warn").
  The unit tests in `tests/` use them too.
- `system_run.py`: `run_subprocess`, `run_in_process` (through `call_run`) and `Child` for
  interactive tests (streaming, SIGINT). `CliResult.warning_lines` are the stderr lines that
  name an input line number, so a summary line (#14) is not counted but a traceback is.
- `system_cases.py`: sizes, cached logs and oracle results, and the `xfail` helper. Every
  cached market ends in a short "float trap" (see `float_trap`), so the #8 xfails of the
  generated markets do not depend on whether a random log happens to hit float noise.

The helper modules are importable because `pyproject.toml` puts `tests/system` on pytest's
`pythonpath` (importlib mode and no `__init__.py` mean test modules cannot import each other).

## Running

    uv run pytest tests/system
    BOOK_ANALYZER_SYSTEM_SCALE=5 uv run pytest tests/system   # 5x longer generated logs

The default scale keeps the whole suite under about 15 seconds on the current (quadratic) code.
Work is checked by counting, not by timing (`test_work_bound.py`): the objects the `Book`
keeps alive after a long replay (independent of how the book is built), and the elements
`sorted` is asked to sort (this one becomes vacuous once #10 stops calling `sorted`).

## xfails and issues

Every known defect is a strict xfail whose reason starts with the GitHub issue number, for
example `#9: warnings are written to stdout`. A scenario that needs earlier fixes is tagged with
the last one in the fix order (#7, #8, #9, #10/#11/#12, then #14) and says so:
`#9 (needs #7, #8)`. When a fix lands, its xfails turn into XPASS(strict), which fails the run:
delete the `xfail` marks tagged with that issue and the tests become regular tests.

    uv run pytest -rxX | grep '#7'      # what the dead-order fix should flip

Each step was checked against scratch implementations of the fixes, applied cumulatively in
the fix order: each step flips exactly the xfails tagged with its issue and breaks nothing else.

| Issue | xfails | What is pinned |
| --- | ---: | --- |
| #7 | 19 | over-reduce and id re-use scenarios, generated markets at target 1, the work bounds |
| #8 | 33 | float noise, precision, overflow, sub-cent change rule, half-up rounding, generated markets at targets 200 and 5000 |
| #9 | 101 | every class of bad line, BOM, undecodable bytes, injected generated logs |
| #10 | 1 | at most two sorts per message (only the touched side is recomputed) |
| #11 | 18 | argument matrix, `--help`, closed pipe, SIGINT |
| #12 | 2 | a result line arrives before stdin is closed (with `--line-buffered`) |
| #14 | 3 | rejected-message summary and `--strict` |

The CLI tests use what the issues specify: usage errors exit 2 with a usage message (#11),
`--line-buffered` (#12) and `--strict` exiting 1 (#14). Where an issue leaves a detail open the
tests accept the alternatives: exit status 141 or death by SIGPIPE, 130 or death by SIGINT
(the same to a shell); any summary wording that mentions the rejection and the count; a BOM on
line 1 stripped or rejected with a warning.

"""Reproducible synthetic benchmark: throughput and per-message latency.

    uv run python benchmarks/bench.py [--messages N] [--target T] [--seed S]

Stdlib only. A seeded generator makes a log that mimics a realistic book: about 200 live
orders, 2-decimal prices on a random walk, roughly half adds and half reduces, almost all
reduces removing their order, and ids never reused while live. The log is replayed through the
installed package (`parse_line`, `Book.apply` and `format_update`, the same steps as
`book_analyzer.cli.run`), timing every message.
"""

import argparse
import random
import statistics
import time
from collections.abc import Iterator
from dataclasses import dataclass

from book_analyzer.book import Book
from book_analyzer.cli import format_update, parse_line

LIVE_ORDERS = 200
FULL_REDUCE_PROBABILITY = 0.995


def generate(messages: int, seed: int) -> Iterator[str]:
    """Yield `messages` log lines; the same seed always gives the same lines."""
    rng = random.Random(seed)
    live: list[tuple[str, int]] = []  # (order id, size) of orders still resting
    mid = 5000  # cents
    timestamp = 28_800_000
    next_id = 0
    for _ in range(messages):
        timestamp += rng.randint(1, 50)
        mid = max(100, mid + rng.choice((-1, 0, 0, 1)))
        # Add while the book is thin; otherwise 50/50, which keeps depth near LIVE_ORDERS.
        if len(live) < LIVE_ORDERS // 2 or (len(live) < LIVE_ORDERS * 2 and rng.random() < 0.5):
            order_id = f"o{next_id:x}"
            next_id += 1
            size = max(1, round(rng.lognormvariate(4.6, 0.6)))  # median about 100
            offset = rng.randint(1, 40)
            if rng.random() < 0.5:
                side, price = "B", mid - offset
            else:
                side, price = "S", mid + offset
            live.append((order_id, size))
            yield f"{timestamp} A {order_id} {side} {price // 100}.{price % 100:02d} {size}"
        else:
            index = rng.randrange(len(live))
            order_id, size = live[index]
            if rng.random() < FULL_REDUCE_PROBABILITY or size == 1:
                live[index] = live[-1]
                live.pop()
                reduce_by = size
            else:
                reduce_by = rng.randint(1, size - 1)
                live[index] = (order_id, size - reduce_by)
            yield f"{timestamp} R {order_id} {reduce_by}"


@dataclass(frozen=True, slots=True)
class Result:
    """Timings of one replay; latencies are per message, in seconds."""

    messages: int
    elapsed: float
    latencies: list[float]
    output_lines: int

    @property
    def messages_per_second(self) -> float:
        return self.messages / self.elapsed

    def percentile(self, fraction: float) -> float:
        ordered = sorted(self.latencies)
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def benchmark(lines: list[str], target_size: int) -> Result:
    """Replay `lines` through the package, timing each message."""
    book = Book(target_size=target_size)
    latencies: list[float] = []
    output_lines = 0
    clock = time.perf_counter
    start = clock()
    for line in lines:
        begin = clock()
        message = parse_line(line)
        assert message is not None
        output_lines += len([format_update(update) for update in book.apply(message)])
        latencies.append(clock() - begin)
    elapsed = clock() - start
    return Result(len(lines), elapsed, latencies, output_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--messages", type=int, default=5000, help="messages to replay")
    parser.add_argument("--target", type=int, default=200, help="TARGET_SIZE")
    parser.add_argument("--seed", type=int, default=1, help="generator seed")
    args = parser.parse_args()

    lines = list(generate(args.messages, args.seed))
    result = benchmark(lines, args.target)
    print(f"messages={args.messages} target={args.target} seed={args.seed}")
    print(f"output lines:   {result.output_lines}")
    print(f"elapsed:        {result.elapsed:.3f} s")
    print(f"throughput:     {result.messages_per_second:,.0f} messages/s")
    print(f"latency mean:   {statistics.fmean(result.latencies) * 1e6:,.1f} us")
    print(f"latency p50:    {result.percentile(0.50) * 1e6:,.1f} us")
    print(f"latency p99:    {result.percentile(0.99) * 1e6:,.1f} us")
    print(f"latency max:    {max(result.latencies) * 1e6:,.1f} us")


if __name__ == "__main__":
    main()

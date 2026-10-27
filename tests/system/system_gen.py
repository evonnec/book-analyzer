"""Seeded synthetic market generator and error injector for the system tests.

Everything here is deterministic: the same arguments always give the same lines. The generator
only emits valid messages (per the specification); the injector inserts invalid ones at known
positions and reports where they are.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    """A generated log (one string per line, no newlines) and its peak live-order count."""

    lines: list[str]
    max_live: int

    @property
    def text(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


def cents(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def generate_market(
    seed: int,
    messages: int,
    *,
    live_target: int = 200,
    over_reduce_rate: float = 0.0,
    full_reduce_rate: float = 0.8,
) -> Market:
    """Generate `messages` valid messages for a market with about `live_target` live orders.

    Prices follow a 2-decimal random walk. Roughly half of the messages are adds and half are
    reduces, and about a fifth share the previous message's timestamp (bursts). Most reduces
    remove the order exactly, some are partial and, when `over_reduce_rate` > 0, some reduce
    by more than the remaining size (also a removal).
    Ids are re-used after removal, orders tie at the same price, and now and then the best
    order of a side is swept away or a very large order is added.
    """
    rng = random.Random(seed)
    live: dict[str, tuple[str, int, int]] = {}  # id -> (side, price in cents, size)
    live_ids: list[str] = []  # for O(1) random choice
    free_ids: list[str] = []
    next_id = 0
    timestamp = 28_800_000
    mid = 4400
    lines: list[str] = []
    max_live = 0

    def fresh_id() -> str:
        nonlocal next_id
        next_id += 1
        return format(next_id, "x") + rng.choice("abcdefgh")

    def remove(order_id: str) -> None:
        del live[order_id]
        live_ids.remove(order_id)
        free_ids.append(order_id)

    def pick_price(side: str) -> int:
        if rng.random() < 0.25 and live:
            same = [price for s, price, _ in live.values() if s == side]
            if same:
                return rng.choice(same)  # tie at an existing price
        ticks = 1 + int(rng.expovariate(0.45))
        if rng.random() < 0.01:
            ticks += rng.randint(20, 80)  # far from the touch
        price = mid - ticks if side == "B" else mid + ticks
        return max(price, 1)

    for _ in range(messages):
        if rng.random() < 0.8:  # otherwise a burst: the same timestamp as the last message
            timestamp += rng.randint(1, 500)
        mid = max(mid + rng.choice((-2, -1, 0, 0, 1, 2)), 50)
        add_probability = 0.56 if len(live) < live_target else 0.44
        if not live or rng.random() < add_probability:
            if free_ids and rng.random() < 0.4:
                order_id = free_ids.pop(rng.randrange(len(free_ids)))
            else:
                order_id = fresh_id()
            side = rng.choice("BS")
            size = rng.randint(1, 300)
            if rng.random() < 0.01:
                size = rng.randint(2000, 6000)  # a big order, for deep targets
            price = pick_price(side)
            live[order_id] = (side, price, size)
            live_ids.append(order_id)
            max_live = max(max_live, len(live))
            lines.append(f"{timestamp} A {order_id} {side} {cents(price)} {size}")
            continue
        if rng.random() < 0.05:  # sweep: remove the best order of a random side
            side = rng.choice("BS")
            best = [(price, order_id) for order_id, (s, price, _) in live.items() if s == side]
            if best:
                _, order_id = max(best) if side == "B" else min(best)
            else:
                order_id = rng.choice(live_ids)
        else:
            order_id = rng.choice(live_ids)
        remaining = live[order_id][2]
        roll = rng.random()
        if roll < over_reduce_rate:
            size = remaining + rng.randint(1, 50)
        elif roll < over_reduce_rate + full_reduce_rate or remaining == 1:
            size = remaining
        else:
            size = rng.randint(1, remaining - 1)
        lines.append(f"{timestamp} R {order_id} {size}")
        if size >= remaining:
            remove(order_id)
        else:
            side, price, _ = live[order_id]
            live[order_id] = (side, price, remaining - size)
    return Market(lines=lines, max_live=max_live)


@dataclass(frozen=True)
class Context:
    """State at an insertion point, so injected lines can refer to live/removed/unknown ids."""

    timestamp: str
    live: dict[str, str]  # live id -> side
    removed: list[str]  # ids removed and not currently live


ARABIC_INDIC_12 = chr(0x661) + chr(0x662)
FULLWIDTH_12 = chr(0xFF11) + chr(0xFF12)

BadFactory = Callable[[Context], str | None]

# Every class of erroneous message. A factory returns None when the context cannot host it.
BAD_LINE_CLASSES: dict[str, BadFactory] = {
    "blank": lambda c: "",
    "spaces only": lambda c: "   ",
    "too few fields": lambda c: f"{c.timestamp} A bad1",
    "add with trailing field": lambda c: f"{c.timestamp} A bad2 S 1.00 1 extra",
    "reduce with trailing field": lambda c: f"{c.timestamp} R bad3 1 1",
    "single token": lambda c: "garbage",
    "non-numeric add size": lambda c: f"{c.timestamp} A bad4 S 1.00 many",
    "non-numeric reduce size": lambda c: f"{c.timestamp} R bad5 many",
    "non-numeric price": lambda c: f"{c.timestamp} A bad6 S cheap 1",
    "unknown side": lambda c: f"{c.timestamp} A bad7 X 1.00 1",
    "unknown type, 6 fields": lambda c: f"{c.timestamp} Z bad8 S 1.00 1",
    "unknown type, 4 fields": lambda c: f"{c.timestamp} X bad9 1",
    "reduce with 6 fields": lambda c: f"{c.timestamp} R bad10 S 1.00 1",
    "add with 4 fields": lambda c: f"{c.timestamp} A bad11 5",
    "zero add size": lambda c: f"{c.timestamp} A bad12 S 1.00 0",
    "negative add size": lambda c: f"{c.timestamp} A bad13 S 1.00 -4",
    "zero reduce size": lambda c: _reduce_live(c, 0),
    "negative reduce size": lambda c: _reduce_live(c, -3),
    "nan price": lambda c: f"{c.timestamp} A bad14 S nan 1",
    "inf price": lambda c: f"{c.timestamp} A bad15 S inf 1",
    "negative price": lambda c: f"{c.timestamp} A bad16 B -1.00 1",
    "zero price": lambda c: f"{c.timestamp} A bad17 B 0.00 1",
    "non-integer timestamp": lambda c: "abc A bad18 S 1.00 1",
    "negative timestamp": lambda c: "-5 A bad19 S 1.00 1",
    "duplicate live id, same side": lambda c: _duplicate(c, same_side=True),
    "duplicate live id, other side": lambda c: _duplicate(c, same_side=False),
    "reduce of unknown id": lambda c: f"{c.timestamp} R neverseen 1",
    "reduce of removed id": lambda c: f"{c.timestamp} R {c.removed[-1]} 1" if c.removed else None,
    "plus sign in size": lambda c: f"{c.timestamp} A bad20 S 1.00 +1",
    "underscore in size": lambda c: f"{c.timestamp} A bad21 S 1.00 1_0",
    "underscore in price": lambda c: f"{c.timestamp} A bad22 S 1_0.00 1",
    "exponent in price": lambda c: f"{c.timestamp} A bad23 S 1e1 1",
    "fractional size": lambda c: f"{c.timestamp} A bad24 S 1.00 1.5",
    "non-ASCII digit in size": lambda c: f"{c.timestamp} A bad25 S 1.00 {ARABIC_INDIC_12}",
    "non-ASCII digit in timestamp": lambda c: f"{FULLWIDTH_12} A bad26 S 1.00 1",
}


def _reduce_live(context: Context, size: int) -> str | None:
    if not context.live:
        return None
    return f"{context.timestamp} R {next(iter(context.live))} {size}"


def _duplicate(context: Context, *, same_side: bool) -> str | None:
    if not context.live:
        return None
    order_id, side = next(iter(context.live.items()))
    new_side = side if same_side else ("S" if side == "B" else "B")
    return f"{context.timestamp} A {order_id} {new_side} 1.00 1"


@dataclass(frozen=True)
class Injected:
    """A log with bad lines inserted; `bad_lines` are 1-based physical line numbers."""

    lines: list[str]
    bad_lines: list[int]
    classes: list[str]

    @property
    def text(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


def inject_errors(
    clean: list[str],
    seed: int,
    *,
    count: int,
    classes: list[str] | None = None,
) -> Injected:
    """Insert `count` bad lines, cycling through `classes` (default: all) in a seeded order.

    Positions are chosen by the seed. A line is only inserted where its class can be built from
    the book state at that point (for example, "reduce of removed id" needs a removed id).
    """
    rng = random.Random(seed)
    names = list(BAD_LINE_CLASSES) if classes is None else classes
    wanted = [names[i % len(names)] for i in range(count)]
    rng.shuffle(wanted)
    positions = sorted(rng.randrange(len(clean) + 1) for _ in wanted)
    live: dict[str, str] = {}
    removed: list[str] = []
    out: list[str] = []
    bad_lines: list[int] = []
    used: list[str] = []
    pending = list(zip(positions, wanted, strict=True))
    last_ts = "1"

    def place(index: int) -> None:
        nonlocal pending
        while pending and pending[0][0] <= index:
            _, name = pending.pop(0)
            context = Context(timestamp=last_ts, live=live, removed=removed)
            line = BAD_LINE_CLASSES[name](context)
            if line is None:  # cannot build here: fall back to a class that always can
                name = "single token"
                line = BAD_LINE_CLASSES[name](context)
                assert line is not None
            out.append(line)
            bad_lines.append(len(out))
            used.append(name)

    sizes: dict[str, int] = {}
    for index, line in enumerate(clean):
        place(index)
        out.append(line)
        fields = line.split()
        last_ts = fields[0]
        order_id = fields[2]
        if fields[1] == "A":
            live[order_id] = fields[3]
            sizes[order_id] = int(fields[5])
            if order_id in removed:
                removed.remove(order_id)
        else:
            sizes[order_id] -= int(fields[3])
            if sizes[order_id] <= 0:
                del live[order_id], sizes[order_id]
                removed.append(order_id)
    place(len(clean))
    return Injected(lines=out, bad_lines=bad_lines, classes=used)

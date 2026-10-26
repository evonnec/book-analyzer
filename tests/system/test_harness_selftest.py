"""Self-tests of the harness: the oracle, the generator and the error injector.

These never run the program under test, so they pass today and guard the tools the other system
tests rely on.
"""

import re

import pytest
from system_cases import market
from system_gen import BAD_LINE_CLASSES, Context, generate_market, inject_errors
from system_oracle import oracle

BOM = chr(0xFEFF)


class TestOracle:
    def test_specification_sample(self, sample_input: str, sample_expected: str) -> None:
        result = oracle(sample_input, 200)
        assert result.stdout == sample_expected
        assert result.rejected == [1]  # the sample starts with a blank line

    def test_sample_without_blank_line(self, sample_input_clean: str, sample_expected: str) -> None:
        result = oracle(sample_input_clean, 200)
        assert result.stdout == sample_expected
        assert result.rejected == []

    def test_sample_with_crlf(self, sample_input_clean: str, sample_expected: str) -> None:
        assert oracle(sample_input_clean.replace("\n", "\r\n"), 200).stdout == sample_expected

    @pytest.mark.parametrize(
        ("log", "target", "expected"),
        [
            # An over-reduce removes the order (it does not leave a negative size behind).
            ("1 A a S 1.00 1\n2 R a 3\n3 A b S 2.00 5\n", 1, "1 B 1.00\n2 B NA\n3 B 2.00\n"),
            ("1 A a B 5.00 1\n2 R a 3\n3 A b B 4.00 5\n", 1, "1 S 5.00\n2 S NA\n3 S 4.00\n"),
            # A partial reduce keeps the order; an exact reduce removes it.
            ("1 A a S 1.00 3\n2 R a 1\n3 R a 2\n", 3, "1 B 3.00\n2 B NA\n"),
            # Asks are consumed lowest first, bids highest first.
            ("1 A a S 3.00 1\n2 A b S 1.00 1\n3 A c S 2.00 1\n", 2, "2 B 4.00\n3 B 3.00\n"),
            ("1 A a B 3.00 1\n2 A b B 1.00 1\n3 A c B 2.00 1\n", 2, "2 S 4.00\n3 S 5.00\n"),
            # Ties at one price, and a fill that stops partway through an order.
            ("1 A a S 1.00 2\n2 A b S 1.00 2\n", 3, "2 B 3.00\n"),
            ("1 A a S 1.50 10\n", 3, "1 B 4.50\n"),
            # Half-up rounding of exact ties, never half-even or binary float rounding.
            ("1 A a S 0.125 1\n", 1, "1 B 0.13\n"),
            ("1 A a S 0.015 1\n", 1, "1 B 0.02\n"),
            ("1 A a S 2.675 1\n", 1, "1 B 2.68\n"),
            ("1 A a S 0.014 1\n", 1, "1 B 0.01\n"),
            # A total changes when its printed value changes: 1.001 -> 1.002 prints once.
            ("1 A a S 1.001 1\n2 A b S 1.002 1\n3 R a 1\n", 1, "1 B 1.00\n"),
            # Exact arithmetic on huge numbers.
            (
                "1 A a S 99999999999.99 1000000000000\n",
                1000000000000,
                "1 B 99999999999990000000000.00\n",
            ),
            # An id may be re-used after removal, on either side.
            (
                "1 A a S 1.00 1\n2 R a 1\n3 A a B 2.00 1\n4 R a 1\n5 A a S 3.00 2\n6 R a 1\n",
                1,
                "1 B 1.00\n2 B NA\n3 S 2.00\n4 S NA\n5 B 3.00\n",
            ),
        ],
    )
    def test_hand_computed_cases(self, log: str, target: int, expected: str) -> None:
        result = oracle(log, target)
        assert result.stdout == expected
        assert result.rejected == []

    @pytest.mark.parametrize(
        ("log", "rejected"),
        [
            ("1 A a S 1.00 5\n2 R a 5\n3 R a 1\n4 A b S 2.00 2\n", [3]),
            ("1 A a S 1.00 5\n2 A a B 0.90 5\n", [2]),
            (f"{BOM}1 A a S 1.00 1\n", []),  # a BOM on line 1 is dropped
            (f"1 A a S 1.00 1\n{BOM}2 A b S 1.00 1\n", [2]),  # but only there
            ("1 A a S 1.00 1\t\r\n", []),
        ],
    )
    def test_rejections(self, log: str, rejected: list[int]) -> None:
        assert oracle(log, 1).rejected == rejected

    @pytest.mark.parametrize("name", list(BAD_LINE_CLASSES))
    def test_every_bad_class_is_rejected_and_changes_nothing(self, name: str) -> None:
        context = Context(timestamp="3", live={"a": "S"}, removed=["r"])
        bad = BAD_LINE_CLASSES[name](context)
        assert bad is not None
        prelude = "1 A a S 1.00 5\n2 A r B 2.00 1\n3 R r 1\n"
        with_bad = oracle(f"{prelude}{bad}\n5 A z B 3.00 2\n", 2)
        assert with_bad.rejected == [4]
        assert with_bad.stdout == oracle(f"{prelude}5 A z B 3.00 2\n", 2).stdout

    def test_rejected_message_leaves_the_state_alone(self) -> None:
        # The rejected add (id in use) must not replace the order or flip its side.
        result = oracle("1 A a S 1.00 1\n2 A a B 5.00 1\n3 R a 1\n", 1)
        assert result.stdout == "1 B 1.00\n3 B NA\n"
        assert result.rejected == [2]


class TestGenerator:
    def test_is_deterministic(self) -> None:
        assert generate_market(7, 500).lines == generate_market(7, 500).lines
        assert generate_market(7, 500).lines != generate_market(8, 500).lines

    def test_shape_of_a_market(self) -> None:
        log = market(1, 3000)
        adds = [line.split() for line in log.lines if " A " in line]
        reduces = [line.split() for line in log.lines if " R " in line]
        assert 0.4 < len(adds) / len(log.lines) < 0.6
        assert 150 <= log.max_live <= 300
        assert all(re.fullmatch(r"[0-9]+\.[0-9]{2}", fields[4]) for fields in adds)
        timestamps = [int(line.split()[0]) for line in log.lines]
        assert timestamps == sorted(timestamps)
        assert len({fields[2] for fields in adds}) < len(adds)  # ids are re-used
        prices = [(fields[3], fields[4]) for fields in adds]
        assert len(set(prices)) < len(prices)  # ties at one price
        assert len(reduces) > 1000

    def test_most_reduces_remove_the_order(self) -> None:
        sizes: dict[str, int] = {}
        removing = partial = 0
        for line in market(2, 3000).lines:
            fields = line.split()
            if fields[1] == "A":
                sizes[fields[2]] = int(fields[5])
            elif int(fields[3]) >= sizes[fields[2]]:
                removing += 1
                del sizes[fields[2]]
            else:
                partial += 1
                sizes[fields[2]] -= int(fields[3])
        assert removing > 2 * partial > 0

    def test_clean_logs_are_fully_accepted_by_the_oracle(self) -> None:
        assert oracle(market(3, 3000).text, 200).rejected == []

    def test_over_reduce_rate_adds_over_reduces(self) -> None:
        sizes: dict[str, int] = {}
        over = 0
        for line in market(4, 2000, 0.05).lines:
            fields = line.split()
            if fields[1] == "A":
                sizes[fields[2]] = int(fields[5])
            else:
                if int(fields[3]) > sizes[fields[2]]:
                    over += 1
                sizes[fields[2]] -= int(fields[3])
                if sizes[fields[2]] <= 0:
                    del sizes[fields[2]]
        assert over > 20


class TestInjector:
    def test_oracle_rejects_exactly_the_injected_lines(self) -> None:
        clean = market(5, 2000)
        injected = inject_errors(clean.lines, seed=1, count=120)
        assert len(injected.bad_lines) == 120
        assert set(injected.classes) == set(BAD_LINE_CLASSES)
        result = oracle(injected.text, 200)
        assert result.rejected == injected.bad_lines
        assert result.stdout == oracle(clean.text, 200).stdout

    def test_bad_lines_are_at_the_recorded_positions(self) -> None:
        clean = market(5, 300)
        injected = inject_errors(clean.lines, seed=2, count=20)
        survivors = [
            line
            for number, line in enumerate(injected.lines, 1)
            if number not in injected.bad_lines
        ]
        assert survivors == clean.lines

    def test_is_deterministic(self) -> None:
        clean = market(5, 300)
        assert inject_errors(clean.lines, 3, count=30) == inject_errors(clean.lines, 3, count=30)

    def test_restricted_classes(self) -> None:
        injected = inject_errors(market(5, 300).lines, 4, count=10, classes=["blank"])
        assert injected.classes == ["blank"] * 10
        assert [injected.lines[n - 1] for n in injected.bad_lines] == [""] * 10

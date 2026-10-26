"""Shared sizes and cached generated logs with their oracle results."""

import os
from functools import cache

import pytest
from system_gen import Market, generate_market
from system_oracle import OracleResult, oracle

SCALE = float(os.environ.get("BOOK_ANALYZER_SYSTEM_SCALE", "1"))

TARGETS = (1, 200, 5000)  # shallow, typical, deep (a sweep of a large part of the book)


def scaled(messages: int) -> int:
    """Scale a default message count by BOOK_ANALYZER_SYSTEM_SCALE."""
    return max(1, int(messages * SCALE))


@cache
def market(seed: int, messages: int, over_reduce_rate: float = 0.0) -> Market:
    return generate_market(seed, messages, over_reduce_rate=over_reduce_rate)


@cache
def expected(seed: int, messages: int, target: int, over_reduce_rate: float = 0.0) -> OracleResult:
    return oracle(market(seed, messages, over_reduce_rate).text, target)


def xfail(issue: str, why: str) -> pytest.MarkDecorator:
    """A strict xfail whose reason starts with the issue number, e.g. "#9: ...".

    Use "#9 (needs #7, #8)" as the issue when a scenario depends on earlier fixes: it is then
    expected to flip when the last of them lands.
    """
    return pytest.mark.xfail(strict=True, reason=f"{issue}: {why}")


# Generated markets re-use ids across sides after removal (needs #7: dead orders) and sum
# floats in a different order when the fill changes (needs #8: exact money). At target 1 no
# sum is ever taken, so only #7 stands in the way.
MARKET_MARKS = {
    1: xfail("#7", "removed orders stay in the book and shadow re-used ids"),
    200: xfail("#8 (needs #7)", "float totals print repeated lines"),
    5000: xfail("#8 (needs #7)", "float totals print repeated lines"),
}


def market_param(target: int) -> object:
    return pytest.param(target, marks=MARKET_MARKS[target], id=f"target{target}")

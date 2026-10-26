"""Smoke test so the benchmark script cannot rot."""

import importlib.util
from pathlib import Path
from types import ModuleType


def _load() -> ModuleType:
    path = Path(__file__).parent.parent / "benchmarks" / "bench.py"
    spec = importlib.util.spec_from_file_location("bench", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_is_deterministic() -> None:
    bench = _load()
    assert list(bench.generate(300, seed=3)) == list(bench.generate(300, seed=3))
    assert list(bench.generate(300, seed=3)) != list(bench.generate(300, seed=4))


def test_benchmark_runs() -> None:
    bench = _load()
    lines = list(bench.generate(400, seed=1))
    result = bench.benchmark(lines, target_size=50)
    assert result.messages == 400
    assert len(result.latencies) == 400
    assert result.messages_per_second > 0
    assert result.percentile(0.5) <= result.percentile(0.99) <= max(result.latencies)
    assert result.output_lines > 0

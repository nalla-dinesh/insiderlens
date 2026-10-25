"""Byte-identity determinism: same seed twice => identical CSV bytes."""

from __future__ import annotations

from generator.build import run_pipeline
from generator.config import GeneratorConfig
from generator.rng import make_rng
from generator.verify import CSV_FILES


def test_double_build_byte_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    cfg = GeneratorConfig()
    run_pipeline(cfg, a, write_report=False, quiet=True)
    run_pipeline(GeneratorConfig(), b, write_report=False, quiet=True)
    for name in CSV_FILES:
        ba = (a / f"{name}.csv").read_bytes()
        bb = (b / f"{name}.csv").read_bytes()
        assert ba == bb, f"{name}.csv differs between identical seeded builds"


def test_different_seed_differs(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    run_pipeline(GeneratorConfig(seed=42), a, write_report=False, quiet=True)
    run_pipeline(GeneratorConfig(seed=43), b, write_report=False, quiet=True)
    assert (a / "transactions.csv").read_bytes() != (b / "transactions.csv").read_bytes()


def test_rng_requires_seed():
    import pytest

    with pytest.raises(ValueError):
        make_rng(None)


def test_rng_sequence_stable():
    r1, r2 = make_rng(42), make_rng(42)
    assert (r1.random(10) == r2.random(10)).all()

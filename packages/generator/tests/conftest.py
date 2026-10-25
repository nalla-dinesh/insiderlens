"""Session fixture: build the full dataset ONCE into a tmp dir, then hand every
test the CSVs as pandas frames (end-to-end: tests read what the API will read).
"""

from __future__ import annotations

import pandas as pd
import pytest
from generator.build import run_pipeline
from generator.config import GeneratorConfig
from generator.verify import CSV_FILES


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> dict[str, pd.DataFrame]:
    out = tmp_path_factory.mktemp("dataset") / "generated"
    run_pipeline(GeneratorConfig(), out, write_report=False, quiet=True)
    frames = {}
    for name in CSV_FILES:
        df = pd.read_csv(out / f"{name}.csv")
        if name in ("transactions", "activity_log"):
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        frames[name] = df
    frames["_out_dir"] = out  # type: ignore[assignment]
    return frames

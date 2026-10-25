"""`python -m generator verify` — two checks, exit 2 on failure:
  1. every CSV in out/ matches its sha256 recorded in meta.json (truncation detection),
  2. a full REBUILD to a temp directory is byte-identical (determinism proof).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from generator.config import GeneratorConfig

CSV_FILES = ["roles", "employees", "customers", "accounts",
             "transactions", "activity_log", "ground_truth"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def verify(out_dir: Path) -> list[str]:
    from generator.build import run_pipeline  # local import avoids a cycle

    lines: list[str] = []
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"{meta_path} missing — run `python -m generator build` first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # 1) checksum integrity of what's on disk
    for name in CSV_FILES:
        path = out_dir / f"{name}.csv"
        got = _sha256(path)
        want = meta["files"][name]["sha256"]
        if got != want:
            raise ValueError(f"{name}.csv checksum mismatch (modified or truncated?)")
    lines.append(f"Checksums OK: {len(CSV_FILES)} CSVs match meta.json")

    # 2) determinism: rebuild elsewhere, byte-compare
    cfg = GeneratorConfig(seed=meta["seed"], days=meta["days"],
                          start_date=meta["start_date"])
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "generated"
        run_pipeline(cfg, tmp_out, write_report=False, quiet=True)
        for name in CSV_FILES:
            a = (out_dir / f"{name}.csv").read_bytes()
            b = (tmp_out / f"{name}.csv").read_bytes()
            if a != b:
                raise ValueError(f"{name}.csv differs on rebuild — generator is NOT deterministic")
    lines.append(f"Determinism OK: identical rebuild for seed={meta['seed']}, "
                 f"days={meta['days']}, since {meta['start_date']}")
    lines.append("Verify complete: dataset is complete, consistent, reproducible.")
    return lines

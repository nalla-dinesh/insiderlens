"""Build orchestration. Pipeline order (order IS part of determinism):

    roles -> employees -> npc pool -> S1..S7 -> baseline population fill
          -> L1..L5  -> baseline txns -> baseline activity
          -> close last_active -> quality gate -> write CSVs -> meta.json -> report
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from generator import baseline_activity, baseline_txns, entities, report
from generator.config import GeneratorConfig
from generator.rng import make_rng
from generator.scenarios import legitimate, suspicious
from generator.types import GenCtx
from generator.verify import CSV_FILES


@dataclass
class BuildSummary:
    out_dir: Path
    counts: dict[str, int]
    quality_passed: int
    quality_total: int


def _serialize_for_csv(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for name, df in frames.items():
        df = df.copy()
        for col in df.columns:
            if name in ("transactions", "activity_log") and col == "ts":
                df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if name == "activity_log":
            df["details"] = df["details"].map(lambda d: json.dumps(d, sort_keys=True))
            df["target_acc"] = df["target_acc"].astype("Int64")   # NA stays empty, no float drift
        if name == "transactions":
            df["approved_by"] = df["approved_by"].astype("Int64")
        out[name] = df
    return out


def _write_frames(frames: dict[str, pd.DataFrame], out_dir: Path) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for name in CSV_FILES:
        df = _serialize_for_csv(frames)[name]
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False, lineterminator="\n", float_format="%.2f",
                  encoding="utf-8")
        meta[name] = {"rows": len(df), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return meta


def run_pipeline(cfg: GeneratorConfig, out_dir: Path, *,
                 write_report: bool = True, quiet: bool = False) -> BuildSummary:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ctx = GenCtx(cfg, make_rng(cfg.seed))

    entities.build_roles(ctx)
    entities.build_employees(ctx)
    entities.build_npc_pool(ctx)
    suspicious.inject_all(ctx)
    pop = entities.fill_baseline_population(ctx)
    legitimate.inject_all(ctx, pop["personal"])
    tx_counts = baseline_txns.build(ctx, pop)
    act_counts = baseline_activity.build(ctx, pop)

    frames = ctx.frames()
    ctx.close_last_active(frames)

    from generator import quality  # local import: quality inspects ctx + frames
    q = quality.run(cfg, frames, ctx)  # raises before ANY file is written

    files_meta = _write_frames(frames, Path(out_dir))
    meta = {
        "seed": cfg.seed, "days": cfg.days, "start_date": cfg.start_date.isoformat(),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": files_meta,
    }
    (Path(out_dir) / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if write_report:
        docs = Path(out_dir).resolve().parent.parent / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "DATA_REPORT.md").write_text(
            report.render(cfg, frames, q, ctx.proofs, tx_counts, act_counts),
            encoding="utf-8",
        )

    total = len(q.assertions) + len(q.global_checks)
    passed = sum(1 for _, ok, _ in q.assertions + q.global_checks if ok)
    if not quiet:
        for name in CSV_FILES:
            print(f"  wrote {name}.csv ({files_meta[name]['rows']:,} rows)")
        print(f"  quality gate: {passed}/{total} checks passed, 0 failures")
        print(f"  ground truth: {len(frames['ground_truth'])} rows across "
              f"{frames['ground_truth']['scenario_id'].nunique()} scenarios")
    return BuildSummary(Path(out_dir), {n: files_meta[n]["rows"] for n in CSV_FILES},
                        passed, total)

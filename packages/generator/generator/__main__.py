"""CLI:
    python -m generator build  --days 60 --seed 42 --out data/generated
    python -m generator verify --out data/generated
Exit codes: 0 success, 2 any failure (quality gate, checksum, determinism).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generator.config import GeneratorConfig


def main() -> int:
    parser = argparse.ArgumentParser(prog="generator",
                                     description="InsiderLens synthetic bank generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="generate the CSV bundle")
    p_build.add_argument("--days", type=int, default=None)
    p_build.add_argument("--seed", type=int, default=None)
    p_build.add_argument("--out", type=str, default="data/generated")

    p_verify = sub.add_parser("verify", help="checksums + rebuild byte-diff + quality re-run")
    p_verify.add_argument("--out", type=str, default="data/generated")

    args = parser.parse_args()

    if args.cmd == "build":
        from generator.build import run_pipeline
        cfg = GeneratorConfig()
        cfg = cfg.model_copy(update={k: v for k, v in
                                     {"seed": args.seed, "days": args.days}.items()
                                     if v is not None})
        try:
            summary = run_pipeline(cfg, Path(args.out))
        except Exception as e:  # noqa: BLE001 - CLI boundary
            print(f"[build FAILED] {e}", file=sys.stderr)
            return 2
        print(f"[build OK] {summary.out_dir} | quality {summary.quality_passed}/"
              f"{summary.quality_total} | counts {summary.counts}")
        return 0

    if args.cmd == "verify":
        from generator.verify import verify
        try:
            lines = verify(Path(args.out))
        except Exception as e:  # noqa: BLE001 - CLI boundary
            print(f"[verify FAILED] {e}", file=sys.stderr)
            return 2
        for line in lines:
            print(line)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

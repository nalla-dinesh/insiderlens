"""Architecture guard (Phase-07 spec §3): the detection engine must be
*provably blind* to ground truth. This test AST-scans every file under
app/engine/ and fails if any import reaches the ground-truth repository,
model, or the evaluation harness. Direct string search would miss aliased
imports (`from app.models import ground_truth as gt`), so we walk the real
import tree at module level.
"""

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / "app" / "engine"
FORBIDDEN_SUBSTRINGS = ("ground_truth", "ground.truth", "evaluation")


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def test_engine_never_imports_ground_truth_or_evaluation() -> None:
    offenders: list[str] = []
    assert ENGINE_DIR.exists(), f"engine dir missing: {ENGINE_DIR}"
    for py in sorted(ENGINE_DIR.rglob("*.py")):
        for mod in _imports_of(py):
            low = mod.lower()
            if any(frag in low for frag in FORBIDDEN_SUBSTRINGS):
                offenders.append(f"{py.name} -> {mod}")
    assert not offenders, "\n".join(offenders)

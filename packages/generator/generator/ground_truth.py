"""Ground-truth file — the ONLY place scenario membership is recorded.

One row per (scenario, entity). `entity_ids` string column holds ONE id per row;
array semantics are recovered by grouping on (scenario_id, entity_type).
Read by EvaluationService ONLY (blindness law).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class GtBuilder:
    rows: list[dict] = field(default_factory=list)
    _next: int = 1

    def add(self, scenario_id: str, entity_type: str, entity_ids: Iterable[int] | int,
            is_suspicious: bool) -> None:
        if isinstance(entity_ids, (int, np.integer)):
            entity_ids = [int(entity_ids)]
        for eid in sorted(int(e) for e in entity_ids):
            self.rows.append({
                "gt_id": self._next,
                "scenario_id": scenario_id,
                "entity_type": entity_type,        # ACCOUNT | CUSTOMER | EMPLOYEE
                "entity_ids": str(eid),
                "is_suspicious": bool(is_suspicious),
            })
            self._next += 1

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.rows,
            columns=["gt_id", "scenario_id", "entity_type", "entity_ids", "is_suspicious"],
        )

"""Quality gate — runs AFTER all builders, BEFORE any file is written.

Three layers, all hard-fail:
  1. every scenario's own assertion (re-derived from the frames),
  2. global volume envelopes + referential integrity,
  3. the blindness law: GT vocabulary must not leak into operational frames.
Build exits 2 with a named list of violations on any failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from generator.config import GeneratorConfig


class QualityError(RuntimeError):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("Dataset quality gate FAILED:\n  - " + "\n  - ".join(failures))


@dataclass
class QualityReport:
    assertions: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, ok, err)
    global_checks: list[tuple[str, bool, str]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def add_assert(self, name: str, err: str = "") -> None:
        self.assertions.append((name, err == "", err))
        if err:
            self.failures.append(f"[scenario assertion] {name}: {err}")

    def add_global(self, name: str, ok: bool, err: str = "") -> None:
        self.global_checks.append((name, ok, err if not ok else ""))
        if not ok:
            self.failures.append(f"[global] {name}: {err}")


def run(cfg: GeneratorConfig, frames: dict[str, pd.DataFrame], ctx) -> QualityReport:
    r = QualityReport()

    # --- layer 1: scenario assertions ---
    for name, fn in ctx.assertions:
        try:
            fn(frames)
            r.add_assert(name)
        except AssertionError as e:
            r.add_assert(name, str(e) or "assertion failed")
        except Exception as e:  # noqa: BLE001 - any crash here is a build failure
            r.add_assert(name, f"{type(e).__name__}: {e}")

    # --- layer 2: volumes + integrity ---
    tx, logs = frames["transactions"], frames["activity_log"]
    acc, cust = frames["accounts"], frames["customers"]
    emp, gt = frames["employees"], frames["ground_truth"]

    r.add_global("customers_total", len(cust) == cfg.volumes.customers_total,
                 f"{len(cust)} != {cfg.volumes.customers_total}")
    r.add_global("accounts_total", len(acc) == cfg.volumes.accounts_total,
                 f"{len(acc)} != {cfg.volumes.accounts_total}")
    r.add_global("employees_total", len(emp) == cfg.volumes.employees_total,
                 f"{len(emp)} != {cfg.volumes.employees_total}")
    r.add_global("txn_envelope", cfg.volumes.txn_min <= len(tx) <= cfg.volumes.txn_max,
                 f"{len(tx)} outside [{cfg.volumes.txn_min}, {cfg.volumes.txn_max}]")
    r.add_global("activity_envelope",
                 cfg.volumes.activity_min <= len(logs) <= cfg.volumes.activity_max,
                 f"{len(logs)} outside [{cfg.volumes.activity_min}, {cfg.volumes.activity_max}]")

    acc_ids, cust_ids, emp_ids = set(acc["acc_id"]), set(cust["cust_id"]), set(emp["emp_id"])
    r.add_global("fk_txn_accounts",
                 set(tx["from_acc"]) <= acc_ids and set(tx["to_acc"]) <= acc_ids,
                 "transaction references unknown account")
    r.add_global("fk_account_customer", set(acc["cust_id"]) <= cust_ids,
                 "account references unknown customer")
    r.add_global("fk_log_employee", set(logs["emp_id"]) <= emp_ids,
                 "activity log references unknown employee")
    r.add_global("fk_txn_approver",
                 set(tx["approved_by"].dropna().astype(int)) <= emp_ids,
                 "transaction references unknown approver")

    gt_acc = set(gt.loc[gt["entity_type"] == "ACCOUNT", "entity_ids"].astype(int))
    gt_cust = set(gt.loc[gt["entity_type"] == "CUSTOMER", "entity_ids"].astype(int))
    gt_emp = set(gt.loc[gt["entity_type"] == "EMPLOYEE", "entity_ids"].astype(int))
    r.add_global("gt_account_ids_exist", gt_acc <= acc_ids, f"ghost gt accounts {gt_acc - acc_ids}")
    r.add_global("gt_customer_ids_exist", gt_cust <= cust_ids, f"ghost gt customers {gt_cust - cust_ids}")
    r.add_global("gt_employee_ids_exist", gt_emp <= emp_ids, f"ghost gt employees {gt_emp - emp_ids}")
    scenarios_found = set(gt["scenario_id"])
    expected = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "L1", "L2", "L3", "L4", "L5"}
    r.add_global("gt_all_scenarios_present", scenarios_found == expected,
                 f"missing {sorted(expected - scenarios_found)}")

    # --- layer 3: blindness law ---
    gt_vocab = {"scenario_id", "is_suspicious", "gt_id"}
    for name, fr in frames.items():
        if name == "ground_truth":
            continue
        leak = gt_vocab & set(fr.columns)
        r.add_global(f"blindness_{name}", not leak, f"GT columns leaked into {name}: {leak}")

    if r.failures:
        raise QualityError(r.failures)
    return r

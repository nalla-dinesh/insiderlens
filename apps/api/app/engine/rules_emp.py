"""E1-E5 insider rules — pure functions over EngineFrames (activity world).

Laws (same as T-rules): thresholds ONLY from RulesConfig; engine re-derives
everything from first principles (off_hours / role_violation CSV flags are
generator hints and are NEVER trusted — IST window and roles table decide).

IST note: timestamps are stored tz-aware UTC; IST = UTC + 5:30, fixed (no DST),
so A literal wall-clock comparison works without a tz db dependency.

Every E-hit evidence carries:
  rows        — the log rows themselves (trimmed to 50): receipts
  records     — {"log_ids": [...]} (evidence/timeline contract)
  gates       — [{"key", "observed", "limit"}] with rules.yaml pointers
plus first_ts / last_ts on the hit for merger/fusion gluing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.graph import EngineFrames
from app.engine.types import RuleHit
from app.services.rules_config import RulesConfig

IST = pd.Timedelta(hours=5, minutes=30)
DAY = pd.Timedelta(days=1)


def _rows_evidence(df: pd.DataFrame, cap: int = 50) -> tuple[list[dict], list[int]]:
    """Receipts for evidence + record ids."""
    df = df.sort_values("ts")
    rows = []
    for r in df.head(cap).itertuples():
        ist = r.ts + IST
        rows.append(
            {
                "log_id": int(r.log_id),
                "emp_id": int(r.emp_id),
                "ts": r.ts.isoformat(),
                "ist_clock": ist.strftime("%Y-%m-%d %H:%M"),
                "ist_hour": int(ist.hour),
                "action": str(r.action),
                "target_acc": int(r.target_acc) if pd.notna(r.target_acc) else None,
            }
        )
    return rows, [int(v) for v in df["log_id"]]


def _hit(
    cfg: RulesConfig,
    rid: str,
    entities: list[int],
    title: str,
    summary: str,
    evidence: dict,
    span: tuple[pd.Timestamp, pd.Timestamp],
) -> RuleHit:
    return RuleHit(
        rule_id=rid,  # type: ignore[arg-type]
        entity_ids=sorted(set(int(e) for e in entities)),
        base_points=cfg.scoring.base_points[rid],
        title=title,
        summary=summary,
        evidence=evidence,
        first_ts=span[0].to_pydatetime(),
        last_ts=span[1].to_pydatetime(),
    )


# ----------------------------------------------------------------------------- E1
def e1_offhours(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """Sensitive actions inside the IST night window, one hit per (emp, night).

    'Night' is a wall-clock window: rows in [22:00, 06:00) belong to the evening
    date that STARTS the window (a 01:30 row counts for the previous evening).
    """
    p = cfg.thresholds.e1_offhours
    log = frames.activity
    sensitive = set(p.sensitive_actions)
    ist = log["ts"] + IST
    night = log[(ist.dt.hour >= p.night_start_hour_ist) | (ist.dt.hour < p.night_end_hour_ist)]
    night = night[night["action"].isin(sensitive)]
    if night.empty:
        return []

    ist_n = night["ts"] + IST
    win_date = ist_n.dt.normalize().where(ist_n.dt.hour >= p.night_end_hour_ist, ist_n.dt.normalize() - DAY)
    work = night.assign(win_date=win_date)
    hits: list[RuleHit] = []
    for (emp, wd), grp in work.groupby(["emp_id", "win_date"], sort=True):
        rows, log_ids = _rows_evidence(grp)
        accs = [int(a) for a in grp["target_acc"].dropna().unique()]
        span = (grp["ts"].min(), grp["ts"].max())
        acts = sorted(grp["action"].unique())
        hits.append(
            _hit(
                cfg,
                "E1",
                [int(emp), *accs],
                "Off-hours sensitive operations",
                f"Employee {int(emp)} ran {len(grp)} sensitive action(s) "
                f"({', '.join(acts)}) in the {p.night_start_hour_ist:02d}:00-"
                f"{p.night_end_hour_ist:02d}:00 IST night window on {wd.date()}.",
                {
                    "emp_id": int(emp),
                    "night_of": str(wd.date()),
                    "rows": rows,
                    "records": {"log_ids": log_ids},
                    "gates": [
                        {
                            "key": "e1_offhours.window_ist",
                            "observed": f"{p.night_start_hour_ist:02d}:00-{p.night_end_hour_ist:02d}:00",
                            "limit": "inside window",
                            "source": "rules.yaml",
                        }
                    ],
                },
                span,
            )
        )
    return hits


# ----------------------------------------------------------------------------- E2
def e2_rbac(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """Action outside the employee's role permissions (derived from roles table).
    One hit per (emp, IST day) — the day is the wearable evidence unit."""
    log = frames.activity
    if log.empty or frames.employees.empty or frames.roles.empty:
        return []
    perms = frames.role_perms()
    role_of = frames.emp_role()
    ist = (log["ts"] + IST).dt.normalize()
    work = log.assign(ist_day=ist)
    hits: list[RuleHit] = []
    for (emp, day), grp in work.groupby(["emp_id", "ist_day"], sort=True):
        role = role_of.get(int(emp))
        allowed = perms.get(role, set())
        bad = grp[~grp["action"].isin(allowed)]
        if bad.empty:
            continue
        rows, log_ids = _rows_evidence(bad)
        accs = [int(a) for a in bad["target_acc"].dropna().unique()]
        span = (bad["ts"].min(), bad["ts"].max())
        missing = sorted(set(bad["action"]))
        hits.append(
            _hit(
                cfg,
                "E2",
                [int(emp), *accs],
                "RBAC violation",
                f"Employee {int(emp)} ({role}) performed {len(bad)} action(s) outside "
                f"the {role} permission set on {day.date()}: {', '.join(missing)}.",
                {
                    "emp_id": int(emp),
                    "role": role,
                    "day": str(day.date()),
                    "missing_actions": missing,
                    "role_allowed_actions": sorted(allowed),
                    "rows": rows,
                    "records": {"log_ids": log_ids},
                    "gates": [
                        {
                            "key": "roles.allowed_actions",
                            "observed": ", ".join(missing),
                            "limit": f"role {role} allows {len(allowed)} actions",
                            "source": "roles table",
                        }
                    ],
                },
                span,
            )
        )
    return hits


# ----------------------------------------------------------------------------- E3
def e3_spike(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """VIEW_ACCOUNT day-count spike vs personal 30d median AND same-role peer median.
    BOTH baselines must be beaten; min_day_count guards degenerate 0-median baselines."""
    p = cfg.thresholds.e3_spike
    log = frames.activity
    if log.empty or frames.employees.empty:
        return []
    views = log[log["action"] == "VIEW_ACCOUNT"].copy()
    if views.empty:
        return []
    views = views.assign(ist_day=(views["ts"] + IST).dt.normalize())
    counts = views.groupby(["emp_id", "ist_day"], sort=True).size().rename("cnt").reset_index()

    role_of = frames.emp_role()
    # peers' median: per (role, day) first, then median of those day-counts
    counts["role"] = counts["emp_id"].map(role_of)
    peer_day = counts.groupby(["role", "ist_day"], sort=True)["cnt"].median()
    pmed = counts.groupby("emp_id")["cnt"].median()

    hits: list[RuleHit] = []
    for row in counts.itertuples():
        emp, cnt = int(row.emp_id), int(row.cnt)
        pm = float(pmed.get(emp, 0.0))
        rm = float(peer_day.get((role_of.get(emp), row.ist_day), 0.0))
        if cnt < p.min_day_count:
            continue
        if not (cnt > p.personal_multiple * pm and cnt > p.peer_multiple * rm):
            continue
        grp = views[(views["emp_id"] == emp) & (views["ist_day"] == row.ist_day)]
        rows, log_ids = _rows_evidence(grp)
        span = (grp["ts"].min(), grp["ts"].max())
        hits.append(
            _hit(
                cfg,
                "E3",
                [emp],
                "Bulk-access spike",
                f"Employee {emp} viewed {cnt} accounts on {row.ist_day.date()} — "
                f"{cnt / max(pm, 1e-9):.1f}x their own {p.lookback_days}d median "
                f"({pm:.1f}) and {cnt / max(rm, 1e-9):.1f}x the {role_of.get(emp)} peer "
                f"median ({rm:.1f}).",
                {
                    "emp_id": emp,
                    "day": str(row.ist_day.date()),
                    "day_count": cnt,
                    "personal_median": pm,
                    "peer_median": rm,
                    "role": role_of.get(emp),
                    "rows": rows,
                    "records": {"log_ids": log_ids},
                    "gates": [
                        {
                            "key": "e3_spike.personal_multiple",
                            "observed": round(cnt / max(pm, 1e-9), 2),
                            "limit": p.personal_multiple,
                            "source": "rules.yaml",
                        },
                        {
                            "key": "e3_spike.peer_multiple",
                            "observed": round(cnt / max(rm, 1e-9), 2),
                            "limit": p.peer_multiple,
                            "source": "rules.yaml",
                        },
                    ],
                },
                span,
            )
        )
    return hits


# ----------------------------------------------------------------------------- E4
def e4_highrisk(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """High-risk config change on an account — one hit per (emp, acc, IST day)."""
    p = cfg.thresholds.e4_highrisk
    log = frames.activity
    hi = log[log["action"].isin(p.actions)]
    if hi.empty:
        return []
    ist = (hi["ts"] + IST).dt.normalize()
    work = hi.assign(ist_day=ist)
    hits: list[RuleHit] = []
    for (emp, acc, day), grp in work.groupby(["emp_id", "target_acc", "ist_day"], sort=True):
        rows, log_ids = _rows_evidence(grp)
        span = (grp["ts"].min(), grp["ts"].max())
        acts = sorted(grp["action"].unique())
        drops = []
        for r in grp.head(10).itertuples():
            d = r.details or {}
            drops.append(
                {
                    "log_id": int(r.log_id),
                    "action": str(r.action),
                    **{k: d[k] for k in ("old", "new", "field", "new_daily_limit") if k in d},
                }
            )
        hits.append(
            _hit(
                cfg,
                "E4",
                [int(emp), int(acc)],
                "High-risk config change",
                f"Employee {int(emp)} made {len(grp)} config change(s) "
                f"({', '.join(acts)}) on account {int(acc)} on {day.date()}.",
                {
                    "emp_id": int(emp),
                    "account": int(acc),
                    "day": str(day.date()),
                    "changes": drops,
                    "rows": rows,
                    "records": {"log_ids": log_ids},
                    "gates": [
                        {
                            "key": "e4_highrisk.actions",
                            "observed": ", ".join(acts),
                            "limit": ", ".join(p.actions),
                            "source": "rules.yaml",
                        }
                    ],
                },
                span,
            )
        )
    return hits


# ----------------------------------------------------------------------------- E5
def e5_burst(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """>= min_actions sensitive actions within window_hours by one employee.
    Canonical-window policy (same as T3): first fully-valid window starting at
    each qualifying start-row, then skip rows inside that window — no near-dup hits."""
    p = cfg.thresholds.e5_burst
    sensitive = set(cfg.thresholds.e1_offhours.sensitive_actions)
    window_ns = int(p.window_hours * 3_600_000_000_000)
    hits: list[RuleHit] = []

    for emp, grp in frames.activity.groupby("emp_id", sort=True):
        rows = grp[grp["action"].isin(sensitive)].sort_values("ts")
        if len(rows) < p.min_actions:
            continue
        arr_ts = rows["ts"].to_numpy(dtype="datetime64[ns]")
        i = 0
        n = len(arr_ts)
        while i <= n - p.min_actions:
            j = int(np.searchsorted(arr_ts, arr_ts[i] + np.timedelta64(window_ns, "ns"), side="right"))
            if j - i < p.min_actions:
                i += 1
                continue
            w = rows.iloc[i:j]
            ev_rows, log_ids = _rows_evidence(w)
            accs = [int(a) for a in w["target_acc"].dropna().unique()]
            span = (w["ts"].min(), w["ts"].max())
            hits.append(
                _hit(
                    cfg,
                    "E5",
                    [int(emp), *accs],
                    "Sensitive action burst",
                    f"Employee {int(emp)} fired {len(w)} sensitive actions in "
                    f"{p.window_hours}h (window {span[0].isoformat()} → "
                    f"{span[1].isoformat()}).",
                    {
                        "emp_id": int(emp),
                        "rows": ev_rows,
                        "records": {"log_ids": log_ids},
                        "gates": [
                            {
                                "key": "e5_burst.min_actions",
                                "observed": len(w),
                                "limit": p.min_actions,
                                "source": "rules.yaml",
                            }
                        ],
                    },
                    span,
                )
            )
            i = j  # canonical: skip covered rows
        # end while
    return hits

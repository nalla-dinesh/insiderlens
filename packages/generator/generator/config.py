"""Generator configuration — every number that shapes the fake bank lives here.

Mirrors the blueprint §3.2. Scenario parameters are deliberately centralised so
that tests import them instead of duplicating constants.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class VolumeBudget(BaseModel):
    customers_total: int = 800
    accounts_total: int = 850
    employees_total: int = 25
    npc_pool_size: int = 52            # shared shell counterparties (40 persons + 12 biz)
    txn_min: int = 45_000
    txn_max: int = 55_000
    activity_min: int = 6_000
    activity_max: int = 14_000


class BaselineBudget(BaseModel):
    merchant_txns: int = 28_000        # retail/merchant payments
    p2p_txns: int = 16_000             # person-to-person transfers
    recurring_customers: int = 450     # rent/EMI/utilities payers
    second_accounts: int = 36          # extra SAVINGS accounts on random persons
    dormant_fraction: float = 0.05     # of eligible personal accounts
    merchants_min: int = 60
    corporates_min: int = 15           # payroll sources (12 actually pay)


class ScenarioParams(BaseModel):
    # --- suspicious ---
    s1: dict = Field(default_factory=lambda: {
        "hops": 4, "seed_amount": 950_000.0, "cut_min": 0.04, "cut_max": 0.06,
        "start_day": 20, "max_span_days": 10,
    })
    s2: dict = Field(default_factory=lambda: {
        "hops": 3, "amounts": [48_500.0, 47_800.0, 47_200.0], "start_day": 33, "gap_days": [0, 2, 5],
    })
    s3: dict = Field(default_factory=lambda: {
        "mules": 7, "deposits": 17, "deposits_lo": 45_000.0, "deposits_hi": 49_500.0,
        "window_days": 5, "start_day": 40, "bulk_out_amount": 860_000.0, "bulk_out_day": 47,
    })
    s4: dict = Field(default_factory=lambda: {
        "accounts": 2, "occurrences": 5, "forward_ratio_lo": 0.88, "forward_ratio_hi": 0.96,
        "lag_hours_max": 20, "days": [8, 13, 19, 26, 33],
        "inflow_amounts": [120_000.0, 95_000.0, 140_000.0, 78_000.0, 132_000.0],
    })
    s5: dict = Field(default_factory=lambda: {
        "employee": 1017, "night_day": 45,
        "cycle_seed": 600_000.0, "cut": 0.04, "cycle_days": [47, 48, 49],
    })
    s6: dict = Field(default_factory=lambda: {
        "dormant_days": 240, "inflow_day": 41, "inflows": [500_000.0, 460_000.0],
        "out_amounts": [210_000.0, 180_000.0, 160_000.0, 150_000.0, 130_000.0, 100_000.0],
        "out_days": [42, 42, 43, 43, 44, 44],
    })
    s7: dict = Field(default_factory=lambda: {
        "income": 35_000.0, "credits": 8, "credit_lo": 300_000.0, "credit_hi": 400_000.0,
        "days": [15, 18, 22, 26, 30, 34, 39, 44],
    })
    # --- legitimate traps ---
    l1: dict = Field(default_factory=lambda: {"employees_paid": 60, "day": 31, "hour": 9.667})
    l2: dict = Field(default_factory=lambda: {
        "base_amount": 220_000.0, "variance": 0.35,
        "loops": [(3, 8, 25), (30, 38, 55)],   # (dayAB, dayBC, dayCA) per loop
    })
    l3: dict = Field(default_factory=lambda: {"amount": 4_500_000.0, "day": 50, "income": 300_000.0})
    l4: dict = Field(default_factory=lambda: {
        # inflow hours baked into injector: 20:00, 21:00, 10:00. Only the middle
        # credit sits within the 48h forward window of the hospital payment.
        "in_amounts": [200_000.0, 180_000.0, 220_000.0], "in_days": [25, 26, 26],
        "out_amount": 580_000.0, "out_day": 28,
    })
    l5: dict = Field(default_factory=lambda: {"bonuses": 40, "day": 52, "hour": 20.25})


class GeneratorConfig(BaseModel):
    seed: int = 42
    days: int = 60
    start_date: date = date(2026, 7, 1)   # covers two month-start salary pulses
    volumes: VolumeBudget = Field(default_factory=VolumeBudget)
    baseline: BaselineBudget = Field(default_factory=BaselineBudget)
    scenarios: ScenarioParams = Field(default_factory=ScenarioParams)

    # global review/reporting bands (mirror infra/config/rules.yaml on the engine side)
    review_band: float = 50_000.0
    reporting_band: float = 1_000_000.0

    # purposes that legitimacy guards treat as inherently explainable
    exempt_purposes: list[str] = [
        "SALARY", "BONUS", "PROPERTY", "HOSPITAL", "VENDOR_PAYMENT", "SERVICES", "EMERGENCY",
    ]

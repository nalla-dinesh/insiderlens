# InsiderLens Synthetic Bank — DATA REPORT

- Generated (UTC): 2026-10-23T16:21:28+00:00
- Seed: `42` (PCG64) — rebuilds are byte-identical
- Window: 60 days starting 2026-07-01 (covers two month-start salary pulses)

## 1. Volumes

| Frame | Rows | Envelope |
|---|---:|---|
| roles.csv | 4 | == 4 |
| employees.csv | 25 | == 25 |
| customers.csv | 800 | == 800 |
| accounts.csv | 850 | == 850 |
| transactions.csv | 46,978 | [45,000, 55,000] |
| activity_log.csv | 9,124 | [6,000, 14,000] |
| ground_truth.csv | 40 | — |

Baseline mix: salary 1,014, recurring 1,800, merchant 28,000, p2p 15,974 | activity: LOGIN 1,070, VIEW_ACCOUNT 6,235, sensitive 1,805, night_noise 10

## 2. Planted suspicious scenarios (ground truth)

| Scenario | GT rows | What was planted (real ids + metrics) |
|---|---:|---|
| S1 | 4 | S1 ring 200053 -> 200054 -> 200055 -> 200056 -> 200053: seed Rs950,000, cuts ['0.048', '0.055', '0.053', '0.047'], retention 85.1%, txn_ids [1, 2, 3, 4] |
| S2 | 3 | S2 ring 200057 -> 200058 -> 200059 -> 200057: amounts [48500.0, 47800.0, 47200.0] (all Rs45k-49.9k, days [33, 35, 38]) |
| S3 | 16 | S3 source 200060 -> 7 mules [200061, 200062, 200063, 200064, 200065, 200066, 200067] (shared phone 9811450650) -> hub 200061 -> collector 200068: 17 deposits Rs804,898 total, bulk-out Rs860,000 day 47 |
| S4 | 2 | S4 mules [200069, 200070] -> hops [200001, 200002]: 5 occurrences each, days [8, 13, 19, 26, 33], forward 0.88-0.96 within 20h |
| S5 | 4 | S5 employee 1017 OFFICER@Nagpur-East: night day45 LOGIN 23:41, KYC_EDIT 23:44, LIMIT_INCREASE 23:47 (role-violation) on ACTIVE acc 200071; approved RTGS leg txn 53 cross-branch; cycle 200071->200072->200073->200071 retention 92.2% |
| S6 | 1 | S6 dormant acc 200074 (silent ~240d at wake): in Rs960,000 day 41, out Rs930,000 across days 42-44 |
| S7 | 2 | S7 cust 100075 'Junior Clerk' income Rs35,000/mo: acc 200075 credits Rs2,881,006 over 8 events days [15, 18, 22, 26, 30, 34, 39, 44] (~82x monthly income) |

## 3. Legitimate traps (engine must NOT flag)

| Trap | GT rows | Rationale |
|---|---:|---|
| L1 | 1 | L1 payroll corp 200041: 60 SALARY credits day 31 ~09:40 batch (exempt purpose, invisible to T-rules) |
| L2 | 3 | L2 triangle 200042/200043/200044: loops [(3, 8, 25), (30, 38, 55)] — every cycle spans >10d with >=2 exempt legs |
| L3 | 2 | L3 trader 200034 (income Rs300,000) -> builder 200045 Rs4,500,000 PROPERTY day 50 (exempt; T6 guard counts non-exempt volume only) |
| L4 | 1 | L4 family 200035: 3 credits Rs600,000 days [25, 26, 26] (hours 20:00/21:00/10:00), one HOSPITAL payment Rs580,000 day 28 12:00 — only ONE inflow inside the 48h >=80% forward window (occurrences = 1 < 3) |
| L5 | 1 | L5 bonus employer 200047: 40 BONUS payments day 52 ~20:15 (evening, NOT in off-hours band 22:00-06:00; exempt purpose) |

## 4. Quality gate

- Scenario assertions: **12/12 passed** (build fails otherwise)
- Global integrity checks: **19/19 passed**

| Check | Result |
|---|---|
| S1: chronological 4-cycle, span<=10d, retention>=70% | PASS |
| S2: 3-cycle, monotone, span<=10d, all legs in [45k,50k) | PASS |
| S3: >=16 structured deposits in <=6d, then >=5x median bulk-out | PASS |
| S4: >=5 forwards >=80% within 20h per mule, drains >=88% of inflow | PASS |
| S5: off-hours edits + role violation + approved-leg cycle + cross-branch; target ACTIVE | PASS |
| S6: >=35d window silence wake + Rs9.6L in + >Rs9L out in <=3d | PASS |
| S7: >=Rs25L credits, total volume >> 6x declared income | PASS |
| L1: exactly 60 SALARY credits from corp | PASS |
| L2: every triangle cycle span>10d or >=2 exempt legs | PASS |
| L3: single PROPERTY payment; non-exempt volume <= 6x income | PASS |
| L4: exactly 1 >=80% forward, single HOSPITAL outflow | PASS |
| L5: 40 BONUS credits all within 20:00-21:00 evening band | PASS |
| customers_total | PASS |
| accounts_total | PASS |
| employees_total | PASS |
| txn_envelope | PASS |
| activity_envelope | PASS |
| fk_txn_accounts | PASS |
| fk_account_customer | PASS |
| fk_log_employee | PASS |
| fk_txn_approver | PASS |
| gt_account_ids_exist | PASS |
| gt_customer_ids_exist | PASS |
| gt_employee_ids_exist | PASS |
| gt_all_scenarios_present | PASS |
| blindness_roles | PASS |
| blindness_employees | PASS |
| blindness_customers | PASS |
| blindness_accounts | PASS |
| blindness_transactions | PASS |
| blindness_activity_log | PASS |

## 5. Scenario-vs-baseline overlap policy

Scenario and NPC accounts are **reserved**: baseline payroll/recurring/merchant/P2P flows and employee view-target sampling never touch them. Consequences:

1. Planted patterns are the ONLY activity on those accounts — scoring deltas are attributable with zero noise.
2. NPC pool consumption is sequential (persons and businesses are never reused across scenarios within one build).
3. Baseline salary payments DO hit the same recipient accounts used by L1/L5 traps — deliberately: the traps must survive adjacent realistic traffic.

## 6. Blindness guarantee

`ground_truth.csv` is the only file knowing scenario membership; the operational frames carry no `scenario_id` / `is_suspicious` vocabulary (enforced by the gate and by tests). The API may read GT **only** inside EvaluationService.

## 7. Determinism

`python -m generator verify` rebuilds the whole dataset to a temp directory and byte-compares every CSV against `meta.json` checksums (written at build time). See `tests/test_determinism.py` for the double-build byte-identity proof.

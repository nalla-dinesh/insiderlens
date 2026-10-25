# Phase 05 — Analyst Console (Frontend Core) — Notes

**Phase:** 05 (analyst-facing React 18 + TypeScript shell for Dashboard / Alert Detail / Explorer)
**Backend touched:** only the 4 additive, prompt-sanctioned extensions (§1 below) — nothing else.

---

## 1. Sanctioned backend extensions (prompt §"minimal API extensions OK")

The alert list endpoint gained read-only, additive fields; all existing customers of
`/api/alerts` are unaffected (Phase 04 suite still passes — 141 tests, see §5).

| Extension | Where | Why the dashboard needs it |
|---|---|---|
| `AlertPage.band_counts` (LOW/MEDIUM/HIGH/CRITICAL) | `schemas/alerts.py`, `repositories/alerts_repo.py` | The band pills at the top of the queue must count the whole *filtered* set, not the 20-row page the table is showing. Computed **with** rule/status/entity filters applied, **without** the band filter — so picking a pill never zeroes the siblings. |
| `AlertSummary.max_amount` | repo 2 extra batched lookups + `Transaction` JOIN | Table's per-row MAX ₹ — computed as the max leg amount among the alert's cited txn ids (evidence `records.txn_ids`/linked evidence). One GROUP BY query per page, not per row. |
| `AlertSummary.entity_counts {accounts, employees}` | same repo | `entity_ids` mix three overlapping id spaces (accounts 200xxx **and employees 3-digit/1017-ish collide heuristically** — learned the hard way: raw-id heuristics misclassify). Resolved server-side with batched `Account`/`Employee` IN-lookups; column simply renders `N acc · M emp · K cust`. |
| `?entity=<int>` filter | repo + router | FilterBar's entity input — `entity_ids ARRAY @> [n]`, consistent with `rule` (ARRAY contains) semantics. |

Test: `tests/api/test_analysis_api.py::test_dashboard_extensions_band_counts_amount_entity` seeds the S5 case and asserts:
`band_counts == {"LOW":0,"MEDIUM":0,"HIGH":0,"CRITICAL":1}`, `max_amount == 600000.0`,
`entity_counts == {"accounts":3,"employees":1}`, `entity=200072` hits / `entity=200080` misses.
**12/12 API tests pass; `ruff check` + `ruff format --check` clean.**

## 2. Component-level contract — the score-never-alone law is TYPE-ENFORCED

There is deliberately **no `<Score/>` component**. The only renderer that can paint a score
takes a *required* `reason` prop, so a bare score does not compile:

```tsx
// src/components/alerts/ScoreWithReason.tsx (contract excerpt)
interface Props {
  score: number;
  reason: string;   // REQUIRED — a bare score cannot compile here
  bandColor: string;
}
export default function ScoreWithReason({ score, reason, bandColor }: Props) { … }
```

Grep the tree — every score on every screen (`AlertTable` rows, alert detail header, top-band
chip) rides through this component. On the detail page the full reason list additionally
appears in `ReasonsTable` and the contributions bar in `ScoreCard` — the arithmetic is
re-shown (`total !== score` ⇒ red "ARITHMETIC MISMATCH" shout, mirroring the test-guard).

## 3. Invariant banner — required *and* force-tested

`src/components/evidence/InvariantBanner.tsx` + `violatesInvariant(reasons, evidence)`:
true iff `reasons` empty, or `evidence.records` has neither `txn_ids` nor `log_ids`.
Rendered full-width above everything on `/alerts/:id`. "Should be impossible (DB CHECK +
tests)" — **forced test**: the failure path was exercised by pointing the detail page's fetch
at a hand-stripped payload (`getAlert` return with `reasons: []`, `records: {txn_ids:[],log_ids:[]}`)
in dev — banner renders with the "file an incident" copy; with normal data it never appears.
The DB `CHECK (cardinality(reasons) > 0)` constraint (Phase 02) plus the pipeline's
post-persist sweep (Phase 04) make the production path unreachable — that's why the banner
carries incident language rather than a polite empty-state.

## 4. What was deliberately *not* built (honesty ledger)

- **Deferred affordances are disabled buttons with explicit tooltips** ("Convert to case —
  Phase 06", "Export evidence bundle — Phase 06", Cases/Evaluation nav items) — never dead clicks.
- **Explorer shows exactly what the Phase-02 ego endpoint returns** (`nodes`, `edges`, `truncated`).
  The stats strip (neighbours, cited legs, cited volume, channels) is derived **client-side** from
  the cited payload only. No fingerprint widget, no "pattern vs context" edge classes, no employee
  halo vertices — those need endpoint data the backend doesn't emit; shipping them off fabricated
  data would violate Rule #1 of the project (evidence over aesthetics). Flagged for Phase 06+.
- **Frontend own-tests:** this phase pins behavior via the strict TS contract (above), lint, and
  build; Vitest component tests were not added this phase (prompt §"tests… may be added later").

## 5. Verification evidence (sandbox)

```
$ npx tsc --noEmit            → TS-CLEAN (strict)
$ npm run lint                → 0 errors, 2 warnings (react-refresh only-export-components
                                 on Chip.tsx & InvariantBanner.tsx — constants alongside
                                 components; non-blocking, by design)
$ npm run build               → ✓ 422 modules; bundles:
                                  index 128.9 kB gz 43.2 · react 164.9 kB gz 53.9 ·
                                  cytoscape 444 kB gz 142.4 (isolated manualChunk — the
                                  graph lib never blocks first paint of text)
$ cd apps/api && python -m pytest tests/ -x -q   → 141 passed in ~60s (unchanged by extensions)
```

**UAT fix (found via user's laptop screenshot):** the Phase-02 ego endpoint's true shape is
`nodes[{id,label,group,risk_hint}]` + `edges[{source,target,amount,ts,txn_id}]` — an earlier type
guess caused every node to collapse into one giant "A/C undefined" circle (caught by the browser,
not by typecheck: type-driven lie). Fixed `types.ts` + `ExplorerCanvas` + stats strip (Channels →
Account types; channel shown only when present), and added a permanent audit guard:
**"no 'undefined' text anywhere on the Explorer result view"**. Re-verified with real screenshots:
depth-1 shows 3 labelled nodes with correct arrow directions; depth-2 renders the closed S5 wash
ring (200071→200072→200073→200071, 3 legs, ₹17,28,960 — exactly the T1 cycle's cited sum).

**Live smoke (sandbox, seeded DB on :5432):**
- `GET :5173/health` → `{"status":"ok","version":"0.1.0"}` (proxied)
- `GET :5173/api/alerts?limit=1` → alert `#126 CRITICAL 150`, `max_amount 600000.0`,
  `entity_counts {"accounts":3,"employees":1}`, `band_counts {LOW 1224, MEDIUM 4827, HIGH 49, CRITICAL 50}`
- `GET :5173/api/graph/ego/200072?depth=1` → 3 nodes / 3 edges (S5 ring)
- `GET :5173/api/timeline/126` → EMPLOYEE events first-dated (timeline auto-scroll anchor present)
- foreign-host request `Host: …e2b.app` → `200` (`allowedHosts: true` for live previews; laptops unaffected)
- compiled bundle contains `Alert queue`, `Why this score — every point explained`,
  `Threshold gates (source: rules.yaml / roles table)`, `Money-flow explorer`, `Run Analysis`

## 6. Run it on your laptop (Windows, Python 3.11 + Node 20+)

Same as before for the API **plus** the new web tier. From the unzipped repo root:

**Terminal 1 — API (unchanged workflow):**
```bat
cd insiderlens\apps\api
..\..\.venv\Scripts\activate.bat
uvicorn app.main:create_app --factory --reload --port 8000
```

**Terminal 2 — Web (new):**
```bat
cd insiderlens\apps\web
npm install
npm run dev
```
Open **http://localhost:5173**. No `.env` needed locally — the axios client is same-origin and
`vite.config.ts` proxies `/api` and `/health` to `:8000` (no CORS, no config). Only set
`VITE_API_URL` (see `.env.example`) if you later point the built app at a *deployed* API.

Checks to eyeball:
1. Dashboard: band pills LOW/MEDIUM/HIGH/CRITICAL counts ≥ table totals; click CRITICAL pill
   → table isolates the S5 case (`3 acc · 1 emp`, MAX ₹6,00,000, score 150, F1 reason in chip).
2. Alert #126 detail: reasons sum visibly to the score; threshold bars red (over) vs green
   (under); timeline shows the *EMPLOYEE* KYC_EDIT first; scroll bar lands on it.
3. Explorer: account `200072`, depth 1 → 3-account ring, legs width-ordered; depth 2 fills in;
   stats strip counts cited rows only.
4. "Run Analysis" button: after it completes, the queue re-fetches itself (watch the
   "last run finished …" chip + the toast with per-band totals).
```

---

## 7. File tree (apps/web)

```
apps/web/
├── index.html                       (title, inline SVG favicon, SPA description)
├── vite.config.ts                   (proxy /api + /health → :8000; allowedHosts; manualChunks)
├── .env.example                     (documents the local-proxy default; unset = zero config)
└── src/
    ├── main.tsx  App.tsx            (shell: Sidebar + TopBar + Routes; runFinished → reloadSignal)
    ├── index.css                    (Tailwind v4 @theme tokens: navy/sky/bands/danger/success)
    ├── lib/
    │   ├── types.ts                 (backend-mirrored shapes; Band, AlertStatus, RULE_IDS, Evidence…)
    │   ├── http.ts                  (single axios client; same-origin default; error→toast interceptor)
    │   ├── api/alerts.ts | analysis.ts | graph.ts   (typed resource calls)
    │   ├── format.ts                (inrFmt en-IN tabular, dtFmt IST, ageFmt, emphasise(**))
    │   └── hooks.ts                 (useApi: AbortController-safe server-state hook)
    ├── components/
    │   ├── alerts/  ScoreWithReason (CONTRACT), BandCards, FilterBar, AlertTable
    │   ├── evidence/ ScoreCard (contribution bar), ReasonsTable (wraps, never ellipsis),
    │   │             ThresholdCompare (over/under bars + rules.yaml source), ActivityTimeline
    │   │             (auto-scrolls to first EMPLOYEE event), InvariantBanner, ActionsFooter
    │   ├── graph/   CytoscapeCanvas, ExplorerCanvas, useCytoscape (StrictMode-safe destroy),
    │   │            useCyResize
    │   ├── layout/  Sidebar (Cases/Evaluation disabled), TopBar (Run Analysis + last-run chip)
    │   └── ui/      Badge (Band/Status), Chip (rule families T/E/F/M), States (skeleton/empty/error)
    └── pages/   DashboardPage · AlertDetailPage · ExplorerPage
```

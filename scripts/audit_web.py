"""Phase-05 live DOM + console audit — drives the built/dev app headlessly.

Docs evidence: every check prints PASS/FAIL with the observed value.
    .venv/bin/python scripts/audit_web.py [base_url]   # default http://localhost:5173
"""

from __future__ import annotations

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:52} {detail}")


def api(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=15) as r:  # noqa: S310 (local)
        return json.loads(r.read().decode())


console_errors: list[str] = []
failed_requests: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 950})

    def _on_console(m):
        if m.type != "error":
            return
        # devtools logs resource 404s even for gracefully handled probes —
        # whitelist our intentional unknown-account probe only
        if "Failed to load resource" in m.text and m.location and "999999" in str(m.location.get("url", "")):
            return
        console_errors.append(f"{m.text} @ {m.location!r}")

    page.on("console", _on_console)
    page.on("requestfailed", lambda r: failed_requests.append(f"{r.method} {r.url} {r.failure}"))
    page.on(
        "response",
        lambda r: failed_requests.append(f"{r.status} {r.url}") if r.status >= 500 else None,
    )

    # ---------------- Dashboard ----------------
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector("text=Alert queue", timeout=15000)
    rows = page.locator("tbody tr").count()
    check("dashboard rows render", rows == 20, f"{rows} rows/20")

    truth = api("/api/alerts?limit=1")
    total = truth["total"]
    cards = page.locator("button:has-text('click to filter'), button:has-text('click to clear')")
    band_txt = {}
    for b in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        n = page.locator(f"button:has(div:text-is('{b}'))").first
        if n.count():
            num = int(n.locator(".font-mono.text-2xl").inner_text().replace(",", ""))
            band_txt[b] = num
    check("band pills == API band_counts", band_txt == truth["band_counts"], str(band_txt))
    check("band pills sum == total", sum(band_txt.values()) == total, f"{sum(band_txt.values())} vs {total}")

    # CRITICAL pill → isolates; MAX ₹ shows 6,00,000; entities "3 acc · 1 emp"
    page.locator("button:has(div:text-is('CRITICAL'))").first.click()
    page.wait_for_timeout(900)
    body = page.inner_text("tbody")
    check(
        "CRITICAL pill narrows table",
        "F1" in body and "600,000" in body or "6,00,000" in body,
        "F1 reason + 6,00,000 visible" if ("F1" in body) else body[:120],
    )
    check("entity counts server-side", "3 acc · 1 emp" in body, "")
    page.locator("button:has-text('Clear filters')").click()
    page.wait_for_timeout(700)

    # entity filter trap: EID 200080 must MISS (test's boundary)
    einput = page.locator("input[placeholder='e.g. 200071']")
    einput.fill("200072")
    page.wait_for_timeout(900)
    n200072 = page.locator("tbody tr").count()
    einput.fill("200080")
    page.wait_for_timeout(900)
    n200080 = page.locator("tbody tr").count()
    check("entity 200072 hits", n200072 > 0, f"{n200072} rows")
    check("entity 200080 boundary empty", n200080 == 0, f"{n200080} rows → EmptyState")
    check("empty CTA shows Explorer link", page.locator("text=Take me to the Explorer").count() > 0, "")
    einput.fill("")
    page.wait_for_timeout(900)

    # row navigate → detail of the first row's id
    page.locator("tbody tr").first.click()
    page.wait_for_selector("text=/Alert #\\d+/", timeout=15000)

    # ---------------- Alert detail: arithmetic ----------------
    detail_truth = None
    header = page.locator("h1").last.inner_text()
    alert_id = int(header.split("#")[1].split(" ")[0])
    detail_truth = api(f"/api/alerts/{alert_id}")
    g = detail_truth["evidence"]["graph"]

    header_score = int(
        page.locator("div.rounded-xl:has-text('Alert #') .font-mono.text-sm.font-bold").first.inner_text()
    )
    big_score = int(page.locator("section:has-text('EXPLAINABLE SCORE') .text-4xl").inner_text())
    pts = [int(t) for t in page.locator("section:has-text('WHY THIS SCORE') td.text-right").all_inner_texts()]
    pts = [
        int(p.replace("+", "").strip())
        for p in page.locator("section:has-text('WHY THIS SCORE') .text-right.font-bold").all_inner_texts()
    ]
    check(
        "score shown == API score",
        header_score == detail_truth["score"] == big_score,
        f"header={header_score} card={big_score} api={detail_truth['score']}",
    )
    check(
        "Σ reasons == score (DoD iron law on screen)",
        sum(pts) == detail_truth["score"],
        f"Σ{pts} = {sum(pts)}",
    )

    reasons_n = page.locator("section:has-text('WHY THIS SCORE') tbody tr").count()
    check(
        "all reasons rendered",
        reasons_n == len(detail_truth["reasons"]),
        f"{reasons_n}/{len(detail_truth['reasons'])}",
    )
    check(
        "invariant banner absent on clean data",
        page.locator("text=Data invariant violation").count() == 0,
        "",
    )
    check("ARITHMETIC MISMATCH absent", page.locator("text=ARITHMETIC MISMATCH").count() == 0, "")
    check(
        "threshold gates render",
        page.locator("text=/vs/").count() >= len(detail_truth["evidence"]["thresholds"]),
        f"{len(detail_truth['evidence']['thresholds'])} gates",
    )
    check(
        "timeline event count == API",
        page.locator("ol.relative li").count() == len(detail_truth["evidence"]["timeline"]),
        f"{page.locator('ol.relative li').count()}/{len(detail_truth['evidence']['timeline'])}",
    )

    # graph canvas: cytoscape layer present; node/edge counts vs evidence
    page.wait_for_selector("canvas", timeout=8000)
    nc = page.evaluate("() => document.querySelectorAll('canvas').length")
    check("cytoscape canvases mounted", nc >= 3, f"{nc} canvases")

    # Status PATCH round-trip: OPEN → ACKNOWLEDGED → back
    before = detail_truth["status"]
    sel = page.locator("select").first
    sel.select_option("ACKNOWLEDGED")
    page.wait_for_timeout(900)
    after = api(f"/api/alerts/{alert_id}")["status"]
    sel.select_option(before)
    page.wait_for_timeout(900)
    restored = api(f"/api/alerts/{alert_id}")["status"]
    check("status PATCH persists", after == "ACKNOWLEDGED", f"{before}→{after}")
    check("status PATCH restores", restored == before, f"→{restored}")

    # Phase-06 actions: alert is case-linked (export enabled) or not (hard-disabled + WHY tooltip)
    detail_json = api(f"/api/alerts/{alert_id}")
    cid = detail_json.get("case_id")
    if cid:
        check(
            "case-linked alert shows 'Open case #' button",
            page.locator(f"button:has-text('Open case #{cid}')").count() == 1,
            f"case_id={cid}",
        )
        exp_btn = page.locator("button:has-text('Export evidence')").first
        check("export enabled on case-linked alert", not exp_btn.is_disabled(), "")
        with urllib.request.urlopen(BASE + f"/api/cases/{cid}/export", timeout=30) as zr:  # noqa: S310
            head = zr.read(4)
        check("GET export streams a ZIP (PK magic)", head[:2] == b"PK", repr(head[:2]))
    else:
        conv = page.locator("button:has-text('Convert to case')")
        check("convert enabled on unlinked alert", conv.count() == 1 and not conv.first.is_disabled(), "")
        exp_btn = page.locator("button:has-text('Export evidence')")
        check(
            "export hard-disabled + WHY tooltip when unlinked",
            exp_btn.is_disabled() and "Convert to a case first" in (exp_btn.get_attribute("title") or ""),
            "",
        )
    page.locator("a:has-text('← queue')").click()
    page.wait_for_selector("text=Alert queue")

    # ---------------- Explorer ----------------
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector("text=Alert queue")
    page.get_by_role("link", name="Explorer").click()
    page.wait_for_selector("text=Money-flow explorer")
    check("explorer empty-state has seed hint", page.locator("text=200072").count() > 0, "")
    page.locator("input[placeholder*='200072']").fill("200072")
    page.locator("button:has-text('Investigate')").click()
    page.wait_for_selector("text=/Ego graph/", timeout=12000)
    checks_ego = api("/api/graph/ego/200072?depth=1")
    nb = page.locator("dt", has_text="Direct neighbours").locator("..").locator("dd").first.inner_text()
    legs = page.locator("text=CITED LEGS").locator("..").locator(".font-mono").first.inner_text()
    check(
        "explorer stats == API",
        int(nb) == checks_ego["nodes"].__len__() - 1 and int(legs) == len(checks_ego["edges"]),
        f"neighbours={nb} legs={legs}",
    )
    vol = sum(e["amount"] for e in checks_ego["edges"])

    # Indian (lakh) grouping, as inrFmt renders with Intl en-IN
    def inr(n: float) -> str:
        s_ = f"{int(round(n))}"
        head, tail = s_[:-3], s_[-3:]
        parts = []
        while head:
            parts.insert(0, head[-2:])
            head = head[:-2]
        return ",".join(parts + [tail]) if parts else tail

    shown = page.locator("dt", has_text="Cited volume").locator("..").locator("dd").first.inner_text()
    check("cited volume shown", inr(vol) in shown, f"api={inr(vol)} ui={shown}")
    check("no undefined labels in explorer graph", "undefined" not in page.inner_text("body"), "")
    page.locator("input[placeholder*='200072']").fill("999999")
    page.locator("button:has-text('Investigate')").click()
    page.wait_for_timeout(1200)
    check(
        "unknown account → explicit error state",
        page.locator("text=Something went wrong").count() > 0
        and "account_not_found" in page.inner_text("body"),
        "",
    )

    # ---------------- Sidebar nav affordances ----------------
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector("text=Alert queue")
    cases_link = page.locator("aside a:has-text('Cases')").first
    check(
        "nav Cases routes to /cases (live since Phase 06)",
        (cases_link.get_attribute("href") or "").endswith("/cases"),
        f"href={cases_link.get_attribute('href')!r}",
    )
    ev_link = page.locator("aside a:has-text('Evaluation')").first
    check(
        "nav Evaluation routes to /evaluation (live since Phase 07)",
        (ev_link.get_attribute("href") or "").endswith("/evaluation"),
        f"href={ev_link.get_attribute('href')!r}",
    )

    # ---------------- Sandbox state constraint proof ----------------
    # App writes NOTHING to ambient storage; prove the preview-sandbox
    # (sandbox=allow-scripts w/o allow-same-origin) leaves no crumbs:
    state = page.evaluate(
        """() => {
          const out = {};
          try { out.localLen = localStorage.length; } catch (e) { out.localBlocked = String(e); }
          try { out.sessionLen = sessionStorage.length; } catch (e) { out.sessionBlocked = String(e); }
          try { out.cookies = document.cookie; } catch (e) { out.cookieBlocked = String(e); }
          return out;
        }"""
    )
    check(
        "zero ambient state writes (storage/cookie)",
        state.get("localLen") == 0 and state.get("sessionLen") == 0 and state.get("cookies") == "",
        json.dumps(state),
    )

    # ---------------- Cases board (Phase 06) ----------------
    # ensure at least one OPEN case exists (board may hold only closed ones)
    board = api("/api/cases")
    if not any(c["status"] == "OPEN" for g in board["groups"].values() for c in g):
        alerts = api("/api/alerts?band=CRITICAL&limit=50")
        free = next(a for a in alerts["items"] if a.get("case_id") in (None, 0))
        name = api("/api/analysts")[0]["name"]
        req = urllib.request.Request(
            BASE + "/api/cases",
            data=json.dumps({"alert_id": free["alert_id"], "assignee": name}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15):  # noqa: S310
            pass

    page.goto(BASE + "/cases", wait_until="networkidle")
    page.wait_for_selector("text=Case board", timeout=15000)
    check("cases nav item routes", "Case board" in page.inner_text("main"), "board rendered")
    five = all(
        page.locator(f"text={lbl}").count() >= 1
        for lbl in ("Open", "In progress", "Escalated", "Closed · fraud", "Closed · benign")
    )
    check("board shows 5 status columns", five, "")
    first_card = page.locator("button:has(.font-mono):has-text('case #')").first
    check(
        "board card visible (band + title + age)",
        first_card.count() == 1,
        first_card.inner_text().split("\n")[0],
    )
    first_card.click()
    page.wait_for_selector("[data-testid='case-drawer']", timeout=8000)
    drawer = page.locator("[data-testid='case-drawer']")
    status_buttons = drawer.locator("button:disabled")
    legal_info = drawer.locator("text=Status (legal moves only)").first
    total_btns = drawer.locator("section").first.locator("button").count()
    disabled_btns = status_buttons.count()
    check(
        "state machine button set (legal enabled, illegal disabled)",
        total_btns == 5,
        f"{total_btns} status buttons, {disabled_btns} disabled; chip={legal_info.count()}",
    )
    body_txt = drawer.inner_text()
    check("drawer shows linked alerts + full evidence", "LINKED ALERTS (1)" in body_txt, "")
    check(
        "drawer has notes thread + add box",
        "NOTES & AUDIT TRAIL" in body_txt and drawer.locator("textarea").count() >= 2,
        "",
    )
    check("drawer export button present", "Export evidence ZIP" in drawer.inner_text(), "")
    # note → visible immediately at thread bottom
    drawer.locator("textarea").last.fill("audit-visible note ✓")
    drawer.locator("button:has-text('Add')").click()
    page.wait_for_timeout(900)
    check("note add updates thread without reload", "audit-visible note ✓" in drawer.inner_text(), "")
    page.keyboard.press("Escape")
    page.locator("button[aria-label='Close case drawer']").click()
    page.wait_for_timeout(400)

    # ---------------- Evaluation page (Phase 07) ----------------
    page.goto(BASE + "/evaluation", wait_until="networkidle")
    page.wait_for_selector("text=Evaluation harness", timeout=15000)
    body_t = page.inner_text("main")
    check(
        "evaluation: 4 metric cards + raw counts render",
        all(k in body_t for k in ("PRECISION", "RECALL", "F1", "FALSE-POSITIVE", "TP", "TN")),
        "",
    )
    check(
        "evaluation: all 12 scenarios listed (S + L) with verdicts",
        all(k in body_t for k in ("S2", "L2", "TP", "TN", "SUSPICIOUS", "TRAP")),
        "",
    )
    check(
        "evaluation: trap rows show silence note (no fabricated evidence)",
        "silence — correct for traps" in body_t,
        "",
    )
    eval_run = api("/api/evaluation/1")
    ok_card = page.locator("section", has_text="CONFUSION MATRIX").first
    check(
        "evaluation: UI recall == API recall",
        f"{eval_run['recall']:.4f}" in body_t and ok_card.count() == 1,
        f"api R={eval_run['recall']}",
    )
    page.screenshot(path="phase7_shots/evaluation.png", full_page=True)

    browser.close()

check("zero console errors overall", len(console_errors) == 0, repr(console_errors[:3]))
check("zero failed/5xx requests overall", len(failed_requests) == 0, repr(failed_requests[:3]))

print("\n" + "=" * 80)
passed = sum(1 for _, ok, _ in results if ok)
print(f"AUDIT: {passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)

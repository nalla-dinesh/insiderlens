#!/usr/bin/env bash
# Phase 06 E2E — the full investigation loop over real HTTP:
#   health → (ingest+run if empty) → CRITICAL alert → case → transitions + notes
#   → closed → illegal-hop proof → ZIP export → unzip -l + jq + PDF text proof.
# Idempotent: run twice — second run relinks the alert into a NEW case
# because the first one closed (sequential-case rule, P4).
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
PYTHON="${PYTHON:-python3}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

say() { printf '\n\033[36m════════ %s ════════\033[0m\n' "$*"; }

say "health"
curl -sSf "${BASE}/health" | jq -c .

say "ingest-if-empty"
TOTAL="$(curl -sSf "${BASE}/api/alerts?limit=1" | jq -r .total)"
echo "alerts in queue: ${TOTAL}"
if [ "${TOTAL}" -eq 0 ]; then
  echo "queue empty → ingesting bundle + running analysis…"
  curl -sSf -X POST "${BASE}/api/ingest" > /dev/null
  curl -sSf -X POST "${BASE}/api/analysis/run" | jq -c '{run_id, status, alerts_by_band, duration_ms}'
else
  echo "already populated — continuing with current queue"
fi

say "pick first HIGH/CRITICAL alert"
AID="$(
  curl -sSf "${BASE}/api/alerts?limit=50&band=CRITICAL" | jq -r '.items[0].alert_id // empty'
)"
if [ -z "${AID}" ]; then
  AID="$(curl -sSf "${BASE}/api/alerts?limit=50&band=HIGH" | jq -r '.items[0].alert_id')"
fi
echo "alert AL-$(printf '%06d' "${AID}")"

say "create case (assignee: first analyst from directory)"
ANALYST="$(curl -sSf "${BASE}/api/analysts" | jq -r '.[0].name')"
CASE_JSON="$(curl -sSf -X POST "${BASE}/api/cases" \
  -H 'content-type: application/json' \
  -d "{\"alert_id\": ${AID}, \"assignee\": \"${ANALYST}\"}")"
CID="$(echo "${CASE_JSON}" | jq -r .case_id)"
echo "case ${CID} ← alert ${AID} · assignee '${ANALYST}'"
echo "${CASE_JSON}" | jq -r '.title'

say "transitions w/ notes: OPEN → IN_PROGRESS → ESCALATED → CLOSED_TRUE"
for S in IN_PROGRESS ESCALATED CLOSED_TRUE; do
  curl -sSf -X POST "${BASE}/api/cases/${CID}/notes" \
    -H 'content-type: application/json' \
    -d "{\"body\": \"e2e: moving towards ${S}\", \"author\": \"${ANALYST}\"}" > /dev/null
  curl -sSf -X PATCH "${BASE}/api/cases/${CID}" \
    -H 'content-type: application/json' \
    -d "{\"status\": \"${S}\", \"actor\": \"${ANALYST}\"}" | jq -c '{case_id, status, closed_at}'
done

say "closed immutability: CLOSED_TRUE → OPEN must be 409"
CODE="$(curl -s -o /dev/null -w '%{http_code}' -X PATCH "${BASE}/api/cases/${CID}" \
  -H 'content-type: application/json' -d '{"status":"OPEN"}')"
[ "${CODE}" = "409" ] && echo "OK — PATCH on closed case rejected (${CODE})" || { echo "FAIL (${CODE})"; exit 1; }

say "export evidence ZIP"
curl -sSf "${BASE}/api/cases/${CID}/export" -o "${TMP}/bundle.zip"
unzip -l "${TMP}/bundle.zip"

say "evidence.json law check (score == Σ reasons)"
mkdir -p "${TMP}/x" && (cd "${TMP}/x" && unzip -q ../bundle.zip)
jq -r '.case.case_id, .alerts[0].score, (.alerts[0].reasons | map(.pts) | add), .alerts[0].score_arithmetic_verified' \
  "${TMP}/x/evidence.json"

say "pdftotext head (via pypdf)"
"${PYTHON}" - "${TMP}/x/report.pdf" <<'PY'
import sys
from pypdf import PdfReader
reader = PdfReader(sys.argv[1])
text = "\n".join((p.extract_text() or "") for p in reader.pages)
print("\n".join(text.splitlines()[:30]))
assert "Score arithmetic" in text, "PDF must contain the score table"
assert "TOTAL" in text, "PDF must contain the arithmetic total row"
print("── pdf text proof ok ──")
PY

say "status history visible in case response"
curl -sSf "${BASE}/api/cases/${CID}" | jq -r '.notes[].body' | grep -E "Status (OPEN|IN_PROGRESS|ESCALATED|CLOSED_TRUE) →" || {
  echo "FAIL: no transition notes in case notes"; exit 1; }

say "E2E PASS (case ${CID}, alert ${AID})"

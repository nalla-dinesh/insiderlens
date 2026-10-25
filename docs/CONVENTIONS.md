# Engineering Conventions — InsiderLens

Applies to both members, every phase, no exceptions.

## 1. Git workflow

- `main` is protected: merge via PR only, PR must be green (lint + tests) and reviewed by the other member.
- Branches: `feat/p<phase>-<slug>` → e.g. `feat/p03-cycle-rule`, `fix/p05-timeline-order`.
- Commits: **Conventional Commits**
  - `feat(api): add ego-graph endpoint`
  - `fix(engine): enforce chronological walk in T1`
  - `test(web): StatusCard error state`
  - scopes: `api`, `web`, `engine`, `generator`, `infra`, `docs`
- One logical change per PR. Daily push, even WIP (prefix `wip:` is fine on a branch, squash before merge).

## 2. Pull-request checklist (paste into every PR)

```
- [ ] ruff check + npm run lint: clean (paste output)
- [ ] pytest / relevant tests: green (paste output)
- [ ] Phase DoD items touched by this PR: listed with evidence
- [ ] No thresholds hardcoded (rules.yaml only)
- [ ] No placeholders / commented-out code / console.log left behind
- [ ] UI change: screenshot attached
```

## 3. Review SLA

4 working hours. Reviewer checks semantics, not style (linters own style).
Blocking comments must say exactly what to change. Praise good catches loudly — 2-person morale matters.

## 4. The five project laws

1. **Config law:** every numeric threshold / weight / window lives in `infra/config/rules.yaml`.
   Code that hardcodes one fails review on sight.
2. **Evidence law:** an alert without reasons + evidence is a bug, not a style issue.
   (Enforced by DB CHECK + API invariant tests.)
3. **Blindness law:** ground truth may be read ONLY by `EvaluationService` (Phase 07).
   Engine importing it = architecture violation.
4. **Determinism law:** generator seeded (SEED=42). Rebuild twice → byte-identical output.
5. **Honesty law:** metrics are computed, never asserted. Tuning changes go in `docs/TUNING.md` with numbers.

## 5. Code style

- Python: 3.11, type hints on all public functions, pydantic v2 for every boundary object,
  ruff (line-length 110) is the formatter+lint authority.
- TypeScript: strict mode; no `any` without a `// justify:` comment; server data crosses the wire ONLY
  through typed API modules (`src/lib/api/*`); components receive typed props.
- Naming: files `snake_case.py` / `PascalCase.tsx`; API routes kebab-free (`/api/alerts`, `/api/graph/ego`);
  DB tables snake plural (`transactions`), models Pascal singular (`Transaction`).
- Errors: never swallow; use the shared error model (`AppError` → JSON) on the API, toasts + error states on the web.
- Logs: structlog with request_id; no print() in committed code.


## 5. Branch protection (human GitHub setup — Phase 08)

Main-branch protection rules to require, all four CI checks green:
`api-test`, `web-build`, `docker-build`, `e2e`. PRs must rebase-clean; the E2E
log uploads as the `e2e-log` artifact for audit.

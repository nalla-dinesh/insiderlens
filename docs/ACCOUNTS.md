# External Accounts — InsiderLens

Everything is free-tier (verified Oct 2026). No credentials in this file — only who owns what.
Fill the Owner/Status columns as accounts get created.

| # | Service | Purpose | Free tier we rely on | Needed from | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | GitHub | Repo + PRs + Actions CI | Free (private repo, ~2,000 CI min/mo) | Phase 00 | _TBD_ | ⬜ |
| 2 | Vercel | Frontend hosting (Phase 09) | Hobby: 100 GB/mo, non-commercial OK | Phase 09 | _TBD_ | ⬜ |
| 3 | Render | API hosting, Docker (Phase 09) | 750 instance-hrs/mo; sleeps 15 min idle | Phase 09 | _TBD_ | ⬜ |
| 4 | Neon | Postgres hosting (Phase 09) | 1 GB storage, no expiry, scale-to-zero | Phase 09 | _TBD_ | ⬜ |
| 5 | UptimeRobot | /health monitoring (Phase 09) | 50 monitors, 5-min interval | Phase 09 | _TBD_ | ⬜ |
| 6 | Sentry (optional) | API error tracking | 5k errors/mo | Phase 09 | _TBD_ | ⬜ |

> Do NOT plan around: Render's own free Postgres (expires 30 days), Fly.io / Koyeb (no cardless free tier),
> DigitalOcean student credit (ended Jul 2026).

## [HUMAN] One-time GitHub setup (do this in Phase 00, ~10 min)

1. Create **private** repo `insiderlens` under the team lead's account.
2. Invite the teammate as collaborator (Settings → Collaborators).
3. Push the Phase-00 scaffold (see README quickstart for the first commit contents).
4. Branch protection on `main` — enable NOW: "Require a pull request before merging (1 approval)".
   Add "Require status checks" only AFTER Phase 08 creates the CI workflow (the check won't exist before).
5. Confirm both members can clone, branch `feat/test-readme`, open a PR, review, merge, delete branch.

## Notes

- Sign up for #1–#5 with the SAME team GitHub/Google identity so admin handover is painless.
- Subdomains are acceptable for the demo (`*.vercel.app`, `*.onrender.com`) — no domain purchase needed.

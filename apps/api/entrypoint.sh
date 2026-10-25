#!/bin/sh
# InsiderLens API entrypoint (Phase 08).
#
# RUN_MIGRATIONS=1 -> run `alembic upgrade head` once, THEN start uvicorn.
# Deliberately OPT-IN (pitfall P5): migration is a one-shot schema op — never
# auto-run it on every container start when more than one instance might boot
# in parallel later. Free-tier compose passes RUN_MIGRATIONS=1 for exactly the
# first boot; a human redeploying omits it.
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] RUN_MIGRATIONS=1 → alembic upgrade head"
  python -m alembic upgrade head
fi

echo "[entrypoint] starting: $*"
exec "$@"

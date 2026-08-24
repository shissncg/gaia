#!/usr/bin/env python3
"""
Ordered Mongo migration runner with an applied-once ledger.

Runs every cross-version data repair in ``MIGRATIONS`` (below), in order,
exactly once. Applied entries are recorded in ``GAIA.applied_migrations`` so a
repeat run (every future ``docker compose up run-migrations``, including every
``gaia update``) is a full skip. A migration that exits nonzero halts the
runner immediately and is NOT recorded — a half-migrated store must stop the
boot loudly, not limp forward.

This is deliberately Mongo-only. The Postgres layer bootstraps via
``Base.metadata.create_all`` + an idempotent hand-rolled promotion on every
engine init (``app/db/postgresql.py``); Alembic is out of scope (see
``docs/self-hosting/upgrading.mdx``).

Run from apps/api (bare python, no ``uv run`` — matches the compose one-shot):
    python scripts/run_migrations.py                # apply every pending entry
    python scripts/run_migrations.py --dry-run       # list pending vs applied, run nothing
    python scripts/run_migrations.py --force 0002_workflow_status_liveness
                                                      # re-run one entry despite the ledger
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys
import time

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.config.settings import settings

# The apps/api directory — every migration argv below is a path relative to
# this, and every subprocess runs with this as its cwd (mirrors where the
# compose one-shot's WORKDIR puts it: /app/apps/api).
API_ROOT = Path(__file__).resolve().parent.parent

# Mongo database name the rest of the scripts layer hardcodes (payment_setup.py,
# grant_pro_access.py) — the scripts layer bypasses repositories by convention.
_DB_NAME = "GAIA"
_LEDGER_COLLECTION = "applied_migrations"

# ---------------------------------------------------------------------------
# Ordered, append-only. Each entry: (migration_id, argv run from apps/api).
# The id is recorded in GAIA.applied_migrations on success and never re-run.
# Only cross-version DATA repairs belong here — never vendor-cloud syncs,
# never seeders (seed-* one-shots own those), never anything non-idempotent,
# never anything that blocks on interactive input or requires vendor-only
# credentials no self-hosted install has.
# ---------------------------------------------------------------------------
MIGRATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "0001_workflow_schedule_types",
        ("python", "scripts/migrate_workflow_schedule_types.py", "--apply"),
    ),
    (
        "0002_workflow_status_liveness",
        ("python", "scripts/migrate_workflow_status_liveness.py", "--apply"),
    ),
    (
        "0003_workflow_integration_fields",
        ("python", "scripts/migrate_workflow_integration_fields.py", "--apply"),
    ),
    (
        "0004_backfill_bot_conversation_source",
        ("python", "scripts/backfill_bot_conversation_source.py"),
    ),
    (
        "0005_workflow_slugs",
        ("python", "scripts/migrate_workflow_slugs.py"),
    ),
    (
        "0006_backfill_integration_favicons",
        ("python", "-m", "scripts.backfill_integration_favicons"),
    ),
    (
        "0007_backfill_usage_daily",
        ("python", "scripts/backfill_usage_daily.py"),
    ),
)

# ---------------------------------------------------------------------------
# Excluded candidates (apps/api/scripts/*.py and apps/api/app/scripts/*.py),
# with reasons. Excluding is fine; excluding silently is not.
#
# - sync_explore_workflows_from_prod.py — vendor-cloud-only: pulls from the
#   live https://api.heygaia.io production API. No self-hosted install has
#   that endpoint or wants prod's explore catalogue overwriting its own.
# - fix_marketplace_mcp.py — a one-time repair of specific marketplace MCP
#   integrations known-bad as of 2026-06-18 (hardcoded curated URL fixes +
#   live probes against those exact servers), not a general schema migration.
# - migrate_mem0_memories.py — requires an external MEM0_API_KEY vendor
#   credential outside the self-host env surface and sys.exit(1)s without it;
#   migrates FROM the already-retired mem0 backend that no self-hosted
#   install (this fork's memory engine long since replaced it) ever used.
# - migrate_vfs_to_juicefs.py — a one-shot cutover for a schema transition
#   (Mongo-VFS -> JuiceFS) completed before self-hosting existed; targets the
#   legacy `vfs_nodes` collection that no self-hosted install can have (the
#   runtime VFS service was deleted pre-self-host), and needs a FUSE-mounted
#   JuiceFS host path this lightweight one-shot container doesn't have.
# - backfill_integration_content.py — defaults to an interactive y/N
#   confirmation prompt (would crash on EOF with no attached stdin) and makes
#   paid, non-deterministic LLM generation calls; a marketplace-copy
#   enhancement, not a correctness repair — self-hosted integrations already
#   render fine with generic fallback copy.
# - backfill_public_workflow_descriptions.py (apps/api/app/scripts/) — its
#   MANIFEST is keyed to hardcoded vendor-production workflow `_id` values
#   (verified: those ids appear nowhere else in this codebase). It is inert
#   on any self-hosted Mongo — seed-explore generates its own ids at insert
#   time, so nothing in the manifest ever matches.
# - fix_subscription_data.py — interactive billing-data cleanup tied to Dodo
#   Payments plan ids. Self-hosted mode never creates real Dodo subscriptions
#   (DEPLOYMENT_MODE=self_hosted grants PRO in-process without touching
#   Mongo/Dodo — see Phase 4), so there is nothing for it to repair.
# - sync_composio_tools.py — not a data migration: a dev/audit tool that
#   fetches the Composio catalogue and writes a local report file, no Mongo
#   writes at all.
# ---------------------------------------------------------------------------


def _ledger_collection() -> AsyncIOMotorCollection:
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGO_DB)
    return client[_DB_NAME][_LEDGER_COLLECTION]


async def _applied_ids(collection: AsyncIOMotorCollection) -> set[str]:
    """Every migration_id already recorded as applied."""
    return {doc["_id"] async for doc in collection.find({}, {"_id": 1})}


def _pending_migrations(
    applied_ids: set[str],
) -> list[tuple[str, tuple[str, ...]]]:
    """Pure filter: MIGRATIONS entries not yet in the ledger, in order."""
    return [(mid, argv) for mid, argv in MIGRATIONS if mid not in applied_ids]


async def _record_applied(
    collection: AsyncIOMotorCollection, migration_id: str, duration_ms: int
) -> None:
    await collection.update_one(
        {"_id": migration_id},
        {"$set": {"applied_at": datetime.now(UTC), "duration_ms": duration_ms}},
        upsert=True,
    )


async def _run_subprocess(argv: tuple[str, ...], cwd: Path) -> int:
    """Run one migration script, streaming its output through live. Returns its exit code."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    while line := await proc.stdout.readline():
        print(f"    | {line.decode(errors='replace').rstrip()}")
    return await proc.wait()


async def _apply_one(
    collection: AsyncIOMotorCollection, migration_id: str, argv: tuple[str, ...]
) -> int:
    """Run one migration and record it on success. Returns the subprocess exit code."""
    print(f"[apply] {migration_id}: {' '.join(argv)}")
    started = time.perf_counter()
    exit_code = await _run_subprocess(argv, API_ROOT)
    duration_ms = int((time.perf_counter() - started) * 1000)

    if exit_code != 0:
        print(f"[FAILED] {migration_id} exited {exit_code} after {duration_ms}ms — halting.")
        return exit_code

    await _record_applied(collection, migration_id, duration_ms)
    print(f"[applied] {migration_id} ({duration_ms}ms)")
    return 0


async def _run_dry_run(collection: AsyncIOMotorCollection) -> int:
    applied_ids = await _applied_ids(collection)
    print("[dry-run] Migration status:")
    for migration_id, _argv in MIGRATIONS:
        state = "applied" if migration_id in applied_ids else "pending"
        print(f"  {migration_id}: {state}")
    return 0


async def _run_force(collection: AsyncIOMotorCollection, force_id: str) -> int:
    registry = dict(MIGRATIONS)
    argv = registry.get(force_id)
    if argv is None:
        print(f"[error] {force_id!r} is not in the migration registry.")
        return 1
    print(f"[force] Re-running {force_id} despite ledger state.")
    return await _apply_one(collection, force_id, argv)


async def _run_pending(collection: AsyncIOMotorCollection) -> int:
    applied_ids = await _applied_ids(collection)
    for migration_id, _argv in MIGRATIONS:
        if migration_id in applied_ids:
            print(f"[skip] {migration_id}: already applied")

    for migration_id, argv in _pending_migrations(applied_ids):
        exit_code = await _apply_one(collection, migration_id, argv)
        if exit_code != 0:
            return exit_code
    return 0


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", action="store_true", help="List pending vs applied migrations; run nothing."
    )
    group.add_argument(
        "--force",
        metavar="MIGRATION_ID",
        help="Re-run one migration_id despite the ledger (operator repair).",
    )
    args = parser.parse_args(argv)

    collection = _ledger_collection()
    if args.dry_run:
        return await _run_dry_run(collection)
    if args.force:
        return await _run_force(collection, args.force)
    return await _run_pending(collection)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

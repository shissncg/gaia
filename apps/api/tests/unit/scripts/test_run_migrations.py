"""Unit tests for the Mongo migration runner.

Two behaviors decide whether an upgrade is safe: an already-applied entry must
never spawn its subprocess again (the ledger is the whole point — a re-run
that silently re-executes a migration could double-fire ARQ jobs or corrupt
already-repaired data), and a failing entry must halt immediately without
being recorded, so a half-migrated store never looks "done".

No `regression` markers — every symbol here is introduced by this change.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.run_migrations import (
    MIGRATIONS,
    _apply_one,
    _pending_migrations,
    _run_force,
    _run_pending,
)


def _fake_collection(applied_ids: set[str]) -> AsyncMock:
    """A Motor-collection stand-in whose `find` yields one doc per applied id."""
    collection = AsyncMock()

    class _Cursor:
        def __aiter__(self):
            return self._gen()

        async def _gen(self):
            for migration_id in applied_ids:
                yield {"_id": migration_id}

    # Motor's `.find()` is synchronous and returns a cursor; only iterating the
    # cursor is async. AsyncMock would make `.find()` itself a coroutine, so
    # override it with a plain MagicMock.
    collection.find = MagicMock(return_value=_Cursor())
    return collection


def test_pending_migrations_filters_out_applied_ids() -> None:
    all_ids = [mid for mid, _ in MIGRATIONS]
    applied = {all_ids[0], all_ids[2]}

    pending = _pending_migrations(applied)

    assert [mid for mid, _ in pending] == [mid for mid in all_ids if mid not in applied]


def test_pending_migrations_preserves_registry_order() -> None:
    pending = _pending_migrations(set())

    assert [mid for mid, _ in pending] == [mid for mid, _ in MIGRATIONS]


def test_migrations_registry_has_unique_ids() -> None:
    ids = [mid for mid, _ in MIGRATIONS]
    assert len(ids) == len(set(ids)), "duplicate migration_id in the registry"


async def test_already_applied_entry_never_spawns_its_subprocess() -> None:
    """The whole point of the ledger: a re-run must not re-execute a settled entry."""
    all_ids = [mid for mid, _ in MIGRATIONS]
    collection = _fake_collection(applied_ids=set(all_ids))

    async def _raise_if_spawned(*args: object, **kwargs: object) -> None:
        raise AssertionError("create_subprocess_exec was called for an already-applied entry")

    with patch("asyncio.create_subprocess_exec", side_effect=_raise_if_spawned):
        exit_code = await _run_pending(collection)

    assert exit_code == 0
    collection.update_one.assert_not_awaited()


async def test_pending_entry_is_applied_and_recorded() -> None:
    collection = _fake_collection(applied_ids=set())
    migration_id, argv = MIGRATIONS[0]

    proc = AsyncMock()
    proc.wait.return_value = 0
    proc.stdout.readline = AsyncMock(side_effect=[b"line one\n", b""])

    with patch("asyncio.create_subprocess_exec", return_value=proc) as spawn:
        exit_code = await _apply_one(collection, migration_id, argv)

    assert exit_code == 0
    spawn.assert_awaited_once()
    called_argv = spawn.await_args.args
    assert called_argv == argv
    collection.update_one.assert_awaited_once()
    filter_arg, update_arg = collection.update_one.await_args.args
    assert filter_arg == {"_id": migration_id}
    assert isinstance(update_arg["$set"]["applied_at"], datetime)
    assert update_arg["$set"]["applied_at"].tzinfo is UTC
    assert isinstance(update_arg["$set"]["duration_ms"], int)


async def test_failing_entry_halts_and_is_not_recorded() -> None:
    """A nonzero exit must stop the runner and leave the ledger untouched."""
    collection = _fake_collection(applied_ids=set())

    proc = AsyncMock()
    proc.wait.return_value = 1
    proc.stdout.readline = AsyncMock(side_effect=[b"boom\n", b""])

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        exit_code = await _run_pending(collection)

    assert exit_code == 1
    collection.update_one.assert_not_awaited()


async def test_failing_entry_never_runs_the_next_one() -> None:
    """Halt-on-failure means later registry entries must never even be attempted."""
    collection = _fake_collection(applied_ids=set())
    calls: list[tuple[str, ...]] = []

    async def _fail_first(*argv: str, **kwargs: object) -> AsyncMock:
        calls.append(argv)
        proc = AsyncMock()
        proc.wait.return_value = 1
        proc.stdout.readline = AsyncMock(side_effect=[b""])
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fail_first):
        await _run_pending(collection)

    assert len(calls) == 1
    assert calls[0] == MIGRATIONS[0][1]


async def test_force_reruns_an_already_applied_entry() -> None:
    """--force ignores ledger state for the one named entry."""
    migration_id, argv = MIGRATIONS[0]
    collection = _fake_collection(applied_ids={migration_id})

    proc = AsyncMock()
    proc.wait.return_value = 0
    proc.stdout.readline = AsyncMock(side_effect=[b""])

    with patch("asyncio.create_subprocess_exec", return_value=proc) as spawn:
        exit_code = await _run_force(collection, migration_id)

    assert exit_code == 0
    spawn.assert_awaited_once()
    collection.update_one.assert_awaited_once()


async def test_force_with_unknown_id_errors_without_spawning() -> None:
    collection = _fake_collection(applied_ids=set())

    async def _raise_if_spawned(*args: object, **kwargs: object) -> None:
        raise AssertionError("create_subprocess_exec was called for an unknown migration_id")

    with patch("asyncio.create_subprocess_exec", side_effect=_raise_if_spawned):
        exit_code = await _run_force(collection, "does-not-exist")

    assert exit_code == 1


@pytest.mark.parametrize("migration_id,argv", MIGRATIONS)
def test_every_registry_entry_targets_an_existing_script(
    migration_id: str, argv: tuple[str, ...]
) -> None:
    """Catch a typo'd path before it ships — the run only fails once someone upgrades."""

    from scripts.run_migrations import API_ROOT

    if argv[1] == "-m":
        module = argv[2]
        script_path = API_ROOT.joinpath(*module.split(".")).with_suffix(".py")
    else:
        script_path = API_ROOT / argv[1]
    assert script_path.is_file(), f"{migration_id}: {script_path} does not exist"

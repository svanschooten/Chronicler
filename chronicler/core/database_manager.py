import asyncio
import logging
import os
import re
import shutil
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from functools import cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from chronicler.core.database import DBChronicle
from chronicler.core.models import Snapshot
from chronicler.core.workspace_lock import WorkspaceLock

logger = logging.getLogger(__name__)

_MIGRATIONS_ROOT = Path(__file__).resolve().parent.parent / "migrations"


SNAPSHOTS_KEPT = 3
"""
How many snapshots of one kind a chronicle keeps: the oldest, which holds the transcript
as it was before the first such change, and the newest of the rest.
"""

SNAPSHOT_STAMP = "%Y%m%d-%H%M%S-%f"
SWAP_ATTEMPTS = 5
SWAP_BACKOFF_SECONDS = 0.1


def _snapshot_pattern(chronicle_id: str) -> re.Pattern[str]:
    """`before-<kind>-<chronicle id>-<stamp>.db`; the id keeps linked chronicles apart."""
    return re.compile(
        rf"^before-(?P<kind>[a-z]+)-{re.escape(chronicle_id)}-(?P<stamp>\d{{8}}-\d{{6}}-\d{{6}})\.db$"
    )


def _vacuum_into(source: Path, destination: Path) -> None:
    literal = str(destination).replace("'", "''")
    connection = sqlite3.connect(source)
    try:
        connection.execute(f"VACUUM INTO '{literal}'")
    finally:
        connection.close()


def _rebuild_search_index(path: Path) -> None:
    """
    Rebuilds a chronicle's FTS index from its lines. The index is keyed on the implicit
    rowid of `transcript_lines`, which SQLite may renumber when it copies the table; a stale
    index finds the wrong lines rather than failing. See docs/search.md.
    """
    connection = sqlite3.connect(path)
    try:
        has_index = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'transcript_search'"
        ).fetchone()
        if has_index:
            connection.execute(
                "INSERT INTO transcript_search(transcript_search) VALUES ('rebuild')"
            )
            connection.commit()
    finally:
        connection.close()


def _swap_in(snapshot: Path, live: Path) -> None:
    """
    Puts a copy of `snapshot` where `live` is, indexed and ready. The copy is made beside the
    live file and renamed over it, so the swap is one step: a crash leaves the old file or the
    new one, never half of either. The snapshot itself stays, so a restore can be repeated.
    """
    staged = live.with_name(live.name + ".restoring")
    try:
        shutil.copyfile(snapshot, staged)
        _rebuild_search_index(staged)
        for attempt in range(SWAP_ATTEMPTS):
            try:
                os.replace(staged, live)
                return
            except PermissionError:
                # Windows refuses to replace a file something still has open; a virus
                # scanner does the same for a moment.
                if attempt == SWAP_ATTEMPTS - 1:
                    raise
                time.sleep(SWAP_BACKOFF_SECONDS * (attempt + 1))
    finally:
        staged.unlink(missing_ok=True)


class NewerSchemaError(RuntimeError):
    """
    A database that a newer Chronicler has already upgraded, so this one cannot open it.
    `kind` is "chronicle" or "workspace", so a client can say so in the user's language; the
    message itself is English, for logs and the server's console.
    """

    def __init__(self, chain: str):
        self.kind = "chronicle" if chain == "project" else "workspace"
        what = self.kind
        super().__init__(
            f"This {what} was made by a newer version of Chronicler. "
            "Update Chronicler to open it; the file is unchanged."
        )


@cache
def _known_revisions(chain: str) -> frozenset[str]:
    """The revisions this version ships, read once: they cannot change while it runs."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / chain))
    return frozenset(
        script.revision for script in ScriptDirectory.from_config(cfg).walk_revisions()
    )


@cache
def _head_revisions(chain: str) -> frozenset[str]:
    """The revisions a database of this chain is stamped with once fully migrated."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / chain))
    return frozenset(ScriptDirectory.from_config(cfg).get_heads())


def _behind_head(path: Path) -> bool:
    """
    Whether the project.db at `path` is stamped with a revision this version knows and
    would migrate. Read-only. False for anything else (missing, unreadable, newer, not a
    Chronicler file), which opening it reports better.
    """
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        stamped = {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")}
    except sqlite3.Error:
        return False
    finally:
        connection.close()
    return (
        bool(stamped)
        and stamped <= _known_revisions("project")
        and (stamped != _head_revisions("project"))
    )


def _refuse_newer_schema(connection: Connection, chain: str) -> None:
    """
    Raises NewerSchemaError if the database is stamped with a revision this version does
    not have. Without it Alembic stops with "Can't locate revision identified by '...'",
    which tells the user nothing about what to do. A new database has no stamp yet.
    """
    if not inspect(connection).has_table("alembic_version"):
        return
    stamped = {
        row[0] for row in connection.exec_driver_sql("SELECT version_num FROM alembic_version")
    }
    if not stamped <= _known_revisions(chain):
        raise NewerSchemaError(chain)


def _run_alembic_upgrade(connection: Connection, chain: str) -> None:
    """
    Run one migration chain ("archive" or "project") to head against an already-open sync
    connection - see chronicler/migrations/<chain>/env.py, which picks this connection up
    via config.attributes["connection"] instead of opening its own engine.

    Refuses a database that a newer Chronicler has upgraded, before touching it.
    """
    # Imported here: thin clients never migrate, and alembic costs about half a second.
    from alembic import command
    from alembic.config import Config

    _refuse_newer_schema(connection, chain)
    logger.info(f"Running {chain} migrations")
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / chain))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


class LinkRefusedError(ValueError):
    """
    A file that cannot be linked as a chronicle. `reason` is one of `REASONS`, so a client
    can say why in its own language; `detail` is the underlying error, if any.
    """

    REASONS = {
        "not_found": "no such file",
        "not_chronicler": "not a Chronicler database",
        "newer_version": "made by a newer version of Chronicler",
        "not_allowed": "outside the folders this server allows chronicles in",
        "unreadable": "could not be read",
    }

    def __init__(self, path: Path | str, reason: str, detail: str = ""):
        self.path = str(path)
        self.reason = reason
        self.detail = detail
        suffix = f" ({detail})" if detail else ""
        super().__init__(f"Cannot link {path}: {self.REASONS[reason]}{suffix}")


def check_linkable_project(path: Path) -> None:
    """
    Raises LinkRefusedError unless `path` is a project.db this version of Chronicler can
    open. Read-only, and before anything is registered: opening a project runs its
    migrations, which would write Chronicler's tables into any SQLite file it was given.
    """
    if not path.is_file():
        raise LinkRefusedError(path, "not_found")
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise LinkRefusedError(path, "unreadable", str(error)) from error
    try:
        revisions = {
            row[0] for row in connection.execute("SELECT version_num FROM alembic_version")
        }
    except sqlite3.DatabaseError as error:
        # "file is not a database", or "no such table" for a SQLite file of something else.
        if "locked" in str(error) or "busy" in str(error):
            raise LinkRefusedError(path, "unreadable", str(error)) from error
        raise LinkRefusedError(path, "not_chronicler") from error
    finally:
        connection.close()
    if not revisions:
        raise LinkRefusedError(path, "not_chronicler")
    if not revisions <= _known_revisions("project"):
        raise LinkRefusedError(path, "newer_version")


EXPORTS_DIR = "exports"


def _clear_files(directory: Path) -> None:
    """Removes the files directly in `directory`, if it exists. Ones in use are skipped."""
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                logger.warning(f"Could not remove leftover export {path}")


class DatabaseManager:
    def __init__(self, workspace_path: Path, busy_timeout: float = 5.0):
        """
        `busy_timeout` is how many seconds a connection waits on another one's write lock
        before raising "database is locked". Tests lower it so contention fails fast.
        """
        self.workspace_path = workspace_path
        self.archive_db_path = workspace_path / "chronicler.db"
        self._connect_args = {"timeout": busy_timeout}
        self.archive_engine = create_async_engine(
            f"sqlite+aiosqlite:///{self.archive_db_path}", connect_args=self._connect_args
        )
        self.archive_session_factory = async_sessionmaker(
            self.archive_engine, expire_on_commit=False
        )
        self._project_engines: dict[str, AsyncEngine] = {}
        self._linked_paths: dict[str, Path | None] = {}
        # Bumped by `close_project`, so a lookup that read the row before a close cannot
        # remember what it read after it.
        self._closes: dict[str, int] = {}
        self._migration_lock = asyncio.Lock()
        self._chronicle_locks: dict[str, asyncio.Lock] = {}
        self._workspace_lock = WorkspaceLock(workspace_path)

    async def init_archive(self):
        """
        Opens the workspace for this process. Raises WorkspaceLockedError if another
        process has it open: one workspace belongs to one process. Raises
        WorkspaceLockUnavailableError if its filesystem cannot take the lock at all, and
        WorkspaceNotWritableError if the folder cannot be written to. See docs/storage.md.
        """
        self._workspace_lock.acquire()
        try:
            (self.workspace_path / "imports").mkdir(parents=True, exist_ok=True)
            _clear_files(self.workspace_path / EXPORTS_DIR)
            async with self._migration_lock:
                async with self.archive_engine.begin() as conn:
                    await conn.run_sync(_run_alembic_upgrade, "archive")
        except Exception:
            self._workspace_lock.release()
            raise

    def get_imports_path(self) -> Path:
        path = self.workspace_path / "imports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_exports_path(self) -> Path:
        """
        Where an archive is built before it is handed over: on the workspace's disk, since a
        system temporary directory can be memory. Each file there belongs to one export in
        flight, so whatever is left when the workspace opens was abandoned and is removed.
        """
        path = self.workspace_path / EXPORTS_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_chronicle_sources_path(self, chronicle_id: str) -> Path:
        """
        Durable per-chronicle storage for audio sources (as opposed to
        get_imports_path()'s shared scratch space, which a worker is free to
        overwrite/lose).
        """
        return self.ensure_sources_path_for(chronicle_id)

    def sources_path_for(self, chronicle_id: str, project_path: Path | None = None) -> Path:
        """
        A chronicle's audio directory: beside a linked project.db, otherwise in the
        workspace. A linked chronicle's files were never in the workspace, so looking
        there made every one of its sources read as missing. See docs/storage.md.

        A pure lookup: reading must not create folders. Use `ensure_sources_path_for`
        when about to write audio.
        """
        return self._chronicle_root(chronicle_id, project_path) / "sources"

    def ensure_sources_path_for(self, chronicle_id: str, project_path: Path | None = None) -> Path:
        path = self.sources_path_for(chronicle_id, project_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def snapshots_path_for(self, chronicle_id: str, project_path: Path | None = None) -> Path:
        """Where copies of a chronicle's database go before a destructive change."""
        path = self._chronicle_root(chronicle_id, project_path) / "snapshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _chronicle_root(self, chronicle_id: str, project_path: Path | None) -> Path:
        """The directory a chronicle's project.db lives in, linked or not."""
        if project_path is not None:
            return project_path.parent
        return self.workspace_path / "chronicles" / chronicle_id

    def get_archive_session(self) -> AsyncSession:
        return self.archive_session_factory()

    async def project_path_for(
        self, chronicle_id: UUID | str, must_exist: bool = False
    ) -> Path | None:
        """
        A linked chronicle's project.db, wherever the user put it; None is the default
        location in the workspace. Read through a short archive session of its own, so a
        caller's open session is never touched, and remembered until `close_project`.

        With `must_exist`, a chronicle with no row raises LookupError (deleted while a task
        waited, or never there), and a linked one whose file has moved FileNotFoundError:
        reading must not create a new empty database. Without it an unknown chronicle is
        simply not linked.
        """
        key = str(chronicle_id)
        if key in self._linked_paths:
            path = self._linked_paths[key]
        else:
            closes = self._closes.get(key, 0)
            async with self.get_archive_session() as session:
                row = (
                    await session.execute(
                        select(DBChronicle.project_path).where(DBChronicle.id == key)
                    )
                ).first()
            if row is None:
                if must_exist:
                    raise LookupError(f"No chronicle {key}")
                return None
            path = Path(row[0]) if row[0] else None
            # Not remembered if `close_project` ran while the row was read: the row may
            # have gone or changed since, and the next lookup reads it again.
            if self._closes.get(key, 0) == closes:
                self._linked_paths[key] = path
        if must_exist and path and not path.is_file():
            raise FileNotFoundError(f"The linked project database {path} was not found")
        return path

    async def would_upgrade_linked(self, chronicle_id: UUID | str) -> bool:
        """
        Whether opening this chronicle would migrate a linked project.db that this process
        has not opened yet. Its file may be shared, and once upgraded an older Chronicler
        cannot open it, so only an explicit open should do that - not, say, a search
        across the workspace. A chronicle in the workspace is never "linked" here. See
        docs/storage.md.
        """
        key = str(chronicle_id)
        if key in self._project_engines:
            return False
        path = await self.project_path_for(key)
        if path is None:
            return False
        return await asyncio.to_thread(_behind_head, path)

    async def get_project_session(
        self, chronicle_id: UUID | str, must_exist: bool = False
    ) -> AsyncSession:
        """
        A session on one chronicle's project database. The caller closes it, with
        `async with`. Prefer `transaction` to write; `must_exist` is described on
        `project_path_for`.
        """
        key = str(chronicle_id)
        path = await self.project_path_for(key, must_exist=must_exist)
        engine = await self._project_engine(key, path)
        return async_sessionmaker(engine, expire_on_commit=False)()

    @asynccontextmanager
    async def transaction(
        self, chronicle_id: UUID | str, must_exist: bool = True
    ) -> AsyncIterator[AsyncSession]:
        """
        One project database transaction: committed when the block ends, rolled back if it
        raises. Do not call `commit` inside it.
        """
        session = await self.get_project_session(chronicle_id, must_exist=must_exist)
        async with session, session.begin():
            yield session

    async def _project_engine(
        self, chronicle_id: str, custom_path: Path | None = None
    ) -> AsyncEngine:
        """
        The engine for one chronicle, creating and migrating it at most once.

        `NullPool`: a connection lives only as long as its session, so a cached engine holds
        no thread and no open file. The cache is what remembers that a database is migrated.

        One lock for every chronicle, not one per chronicle: Alembic drives migrations
        through a process-global proxy, so two chains running concurrently corrupt each
        other's context even when they target different files. See docs/storage.md.
        """
        # The chronicle's own lock first: a restore holds it while it swaps the file, so
        # nothing reopens the database between closing it and the swap.
        async with self._chronicle_lock(chronicle_id):
            return await self._open_project_engine(chronicle_id, custom_path)

    def _chronicle_lock(self, chronicle_id: str) -> asyncio.Lock:
        return self._chronicle_locks.setdefault(chronicle_id, asyncio.Lock())

    async def _open_project_engine(
        self, chronicle_id: str, custom_path: Path | None
    ) -> AsyncEngine:
        engine = self._project_engines.get(chronicle_id)
        if engine is not None:
            return engine

        async with self._migration_lock:
            engine = self._project_engines.get(chronicle_id)
            if engine is not None:
                return engine

            if custom_path:
                project_db_path = custom_path
            else:
                project_db_path = self.workspace_path / "chronicles" / chronicle_id / "project.db"
            project_db_path.parent.mkdir(parents=True, exist_ok=True)

            engine = create_async_engine(
                f"sqlite+aiosqlite:///{project_db_path}",
                connect_args=self._connect_args,
                poolclass=NullPool,
            )
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(_run_alembic_upgrade, "project")
            except Exception:
                await engine.dispose()
                raise

            self._project_engines[chronicle_id] = engine
            return engine

    async def snapshot_project(
        self, chronicle_id: UUID | str, destination: Path, must_exist: bool = True
    ) -> Path:
        """
        Writes a consistent copy of one chronicle's database to `destination`.

        `VACUUM INTO` rather than a file copy: another session may be writing to the file,
        so copying it could catch a write half-made. SQLite builds the copy from committed
        pages instead, without disturbing that session. See docs/storage.md.

        `must_exist` as on `project_path_for`: copying a linked database that has moved
        must not create an empty one in its place.
        """
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite {destination}")

        key = str(chronicle_id)
        path = await self.project_path_for(key, must_exist=must_exist)
        destination.parent.mkdir(parents=True, exist_ok=True)
        engine = await self._project_engine(key, path)
        literal = str(destination).replace("'", "''")
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"VACUUM INTO '{literal}'")
        return destination

    async def snapshot_before(
        self, chronicle_id: UUID | str, kind: str, must_exist: bool = True
    ) -> Path:
        """
        Copies the chronicle's database to `snapshots/before-<kind>-<id>-<time>.db` beside its
        project.db, then prunes that kind to `SNAPSHOTS_KEPT`. Call it before a change that
        drops or replaces text, outside any transaction: VACUUM INTO cannot run inside one.
        See docs/storage.md.
        """
        key = str(chronicle_id)
        # Checked before the snapshots folder is made beside a linked file that has moved.
        path = await self.project_path_for(key, must_exist=must_exist)
        directory = self.snapshots_path_for(key, path)
        prefix = f"before-{kind}-{key}-"
        destination = directory / f"{prefix}{datetime.now().strftime(SNAPSHOT_STAMP)}.db"
        await self.snapshot_project(key, destination, must_exist=must_exist)
        self._prune_snapshots(directory, prefix)
        return destination

    @staticmethod
    def _prune_snapshots(directory: Path, prefix: str) -> None:
        snapshots = sorted(directory.glob(f"{prefix}*.db"))
        oldest, rest = snapshots[:1], snapshots[1:]
        for old in rest[: max(len(rest) - (SNAPSHOTS_KEPT - len(oldest)), 0)]:
            old.unlink()

    async def list_snapshots(self, chronicle_id: UUID | str) -> list[Snapshot]:
        """This chronicle's snapshots, newest first. Reads only: no folder is created."""
        key = str(chronicle_id)
        path = await self.project_path_for(key, must_exist=True)
        directory = self._chronicle_root(key, path) / "snapshots"
        if not directory.is_dir():
            return []
        pattern = _snapshot_pattern(key)
        found = []
        for file in directory.iterdir():
            match = pattern.match(file.name)
            if match and file.is_file():
                found.append(
                    Snapshot(
                        name=file.name,
                        kind=match["kind"],
                        created_at=datetime.strptime(match["stamp"], SNAPSHOT_STAMP),
                        size_bytes=file.stat().st_size,
                    )
                )
        return sorted(found, key=lambda s: s.created_at, reverse=True)

    async def restore_project(self, chronicle_id: UUID | str, snapshot_name: str) -> None:
        """
        Replaces the chronicle's database with one of its snapshots.

        The state being replaced is snapshotted first (kind `restore`), so a restore can be
        undone like anything else. The chronicle's own lock is held from closing the engine
        to the swap, and `_project_engine` takes it too: the transcript view loads three
        panels at once, and any of them would otherwise reopen the file in between. The
        restored file is indexed before anything can open it. Raises LookupError for a name
        that is not one of this chronicle's snapshots, and LinkRefusedError for one a newer
        Chronicler wrote. Whatever still has a session open on the file can make the swap
        fail on Windows, after a few retries.
        """
        key = str(chronicle_id)
        path = await self.project_path_for(key, must_exist=True)
        live = path or self.workspace_path / "chronicles" / key / "project.db"
        directory = self._chronicle_root(key, path) / "snapshots"
        snapshot = directory / snapshot_name
        if (
            Path(snapshot_name).name != snapshot_name
            or not _snapshot_pattern(key).match(snapshot_name)
            or not snapshot.is_file()
        ):
            raise LookupError(f"No snapshot {snapshot_name!r} for chronicle {key}")
        await asyncio.to_thread(check_linkable_project, snapshot)

        async with self._chronicle_lock(key):
            await self.close_project(key)
            if live.is_file():
                prefix = f"before-restore-{key}-"
                safety = directory / f"{prefix}{datetime.now().strftime(SNAPSHOT_STAMP)}.db"
                await asyncio.to_thread(_vacuum_into, live, safety)
                self._prune_snapshots(directory, prefix)
            await asyncio.to_thread(_swap_in, snapshot, live)
        logger.info(f"Restored chronicle {key} from {snapshot_name}")

    async def close_project(self, chronicle_id: str) -> None:
        """
        Forgets one chronicle's project database: where it is linked, and that it was
        migrated. The next open looks the chronicle up afresh and migrates whatever file is
        at that path. Call it whenever the row's `project_path` changes or the row goes.

        Connections are not pooled, so none outlive their session; a session still open
        when this runs keeps its file open until it closes. See docs/storage.md.
        """
        self._closes[chronicle_id] = self._closes.get(chronicle_id, 0) + 1
        self._linked_paths.pop(chronicle_id, None)
        engine = self._project_engines.pop(chronicle_id, None)
        if engine is not None:
            await engine.dispose()

    async def close_all(self):
        await self.archive_engine.dispose()
        for engine in self._project_engines.values():
            await engine.dispose()
        self._project_engines.clear()
        self._linked_paths.clear()
        self._workspace_lock.release()

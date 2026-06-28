"""Pi coding agent project discovery and session management.

This module provides functionality for discovering pi coding agent sessions,
grouping them by working directory (project), and listing sessions.

Pi stores sessions under:
    ~/.pi/agent/sessions/--<path>--/<timestamp>_<uuid>.jsonl

The directory slug encodes the working directory path, but we do NOT parse
the slug — we read ``cwd`` from the session header, which is more robust.
Sessions are grouped into projects by that ``cwd`` value.

The sidecar file ``~/.pi/agent/sessions/.wingman-titles.json`` lives in the
same directory tree but is NOT a session file (wrong extension) and is
automatically excluded by the ``*.jsonl`` glob pattern.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Process-scoped discovery cache keyed by resolved pi_data_dir path.
# Avoids redundant full-scan rglob on every call to list_all_projects() /
# find_project_by_name() within a single CLI invocation.
#
# Cache semantics: results are valid for the lifetime of the process.
# Call clear_pi_workspace_cache() before re-scanning (e.g. in tests or
# long-running daemons that may observe filesystem changes).
_workspace_cache: Dict[Path, List["PiWorkspace"]] = {}


def _safe_mtime(path: Path) -> float:
    """Return the mtime of *path*, or 0.0 on any OS error.

    Prevents a single unreadable/deleted file from aborting the sort during
    session discovery or workspace file listing.
    """
    try:
        return path.stat().st_mtime
    except OSError as exc:
        logger.warning("Cannot stat %s (skipping in sort): %s", path, exc)
        return 0.0


@dataclass
class PiSessionInfo:
    """Lightweight session info used during project discovery.

    Attributes:
        session_id: UUID of the session (from the session header).
        file_path: Absolute path to the session JSONL file.
        cwd: Working directory where the session was started.
        timestamp: Session start timestamp (ISO-8601 string).
    """

    session_id: str
    file_path: Path
    cwd: str
    timestamp: str


@dataclass
class PiWorkspace:
    """Represents a pi project — all sessions sharing the same cwd.

    Attributes:
        workspace_path: Full cwd path string (the project directory).
        workspace_name: Human-readable name (basename of cwd).
        sessions: Ordered list of sessions (newest first).
        session_count: Number of sessions in this workspace.
        last_modified: Timestamp of the most recent session, formatted as
            ``YYYY-MM-DD HH:MM:SS``, or ``"Unknown"`` if unavailable.
        pi_data_dir: Path to the ~/.pi/agent directory.
    """

    workspace_path: str
    workspace_name: str
    sessions: List[PiSessionInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    pi_data_dir: Optional[Path] = None
    _latest_ts: Optional[datetime] = field(default=None, repr=False, compare=False)


def _scan_session_files(sessions_dir: Path) -> List[Path]:
    """Recursively find all pi session JSONL files under the sessions directory.

    Uses ``rglob("*.jsonl")`` which naturally excludes the ``.wingman-titles.json``
    sidecar (wrong extension) and any other non-JSONL files.

    Args:
        sessions_dir: Path to ``~/.pi/agent/sessions/``.

    Returns:
        List of JSONL file paths sorted by modification time (newest first).
    """
    if not sessions_dir.exists():
        return []

    session_files = [f for f in sessions_dir.rglob("*.jsonl") if f.is_file()]
    session_files.sort(
        key=lambda f: _safe_mtime(f),
        reverse=True,
    )
    return session_files


def _parse_session_header_lightweight(file_path: Path) -> Optional[PiSessionInfo]:
    """Read only line 1 of a session file for fast project discovery.

    Delegates to ``parse_pi_session_meta`` and converts the returned header
    dict to a ``PiSessionInfo``. Skips the file silently (logs a warning)
    if parsing fails for any reason so that a single corrupt file does not
    abort discovery.

    Args:
        file_path: Path to a pi session JSONL file.

    Returns:
        PiSessionInfo, or None if the file cannot be parsed.
    """
    # Import here to avoid a circular import; pi_parser imports from models
    # which is safe, but keeping the import local avoids module-level coupling.
    from .pi_parser import parse_pi_session_meta
    from .exceptions import ChatFileNotFoundError, InvalidChatFileError

    try:
        header = parse_pi_session_meta(file_path)
        return PiSessionInfo(
            session_id=header.get("id", file_path.stem),
            file_path=file_path,
            cwd=header.get("cwd", ""),
            timestamp=header.get("timestamp", ""),
        )
    except (ChatFileNotFoundError, InvalidChatFileError) as exc:
        logger.warning("Failed to parse pi session header from %s: %s", file_path, exc)
        return None
    except Exception as exc:
        logger.warning(
            "Unexpected error reading pi session header from %s: %s", file_path, exc
        )
        return None


def discover_pi_workspaces(
    pi_data_dir: Path,
    use_cache: bool = True,
) -> List[PiWorkspace]:
    """Discover all pi projects by scanning sessions and grouping by cwd.

    Reads the session header (line 1 only) of every JSONL file under
    ``<pi_data_dir>/sessions/``, groups them by ``cwd``, and returns
    a list of PiWorkspace objects sorted newest-first.

    Results are cached per ``pi_data_dir`` for the lifetime of the process
    (see ``_workspace_cache``).  Pass ``use_cache=False`` to force a fresh
    scan, e.g. in long-running processes or after known filesystem changes.
    Call ``clear_pi_workspace_cache()`` to invalidate all cached results.

    Args:
        pi_data_dir: Path to the ``~/.pi/agent`` directory.
        use_cache: If ``True`` (default), return cached results when available.
            Set to ``False`` to bypass the cache and re-scan the filesystem.

    Returns:
        List of PiWorkspace objects (one per unique cwd), sorted by
        ``last_modified`` descending. Returns ``[]`` when the sessions
        directory is absent or contains no valid session files.
    """
    cache_key = pi_data_dir.resolve()
    if use_cache and cache_key in _workspace_cache:
        logger.debug("Returning cached pi workspaces for %s", cache_key)
        return _workspace_cache[cache_key]

    sessions_dir = pi_data_dir / "sessions"

    if not sessions_dir.exists():
        logger.debug("Pi sessions directory not found: %s", sessions_dir)
        return []

    session_files = _scan_session_files(sessions_dir)
    logger.debug("Found %d pi session files", len(session_files))

    # Group PiSessionInfo objects by cwd
    cwd_groups: Dict[str, List[PiSessionInfo]] = {}

    for file_path in session_files:
        info = _parse_session_header_lightweight(file_path)
        if info is None:
            continue
        # Use cwd as the grouping key; fall back to parent directory name for
        # sessions whose header lacks a cwd field so they remain discoverable.
        group_key = info.cwd if info.cwd else str(file_path.parent)
        cwd_groups.setdefault(group_key, []).append(info)

    # Build PiWorkspace per cwd
    workspaces: List[PiWorkspace] = []

    for cwd, sessions in cwd_groups.items():
        workspace_name = Path(cwd).name or cwd

        # Derive last_modified from the newest session timestamp
        last_modified = "Unknown"
        latest_ts: Optional[datetime] = None

        for session in sessions:
            if session.timestamp:
                try:
                    ts = datetime.fromisoformat(
                        session.timestamp.replace("Z", "+00:00")
                    )
                    # Normalize naive datetimes (no tzinfo) to UTC so all
                    # timestamps are comparable in the sort key.
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                except (ValueError, TypeError):
                    pass

        if latest_ts is not None:
            last_modified = latest_ts.strftime("%Y-%m-%d %H:%M:%S")

        workspaces.append(
            PiWorkspace(
                workspace_path=cwd,
                workspace_name=workspace_name,
                sessions=sessions,
                session_count=len(sessions),
                last_modified=last_modified,
                pi_data_dir=pi_data_dir,
                _latest_ts=latest_ts,
            )
        )

    # Sort workspaces newest-first; workspaces with no parseable timestamp sort last.
    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    workspaces.sort(
        key=lambda w: (w._latest_ts is not None, w._latest_ts or _epoch),
        reverse=True,
    )

    logger.info(
        "Discovered %d pi projects from %d sessions",
        len(workspaces),
        len(session_files),
    )
    _workspace_cache[cache_key] = workspaces
    return workspaces


def clear_pi_workspace_cache() -> None:
    """Clear the process-scoped workspace discovery cache.

    Useful in tests or when the caller knows pi session files have changed
    since the last discovery call.
    """
    _workspace_cache.clear()


def get_pi_session_files(workspace: PiWorkspace) -> List[Path]:
    """Return existing session file paths for a PiWorkspace, newest first.

    Args:
        workspace: Discovered PiWorkspace.

    Returns:
        List of session file paths that still exist on disk, sorted by
        modification time descending.
    """
    paths = [s.file_path for s in workspace.sessions if s.file_path.exists()]
    paths.sort(key=lambda f: _safe_mtime(f), reverse=True)
    return paths

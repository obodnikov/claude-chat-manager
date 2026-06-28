"""Wingman title index writer for pi coding agent sessions.

This module provides read-modify-write access to the wingman sidecar index
at ``~/.pi/agent/sessions/.wingman-titles.json``.  It is the only module in
this project that writes to a file owned by another project (sqowe-wingman).

Rules:
- Never overwrite a ``source:"manual"`` entry (user-defined names are sacred).
- Refresh an existing ``source:"llm"`` entry with the latest generated title.
- Atomic write: write to a temp file in the same directory, then os.replace().
- Merge: always preserve ``version`` and all other top-level keys (forward-compat
  with future wingman schema additions).
- Locking: a POSIX advisory lock on a companion ``<path>.lock`` file serialises
  concurrent writers (other export processes, wingman itself) so the
  read-modify-write cycle is race-free.
- Title normalisation: strip whitespace, collapse control chars, enforce max
  length before writing so downstream consumers see clean data.
- Fail-safe: any exception is logged as a warning and returns False — a title
  sync failure must never break an export.
"""

import copy
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Callable, Optional

logger = logging.getLogger(__name__)

# Default structure for a missing or corrupt index file.
DEFAULT_INDEX: dict = {"version": 1, "titles": {}}


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with Z suffix.

    Returns:
        UTC timestamp string, e.g. ``"2026-06-28T12:34:56.789000Z"``.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_title(title: str, max_length: int = 200) -> str:
    """Normalise a raw LLM-generated title for safe storage.

    - Strips leading/trailing whitespace.
    - Removes all ASCII control characters (0x00-0x1F, 0x7F).
    - Collapses repeated whitespace to a single space.
    - Truncates to *max_length* characters.

    Args:
        title: Raw title string from the LLM.
        max_length: Maximum number of characters to keep (default 200).

    Returns:
        Normalised title string, or empty string if the result is blank.
    """
    normalised = title.strip()
    # Replace all ASCII control characters (including NUL, CR, LF, TAB) with space.
    normalised = re.sub(r'[\x00-\x1f\x7f]+', ' ', normalised)
    normalised = re.sub(r' {2,}', ' ', normalised)
    return normalised[:max_length].strip()


def title_index_path(pi_data_dir: Path) -> Path:
    """Derive the wingman title index path from the pi data directory.

    Args:
        pi_data_dir: Root of the pi data directory (``~/.pi/agent`` by default).

    Returns:
        Absolute path to ``.wingman-titles.json`` inside the sessions subdir.
    """
    return pi_data_dir / "sessions" / ".wingman-titles.json"


def load_title_index(path: Path) -> dict:
    """Load the wingman title index from disk.

    Uses a *repair* strategy: if the file parses as a JSON object, preserve all
    top-level keys (forward-compat with future wingman schema additions) and
    coerce ``titles`` to ``{}`` when it is missing or not a dict.  Only falls
    back to ``DEFAULT_INDEX`` when the file is missing, unreadable, or its
    top-level value is not a dict.

    Args:
        path: Path to ``.wingman-titles.json``.

    Returns:
        Parsed (and if necessary repaired) index dict.
    """
    if not path.exists():
        logger.debug(f"Title index not found at {path}, starting fresh")
        return copy.deepcopy(DEFAULT_INDEX)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, dict):
            logger.warning(
                f"Title index at {path} is not a JSON object, treating as empty"
            )
            return copy.deepcopy(DEFAULT_INDEX)

        # Repair: coerce titles to {} when missing or wrong type, but keep
        # every other top-level key so future wingman schema additions survive.
        if not isinstance(data.get("titles"), dict):
            if "titles" in data:
                logger.warning(
                    f"Title index 'titles' field at {path} is not a dict — resetting to {{}}"
                )
            data["titles"] = {}

        # Ensure version is present.
        data.setdefault("version", 1)

        return data

    except json.JSONDecodeError as exc:
        logger.warning(f"Title index at {path} is not valid JSON ({exc}), treating as empty")
        return copy.deepcopy(DEFAULT_INDEX)
    except OSError as exc:
        logger.warning(f"Could not read title index at {path}: {exc}")
        return copy.deepcopy(DEFAULT_INDEX)


def upsert_llm_title(
    path: Path,
    session_id: str,
    title: str,
    model: str,
    msg_count: int,
    now: Callable[[], str] = _utc_now_iso,
) -> bool:
    """Write or refresh an LLM-generated title for a pi session.

    Normalises the title before writing (strip, collapse whitespace, max 200
    chars).  Acquires a POSIX advisory lock on a companion
    ``<path>.lock`` file before executing the read-modify-merge-write cycle so
    that concurrent writers (other export processes, wingman) cannot interleave.

    Cycle:
    1. Normalise title; skip if empty after normalisation.
    2. Lock (``<path>.lock``).
    3. Load the current index (missing/corrupt → repaired/empty default).
    4. If an entry exists with ``source:"manual"``, release lock and return
       ``False`` (user-defined names are never overwritten).
    5. Write / overwrite with ``source:"llm"`` and full metadata.
    6. Persist atomically: temp file in the same directory + ``os.replace()``.
    7. Unlock.

    All exceptions are caught, logged as warnings, and cause the function to
    return ``False`` — a title-sync failure must never interrupt an export.

    Args:
        path: Path to ``.wingman-titles.json``.
        session_id: Pi session UUID (``id`` field from session header).
        title: Raw LLM-generated title string (spaces intact, not slugified).
        model: OpenRouter model identifier used to generate the title.
        msg_count: Number of raw messages in the session file (for wingman
            staleness checks — must reflect the unfiltered session, not the
            post-export message count).
        now: Callable returning a UTC ISO-8601 timestamp string.  Injected for
             deterministic testing; defaults to the real clock.

    Returns:
        ``True`` if the index was updated, ``False`` otherwise.
    """
    try:
        normalised_title = _normalize_title(title)
        if not normalised_title:
            logger.debug(
                f"Skipping title upsert for session {session_id}: "
                "title is empty after normalisation"
            )
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        # Use <filename>.lock (not with_suffix) to avoid collisions.
        lock_path = path.parent / (path.name + ".lock")

        # Open in binary append mode so the file is never truncated and
        # msvcrt.locking can reliably lock a non-empty region on Windows.
        with open(lock_path, "ab") as lock_fh_bin:
            # Ensure at least 1 byte exists (required by msvcrt.locking).
            if lock_fh_bin.tell() == 0:
                lock_fh_bin.write(b"\x00")
                lock_fh_bin.flush()
            lock_fh_bin.seek(0)
            locked = _acquire_lock(lock_fh_bin)
            if not locked:
                logger.warning(
                    f"Could not acquire lock for {path}; skipping wingman title sync "
                    f"to avoid unsafe concurrent write"
                )
                return False
            try:
                index = load_title_index(path)
                titles: dict = index.setdefault("titles", {})

                existing = titles.get(session_id)
                if existing and existing.get("source") == "manual":
                    logger.debug(
                        f"Skipping title upsert for session {session_id}: "
                        "existing entry has source='manual'"
                    )
                    return False

                titles[session_id] = {
                    "title": normalised_title,
                    "source": "llm",
                    "model": model,
                    "generatedAt": now(),
                    "sourceMsgCount": msg_count,
                }

                # Ensure version is preserved (may be absent in default index).
                index.setdefault("version", 1)

                _atomic_write(path, index)

                logger.debug(
                    f"Upserted LLM title for session {session_id}: {normalised_title!r} "
                    f"(model={model}, msgs={msg_count})"
                )
                return True
            finally:
                _release_lock(lock_fh_bin)

    except Exception as exc:
        logger.warning(
            f"Failed to upsert title for session {session_id} in {path}: {exc}"
        )
        return False


def sync_wingman_title(
    pi_data_dir: Path,
    session_id: Optional[str],
    title: str,
    model: str,
    msg_count: int,
    context: str = "export",
) -> None:
    """Convenience wrapper: sync a single LLM title to the wingman index.

    Resolves the index path, calls ``upsert_llm_title``, and logs at the
    appropriate level.  Silently skips when ``session_id`` is falsy.

    This helper centralises model resolution and error handling so that both
    the book (``exporters.py``) and wiki (``wiki_generator.py``) code paths
    call identical logic.

    Args:
        pi_data_dir: Root of the pi data directory (from ``config.pi_data_dir``).
        session_id: Pi session UUID; if ``None`` or empty the call is a no-op.
        title: Raw LLM-generated title (spaces intact, not slugified).
        model: OpenRouter model string used to produce the title.
        msg_count: Number of raw messages in the session file.
        context: Short label for log messages (e.g. ``"book"`` or ``"wiki"``).
    """
    if not session_id:
        return
    try:
        # Create pi_data_dir/sessions if absent (fresh environment).
        sessions_dir = pi_data_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Resolve base after mkdir so the path exists for resolve().
        resolved_base = pi_data_dir.resolve()

        # Path-traversal guard: ensure the derived index path stays within
        # pi_data_dir (guards against symlink-based escape).
        index_path = title_index_path(pi_data_dir)
        # Resolve parent (which now exists) then append the filename.
        resolved_index = index_path.parent.resolve() / index_path.name
        try:
            resolved_index.relative_to(resolved_base)
        except ValueError:
            logger.warning(
                f"Wingman title sync skipped ({context}): "
                f"index path {resolved_index!r} is outside pi_data_dir {resolved_base!r}"
            )
            return
        upsert_llm_title(index_path, session_id, title, model, msg_count)
    except Exception as exc:
        logger.warning(f"Wingman title sync failed ({context}): {exc}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _acquire_lock(fh: "Any") -> bool:
    """Acquire an exclusive advisory lock on *fh* (blocking).

    Uses ``fcntl.flock`` on POSIX (binary or text handle) and
    ``msvcrt.locking`` on Windows.  The file must be opened in binary
    append mode (``"ab"``) with at least one byte written before this
    call so that ``msvcrt.locking`` can lock a non-empty region.

    Args:
        fh: Open binary file handle to use as the lock file.

    Returns:
        ``True`` if the lock was acquired, ``False`` if locking is not
        available on this platform or failed non-fatally.
    """
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_EX)
        return True
    except ImportError:
        pass  # Not POSIX — try Windows path
    except OSError as exc:
        logger.warning(f"fcntl.flock failed: {exc}")
        return False
    try:
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        return True
    except ImportError:
        pass  # Neither fcntl nor msvcrt — truly unsupported platform
    except OSError as exc:
        logger.warning(f"msvcrt.locking failed: {exc}")
        return False
    return False


def _release_lock(fh: "Any") -> None:
    """Release the advisory lock on *fh*.

    Args:
        fh: Open binary file handle that was locked via ``_acquire_lock``.
    """
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)
        return
    except ImportError:
        pass
    except OSError:
        pass
    try:
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    except (ImportError, OSError):
        pass


def _atomic_write(path: Path, data: dict) -> None:
    """Write *data* to *path* atomically using a temp file + os.replace().

    The temp file is created in the same directory so ``os.replace()`` is
    guaranteed to be on the same filesystem (avoids cross-device rename errors).
    The file is fsynced before rename for durability against power loss.

    Args:
        path: Destination file path.
        data: JSON-serialisable dict to write.

    Raises:
        OSError: If the directory does not exist or write/rename fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".wingman-titles-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")  # POSIX convention: end file with newline
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Clean up orphaned temp file before re-raising.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

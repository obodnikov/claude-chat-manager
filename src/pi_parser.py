"""Pi coding agent chat file parsing utilities.

This module handles parsing of pi's JSONL session files and extracting
conversation messages.

Pi stores chat data in session files at:
    ~/.pi/agent/sessions/--<path>--/<timestamp>_<uuid>.jsonl

Each file is JSONL with typed entries:
1. session header (line 1, type="session"): metadata (id, cwd, version, timestamp)
2. message entries (type="message"): conversation turns
3. other lifecycle entries (model_change, compaction, etc.): skipped for export

This module provides functions to:
- Parse session files to extract metadata and messages
- Normalize pi content blocks to plain text
- Convert to ChatMessage objects for unified export
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import ChatFileNotFoundError, InvalidChatFileError
from .models import ChatMessage, ChatSource

logger = logging.getLogger(__name__)

# Message roles to include in exports (matching Codex behaviour)
_EXPORT_ROLES = frozenset({"user", "assistant"})

# Entry types that carry conversation messages
_MESSAGE_ENTRY_TYPE = "message"

# Content block types to extract text from
_TEXT_BLOCK_TYPE = "text"

# Content block types to skip during normalisation
_SKIP_BLOCK_TYPES = frozenset({"thinking", "toolCall", "image"})


@dataclass
class PiSession:
    """Represents a parsed pi coding agent session.

    Attributes:
        session_id: Unique identifier (UUID) for the session — wingman's index key.
        cwd: Working directory where the session was started.
        timestamp: Session start timestamp (ISO-8601 string).
        version: Pi session format version (1, 2, or 3).
        messages: List of raw message dictionaries extracted from the file.
        file_path: Path to the original session JSONL file.
    """

    session_id: str
    cwd: str
    timestamp: str
    version: int
    messages: List[Dict[str, Any]] = field(default_factory=list)
    file_path: Optional[Path] = None


def parse_pi_session_meta(file_path: Path) -> Dict[str, Any]:
    """Parse only the session header (line 1) from a pi session file.

    Lightweight fast-path used during project discovery: reads a single
    line rather than streaming the whole file.

    The implementation is tolerant of missing optional fields (``version``,
    ``cwd``, ``timestamp``) — callers must handle absent or empty values.
    Only ``type == "session"`` is enforced; if any other type is found the
    file is rejected as not a pi session.

    Args:
        file_path: Path to the pi session JSONL file.

    Returns:
        Dictionary with the raw session header fields (at minimum
        ``type="session"``; ``id``, ``cwd``, ``version``, and
        ``timestamp`` are present in well-formed files but may be absent).

    Raises:
        ChatFileNotFoundError: If the file does not exist.
        InvalidChatFileError: If the first line is not valid JSON, is empty,
            or has ``type`` != ``"session"``.
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Pi session file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            # Read the first *non-empty* line as the header so that files
            # with a leading BOM or blank line are handled gracefully.
            header_line = ""
            for raw_line in fh:
                stripped = raw_line.strip()
                if stripped:
                    header_line = stripped
                    break

            if not header_line:
                raise InvalidChatFileError(f"Empty pi session file: {file_path}")

            data = json.loads(header_line)

            if not isinstance(data, dict) or data.get("type") != "session":
                entry_type = (
                    data.get("type") if isinstance(data, dict) else type(data).__name__
                )
                raise InvalidChatFileError(
                    f"First non-empty line is not a pi session header in {file_path}: "
                    f"type={entry_type!r}"
                )

            return data

    except json.JSONDecodeError as exc:
        raise InvalidChatFileError(
            f"Invalid JSON in pi session header {file_path}: {exc}"
        ) from exc


def parse_pi_session_file(file_path: Path) -> PiSession:
    """Parse a pi session JSONL file and return structured session data.

    Streams the entire file, capturing the session header from line 1 and
    collecting type="message" entries whose role is "user" or "assistant".
    All other entry types (model_change, compaction, thinking_level_change,
    etc.) are skipped. Malformed lines are logged and skipped rather than
    aborting the parse.

    Args:
        file_path: Path to the pi session JSONL file.

    Returns:
        PiSession with header metadata and collected message entries.

    Raises:
        ChatFileNotFoundError: If the file does not exist.
        InvalidChatFileError: If no valid session header is found before message entries.
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Pi session file not found: {file_path}")

    header: Optional[Dict[str, Any]] = None
    messages: List[Dict[str, Any]] = []

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            for line_num, raw_line in enumerate(fh, 1):
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping invalid JSON on line %d in %s: %s",
                        line_num,
                        file_path,
                        exc,
                    )
                    continue

                if not isinstance(data, dict):
                    continue

                entry_type = data.get("type", "")

                # The first non-empty valid JSON dict with type="session" is the header.
                # Using a flag rather than line_num == 1 tolerates leading blank lines / BOM.
                if header is None:
                    if entry_type != "session":
                        raise InvalidChatFileError(
                            f"Pi session file missing header (first non-empty entry has "
                            f"type={entry_type!r}): {file_path}"
                        )
                    header = data
                    continue

                # Collect only message entries with relevant roles
                if entry_type == _MESSAGE_ENTRY_TYPE:
                    msg = data.get("message", {})
                    if isinstance(msg, dict) and msg.get("role") in _EXPORT_ROLES:
                        messages.append(
                            {
                                "role": msg.get("role"),
                                "content": msg.get("content", ""),
                                "timestamp": data.get("timestamp"),
                            }
                        )
                # All other types are silently skipped

    except (ChatFileNotFoundError, InvalidChatFileError):
        raise
    except Exception as exc:
        raise InvalidChatFileError(
            f"Failed to read pi session file {file_path}: {exc}"
        ) from exc

    if header is None:
        raise InvalidChatFileError(f"No session header found in {file_path}")

    raw_version = header.get("version")
    try:
        version = int(raw_version) if raw_version is not None else 1
    except (ValueError, TypeError):
        logger.warning(
            "Invalid version value %r in %s, defaulting to 1", raw_version, file_path
        )
        version = 1

    return PiSession(
        session_id=header.get("id", file_path.stem),
        cwd=header.get("cwd", ""),
        timestamp=header.get("timestamp", ""),
        version=version,
        messages=messages,
        file_path=file_path,
    )


def normalize_pi_content(content: Any) -> str:
    """Normalise a pi message's content field to a plain string.

    Pi messages carry content either as a bare string (common for user
    messages) or as a list of typed blocks (common for assistant messages).
    This function extracts readable text from both forms:

    - ``str`` — returned as-is.
    - ``list`` — text fields from blocks of ``type="text"`` are joined with
      newlines; ``thinking``, ``toolCall``, and ``image`` blocks are dropped.
    - Anything else — converted to string via ``str()``.

    Args:
        content: The raw ``content`` value from a pi message entry.

    Returns:
        Normalised plain-text string (may be empty if only non-text blocks
        were present).
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type in _SKIP_BLOCK_TYPES:
                continue
            if block_type == _TEXT_BLOCK_TYPE:
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts)

    return str(content) if content else ""


def extract_pi_messages(session: PiSession) -> List[ChatMessage]:
    """Extract ChatMessage objects from a parsed PiSession.

    Applies ``normalize_pi_content`` to each message and discards entries
    that are empty after normalisation.

    Args:
        session: Parsed PiSession object.

    Returns:
        List of ChatMessage objects with ``source=ChatSource.PI`` and
        ``execution_id`` set to the session UUID.
    """
    chat_messages: List[ChatMessage] = []

    for msg in session.messages:
        role = msg.get("role", "unknown")
        raw_content = msg.get("content", "")
        timestamp = msg.get("timestamp")

        normalised = normalize_pi_content(raw_content)
        if not normalised.strip():
            # Skip messages that are empty after normalisation (e.g. image-only)
            continue

        chat_messages.append(
            ChatMessage(
                role=role,
                content=normalised,
                timestamp=timestamp,
                tool_result=None,
                source=ChatSource.PI,
                execution_id=session.session_id,
                context_items=None,
            )
        )

    return chat_messages

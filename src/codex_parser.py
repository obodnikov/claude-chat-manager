"""OpenAI Codex CLI chat file parsing utilities.

This module handles parsing of Codex's JSONL rollout files and
extracting conversation messages.

Codex stores chat data in rollout files at:
    ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl

Each file is JSONL with typed entries:
1. session_meta (line 1): Session metadata (id, cwd, model, git info)
2. response_item: Conversation content (messages, tool calls, reasoning)
3. event_msg: Lifecycle events (skip for export)
4. turn_context: Turn metadata (skip for export)

This module provides functions to:
- Parse rollout files to extract session metadata and messages
- Normalize Codex content blocks to plain text
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


@dataclass
class CodexSession:
    """Represents a parsed Codex CLI session.

    Attributes:
        session_id: Unique identifier (UUID) for the session
        cwd: Working directory where session was started
        model: Model used (e.g., "gpt-5.3-codex")
        timestamp: Session start timestamp (ISO-8601)
        cli_version: Codex CLI version string
        model_provider: Model provider (e.g., "openai")
        git_branch: Git branch at session start (optional)
        git_repo_url: Git remote URL (optional)
        messages: List of raw message dictionaries extracted from rollout
        file_path: Path to the original rollout file
    """
    session_id: str
    cwd: str
    model: str
    timestamp: str
    cli_version: str
    model_provider: str = "openai"
    git_branch: Optional[str] = None
    git_repo_url: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    file_path: Optional[Path] = None


def parse_codex_session_meta(file_path: Path) -> Dict[str, Any]:
    """Parse only the session_meta header from a Codex rollout file.

    This is a lightweight function that reads only the first line,
    used during project discovery to get cwd and session info
    without parsing the entire conversation.

    Args:
        file_path: Path to the rollout JSONL file

    Returns:
        Dictionary with session metadata fields

    Raises:
        ChatFileNotFoundError: If file doesn't exist
        InvalidChatFileError: If first line is not valid session_meta
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Rollout file not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if not first_line:
                raise InvalidChatFileError(f"Empty rollout file: {file_path}")

            data = json.loads(first_line)

            if data.get('type') != 'session_meta':
                raise InvalidChatFileError(
                    f"First line is not session_meta in {file_path}: type={data.get('type')}"
                )

            return data.get('payload', {})
    except json.JSONDecodeError as e:
        raise InvalidChatFileError(f"Invalid JSON in {file_path}: {e}")


def parse_codex_rollout_file(file_path: Path) -> CodexSession:
    """Parse a Codex rollout JSONL file and return structured session data.

    Reads the entire file, extracting:
    - Session metadata from line 1 (session_meta)
    - User and assistant messages from response_item entries
    - Model name from turn_context if not in session_meta
    - Filters out developer messages, reasoning, tool calls, events

    Args:
        file_path: Path to the rollout JSONL file

    Returns:
        CodexSession with parsed data

    Raises:
        ChatFileNotFoundError: If file doesn't exist
        InvalidChatFileError: If file format is invalid
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Rollout file not found: {file_path}")

    session_meta = None
    messages = []
    model_name = None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON on line {line_num} in {file_path}: {e}")
                    continue

                entry_type = data.get('type', '')
                payload = data.get('payload', {})
                timestamp = data.get('timestamp')

                # Line 1: session_meta
                if entry_type == 'session_meta':
                    session_meta = payload
                    continue

                # Capture model from turn_context if not yet found
                if entry_type == 'turn_context' and model_name is None:
                    model_name = payload.get('model', '')

                # Conversation messages
                if entry_type == 'response_item':
                    payload_type = payload.get('type', '')
                    role = payload.get('role', '')

                    # Only include user and assistant messages
                    if payload_type == 'message' and role in ('user', 'assistant'):
                        messages.append({
                            'role': role,
                            'content': payload.get('content', []),
                            'timestamp': timestamp,
                            'phase': payload.get('phase')
                        })

                # Skip all other types: event_msg, compacted, etc.

    except (ChatFileNotFoundError, InvalidChatFileError):
        raise
    except Exception as e:
        raise InvalidChatFileError(f"Failed to read rollout file {file_path}: {e}")

    if session_meta is None:
        raise InvalidChatFileError(f"No session_meta found in {file_path}")

    # Extract git info
    git_info = session_meta.get('git', {}) or {}

    # Use model from session_meta first, fall back to turn_context
    effective_model = session_meta.get('model', '') or model_name or 'unknown'

    return CodexSession(
        session_id=session_meta.get('id', file_path.stem),
        cwd=session_meta.get('cwd', ''),
        model=effective_model,
        timestamp=session_meta.get('timestamp', ''),
        cli_version=session_meta.get('cli_version', ''),
        model_provider=session_meta.get('model_provider', 'openai'),
        git_branch=git_info.get('branch'),
        git_repo_url=git_info.get('repository_url'),
        messages=messages,
        file_path=file_path
    )


def normalize_codex_content(content: Any) -> str:
    """Normalize Codex's structured content to plain text.

    Handles content arrays with input_text/output_text blocks.

    Args:
        content: Message content — string or list of content blocks

    Returns:
        Normalized string content
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get('type', '')
            if block_type in ('input_text', 'output_text'):
                text = block.get('text', '')
                if text:
                    text_parts.append(text)
        return '\n'.join(text_parts) if text_parts else ''

    return str(content) if content else ''


def extract_codex_messages(session: CodexSession) -> List[ChatMessage]:
    """Extract ChatMessage objects from a parsed Codex session.

    Args:
        session: Parsed CodexSession object

    Returns:
        List of ChatMessage objects with source=ChatSource.CODEX
    """
    chat_messages = []

    for msg in session.messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        timestamp = msg.get('timestamp')

        # Normalize content (handle input_text/output_text blocks)
        normalized_content = normalize_codex_content(content)

        # Skip empty messages
        if not normalized_content.strip():
            continue

        chat_msg = ChatMessage(
            role=role,
            content=normalized_content,
            timestamp=timestamp,
            tool_result=None,
            source=ChatSource.CODEX,
            execution_id=session.session_id,
            context_items=None
        )
        chat_messages.append(chat_msg)

    return chat_messages

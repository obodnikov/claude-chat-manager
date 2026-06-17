"""Cline (VS Code extension) chat file parsing utilities.

This module handles parsing of the Cline VS Code extension's JSON
conversation files and extracting conversation messages.

The VS Code extension stores chat data in VS Code globalStorage:
    ~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/
    (or the OS-equivalent globalStorage path)

Each task (conversation) has:
1. ui_messages.json (PRIMARY): Rich UI event log with say/ask types
2. api_conversation_history.json (FALLBACK): Raw Anthropic API transcript

The host-agnostic message-schema logic (say/ask classification, ask-text
decoding, content normalization) lives in ``cline_messages`` and is shared
with the future Cline CLI source.

This module provides functions to:
- Parse Cline task directories to extract session metadata and messages
- Handle primary/fallback conversation source strategy
- Convert to ChatMessage objects for unified export
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cline_messages import (
    classify_ask,
    classify_say,
    decode_ask_text,
    normalize_cline_content,
)
from .exceptions import ChatFileNotFoundError, InvalidChatFileError
from .models import ChatMessage, ChatSource

logger = logging.getLogger(__name__)


@dataclass
class ClineVscodeSession:
    """Represents a parsed Cline VS Code task/session.

    Attributes:
        task_id: Unique identifier (epoch-ms string) for the task
        cwd: Working directory where task was initialized
        title: Task title (from taskHistory.task or first user msg)
        timestamp: Task start timestamp (epoch ms or ISO string)
        model: Model used (e.g., "claude-opus-4.6")
        cline_version: Cline extension version
        total_cost: Total cost of the task
        messages: List of raw message dictionaries extracted
        task_dir: Path to the task directory
    """
    task_id: str
    cwd: str
    title: str
    timestamp: str
    model: str = ""
    cline_version: str = ""
    total_cost: float = 0.0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    task_dir: Optional[Path] = None


def parse_cline_vscode_task(
    task_dir: Path,
    task_id: str = "",
    cwd: str = "",
    title: str = "",
    timestamp: str = "",
    model: str = "",
    total_cost: float = 0.0,
) -> ClineVscodeSession:
    """Parse a Cline VS Code task directory and return structured session data.

    Implements the primary/fallback strategy:
    1. Try ui_messages.json first (primary source)
    2. If missing/unreadable/empty, fall back to api_conversation_history.json

    Metadata (cwd, title, timestamp, etc.) can be passed from taskHistory.json
    via the discovery layer (ClineVscodeTaskInfo). If not provided, the parser
    falls back to extracting what it can from task_metadata.json.

    Args:
        task_dir: Path to the task directory (tasks/<task-id>/)
        task_id: Task identifier (defaults to directory name)
        cwd: Working directory from taskHistory.json
        title: Task title from taskHistory.json
        timestamp: Task timestamp from taskHistory.json (epoch ms)
        model: Model identifier from taskHistory.json
        total_cost: Total cost from taskHistory.json

    Returns:
        ClineVscodeSession with parsed data

    Raises:
        ChatFileNotFoundError: If task directory doesn't exist
        InvalidChatFileError: If neither conversation file is valid
    """
    if not task_dir.exists():
        raise ChatFileNotFoundError(f"Cline task directory not found: {task_dir}")

    ui_path = task_dir / "ui_messages.json"
    api_path = task_dir / "api_conversation_history.json"

    messages = []
    task_metadata = {}

    # Try to load task metadata if available
    metadata_path = task_dir / "task_metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                task_metadata = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.debug(f"Could not read task_metadata.json: {e}")

    # Primary: Parse ui_messages.json
    if ui_path.exists():
        try:
            messages = _parse_ui_messages(ui_path)
        except (ChatFileNotFoundError, InvalidChatFileError, OSError,
                json.JSONDecodeError) as e:
            logger.warning(f"ui_messages.json parse failed for {task_dir}: {e}")
            messages = []

    # Fallback: Parse api_conversation_history.json
    if not messages and api_path.exists():
        logger.info(f"Falling back to api_conversation_history.json for {task_dir}")
        try:
            messages = _parse_api_history(api_path)
        except (ChatFileNotFoundError, InvalidChatFileError, OSError,
                json.JSONDecodeError) as e:
            logger.warning(f"api_conversation_history.json parse failed for {task_dir}: {e}")

    if not messages:
        raise InvalidChatFileError(
            f"No valid conversation messages found in {task_dir}"
        )

    # Extract metadata from task_metadata.json if not provided via args
    cline_version = ""
    if task_metadata and isinstance(task_metadata, dict):
        env_history = task_metadata.get('environment_history', [])
        if isinstance(env_history, list) and env_history:
            first_env = env_history[0]
            if isinstance(first_env, dict):
                cline_version = first_env.get('cline_version', '') or ''

        if not model:
            model_usage = task_metadata.get('model_usage', [])
            if isinstance(model_usage, list) and model_usage:
                first_usage = model_usage[0]
                if isinstance(first_usage, dict):
                    model = first_usage.get('model_id', '') or ''

    return ClineVscodeSession(
        task_id=task_id or task_dir.name,
        cwd=cwd,
        title=title,
        timestamp=timestamp,
        model=model,
        cline_version=cline_version,
        total_cost=total_cost,
        messages=messages,
        task_dir=task_dir
    )


def _parse_ui_messages(ui_path: Path) -> List[Dict[str, Any]]:
    """Parse ui_messages.json and extract conversation messages.

    Uses the shared say/ask classification (``cline_messages``) to keep
    user/assistant messages and drop tool/lifecycle noise.

    Args:
        ui_path: Path to ui_messages.json

    Returns:
        List of message dictionaries with role, content, timestamp
    """
    if not ui_path.exists():
        raise ChatFileNotFoundError(f"ui_messages.json not found: {ui_path}")

    try:
        with open(ui_path, 'r', encoding='utf-8') as f:
            ui_messages = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidChatFileError(f"Invalid JSON in {ui_path}: {e}")

    if not isinstance(ui_messages, list):
        raise InvalidChatFileError(f"ui_messages.json is not an array: {ui_path}")

    messages = []

    for entry in ui_messages:
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get('type', '')
        timestamp = entry.get('ts')
        raw_text = entry.get('text')

        # Normalize text defensively: ensure it's a string
        text = str(raw_text) if raw_text is not None else ''

        if entry_type == 'say':
            say_subtype = entry.get('say', '')
            role = classify_say(say_subtype)
            if not role:
                logger.debug(f"Skipping say subtype: {say_subtype}")
                continue
            if text and text.strip():
                messages.append({
                    'role': role,
                    'content': text,
                    'timestamp': timestamp,
                    'subtype': say_subtype
                })

        elif entry_type == 'ask':
            ask_subtype = entry.get('ask', '')
            role = classify_ask(ask_subtype)
            if not role:
                logger.debug(f"Skipping ask subtype: {ask_subtype}")
                continue
            decoded_text = decode_ask_text(ask_subtype, text)
            if decoded_text and decoded_text.strip():
                messages.append({
                    'role': role,
                    'content': decoded_text,
                    'timestamp': timestamp,
                    'subtype': ask_subtype
                })

        # Skip unknown entry types

    return messages


def _parse_api_history(api_path: Path) -> List[Dict[str, Any]]:
    """Parse api_conversation_history.json as fallback.

    Handles Anthropic API message format with content block filtering.

    Args:
        api_path: Path to api_conversation_history.json

    Returns:
        List of message dictionaries with role, content, timestamp
    """
    if not api_path.exists():
        raise ChatFileNotFoundError(f"api_conversation_history.json not found: {api_path}")

    try:
        with open(api_path, 'r', encoding='utf-8') as f:
            api_messages = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidChatFileError(f"Invalid JSON in {api_path}: {e}")

    if not isinstance(api_messages, list):
        raise InvalidChatFileError(f"api_conversation_history.json is not an array: {api_path}")

    messages = []

    for entry in api_messages:
        if not isinstance(entry, dict):
            continue

        role = entry.get('role', '')
        if role not in ('user', 'assistant'):
            continue

        content = entry.get('content', [])

        # Extract text from content blocks, skipping tool_use/tool_result/etc.
        text_parts = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    raw_text = block.get('text', '')
                    text = raw_text if isinstance(raw_text, str) else (
                        str(raw_text) if raw_text is not None else ''
                    )
                    # Strip wrapper noise from user messages
                    if role == 'user':
                        text = _strip_api_wrapper_noise(text)
                    if text and text.strip():
                        text_parts.append(text)
        elif isinstance(content, str):
            text = content
            if role == 'user':
                text = _strip_api_wrapper_noise(text)
            if text and text.strip():
                text_parts.append(text)

        # Skip empty messages (pure tool-result turns)
        if not text_parts:
            continue

        full_text = '\n\n'.join(text_parts)

        messages.append({
            'role': role,
            'content': full_text,
            'timestamp': None,
            'subtype': 'api_history'
        })

    return messages


def _strip_api_wrapper_noise(text: str) -> str:
    """Strip wrapper noise from api_conversation_history user messages.

    Removes:
    - <task>...</task> wrappers (unwraps to inner text)
    - <environment_details>...</environment_details> (drops entirely)
    - task_progress instruction preamble
    - Tool-result feedback blocks

    Args:
        text: Raw user message text

    Returns:
        Cleaned text
    """
    # Remove <environment_details>...</environment_details> entirely
    text = re.sub(r'<environment_details>.*?</environment_details>', '', text, flags=re.DOTALL)

    # Unwrap <task>...</task> to inner text
    task_match = re.search(r'<task>(.*?)</task>', text, re.DOTALL)
    if task_match:
        text = task_match.group(1).strip()

    # TODO: Add more stripping patterns as needed based on real data

    return text.strip()


def extract_cline_vscode_messages(session: ClineVscodeSession) -> List[ChatMessage]:
    """Extract ChatMessage objects from a parsed Cline VS Code session.

    Args:
        session: Parsed ClineVscodeSession object

    Returns:
        List of ChatMessage objects with source=ChatSource.CLINE_VSCODE
    """
    chat_messages = []

    for msg in session.messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        timestamp = msg.get('timestamp')

        # Normalize content
        normalized_content = normalize_cline_content(content)

        # Skip empty messages
        if not normalized_content:
            continue

        chat_msg = ChatMessage(
            role=role,
            content=normalized_content,
            timestamp=timestamp,
            tool_result=None,
            source=ChatSource.CLINE_VSCODE,
            execution_id=session.task_id,
            context_items=None
        )
        chat_messages.append(chat_msg)

    return chat_messages

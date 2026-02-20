# Codex CLI Chat Source — Implementation Guide

## 1. Overview

This document provides a complete implementation guide for adding OpenAI Codex CLI as a third chat source to claude-chat-manager, alongside the existing Claude Desktop and Kiro IDE sources.

**Goal:** Full feature parity with Claude and Kiro sources — project discovery, interactive browsing, all export formats (pretty, markdown, book, wiki), source filtering via `--source codex`, and comprehensive tests.

**Branch:** `feat/codex-1`

---

## 2. What is Codex CLI?

OpenAI Codex CLI is a terminal-based coding assistant (direct competitor to Claude Code). It is installed via `npm i -g @openai/codex` and runs interactively in the terminal.

- **Repository:** [github.com/openai/codex](https://github.com/openai/codex) (Apache-2.0)
- **Home directory:** `~/.codex/` (configurable via `CODEX_HOME` env var)
- **Models:** `codex-1`, `gpt-5.3-codex`, etc.
- **Session format:** JSONL rollout files

---

## 3. Codex Data Storage Structure

```
~/.codex/
├── config.toml              # User configuration
├── auth.json                # Credentials
├── history.jsonl            # Aggregated session transcript history
├── log/                     # Log files
│   └── codex-tui.log
├── sessions/                # Per-session rollout files
│   └── <YYYY>/
│       └── <MM>/
│           └── <DD>/
│               └── rollout-<YYYY-MM-DD>T<HH-MM-SS>-<uuid>.jsonl
├── archived_sessions/       # Archived old sessions
├── shell_snapshots/
├── skills/
└── version.json
```

**Key observations:**
- Sessions are organized by **date** (`YYYY/MM/DD/`), NOT by project/workspace
- Each session file is a JSONL rollout containing the full conversation
- The `session_meta` (first line) contains `cwd` — the working directory, which serves as the project grouping key
- Sessions sharing the same `cwd` belong to the same "project"
- File naming: `rollout-<ISO-date>T<time>-<uuid>.jsonl`

**`history.jsonl`** — Aggregated user input history (one entry per user message):
```json
{"session_id":"<uuid>","ts":1771578091,"text":"user message text"}
```
This file is NOT used for full conversation export — it only contains user inputs.

---

## 4. Codex JSONL Rollout Format — Complete Specification

Each rollout file is JSONL (one JSON object per line). Every line has:
```json
{"timestamp": "<ISO-8601>", "type": "<type>", "payload": {...}}
```

### 4.1 Line Types

| `type` | Description | Count (typical session) |
|--------|-------------|------------------------|
| `session_meta` | Session metadata header (always line 1) | 1 |
| `response_item` | Conversation content (messages, tool calls, reasoning) | ~500+ |
| `event_msg` | Lifecycle events (turn start/complete, token counts) | ~500+ |
| `turn_context` | Turn metadata (model, policies, user instructions) | ~180 |
| `compacted` | Context compaction marker | 0-1 |

### 4.2 `session_meta` (Line 1 — Always Present)

```json
{
  "timestamp": "2026-02-20T09:01:31.862Z",
  "type": "session_meta",
  "payload": {
    "id": "019c7a47-6a4c-78d2-9fb1-27fda2245dd9",
    "timestamp": "2026-02-20T09:00:26.572Z",
    "cwd": "/Users/eobomik/src/eodhd_realtime_candles",
    "originator": "codex_cli_rs",
    "cli_version": "0.104.0",
    "source": "cli",
    "model_provider": "openai",
    "base_instructions": {
      "text": "You are Codex, a coding agent..."
    },
    "git": {
      "commit_hash": "326f75927b893c7fbad509fe763ca865ae93ee32",
      "branch": "fix/pgsql-start",
      "repository_url": "ssh://git@gitlab.obodnikov.com:2222/mike/eodhd_realtime_candles.git"
    }
  }
}
```

**Fields to extract:**
- `payload.id` → session ID (UUID)
- `payload.cwd` → working directory (project grouping key)
- `payload.timestamp` → session start time
- `payload.model_provider` → "openai"
- `payload.cli_version` → Codex CLI version
- `payload.git.branch` → git branch (optional, may be absent)
- `payload.git.repository_url` → git remote URL (optional)

### 4.3 `response_item` — Conversation Content

#### 4.3.1 User Messages
```json
{
  "timestamp": "2026-02-20T09:01:31.862Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "user",
    "content": [
      {
        "type": "input_text",
        "text": "read and analyze docker logs on production server"
      }
    ]
  }
}
```

**Content blocks:** Array of `{"type": "input_text", "text": "..."}` objects.

#### 4.3.2 Assistant Messages
```json
{
  "timestamp": "2026-02-20T09:01:38.318Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "output_text",
        "text": "I'll load and follow the project steering docs..."
      }
    ],
    "phase": "commentary"
  }
}
```

**Content blocks:** Array of `{"type": "output_text", "text": "..."}` objects.
**`phase`** field (assistant only): `"commentary"` for intermediate updates, absent for final answers.

#### 4.3.3 Developer Messages (SKIP — system instructions)
```json
{
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "developer",
    "content": [{"type": "input_text", "text": "<permissions instructions>..."}]
  }
}
```
**Action:** Filter out entirely — these are system/sandbox permission instructions.

#### 4.3.4 Reasoning Items (SKIP — encrypted thinking)
```json
{
  "type": "response_item",
  "payload": {
    "type": "reasoning",
    "summary": [{"type": "summary_text", "text": "**Planning to read steering files**"}],
    "encrypted_content": "gAAAAABpmCLx2XDW4..."
  }
}
```
**Action:** Filter out — contains encrypted chain-of-thought, not user-facing content.

#### 4.3.5 Function Calls (tool invocations)
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "exec_command",
    "arguments": "{\"cmd\":\"rg --files .kirp/steering\"}",
    "call_id": "call_oD4BmkhVOpqQzVElE2aYww0v"
  }
}
```
**Action:** Filter out for book/markdown exports. Include as `[Tool: exec_command]` for verbose mode.

#### 4.3.6 Function Call Outputs
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_oD4BmkhVOpqQzVElE2aYww0v",
    "output": "Chunk ID: da29a1\nWall time: 0.3586 seconds\n..."
  }
}
```
**Action:** Filter out for book/markdown. Include for verbose/raw.

#### 4.3.7 Custom Tool Calls (apply_patch, etc.)
```json
{
  "type": "response_item",
  "payload": {
    "type": "custom_tool_call",
    "status": "completed",
    "call_id": "call_g8GckInw...",
    "name": "apply_patch",
    "input": "*** Begin Patch\n*** Update File: src/websocket_manager.py\n..."
  }
}
```
**Action:** Filter out for book. Include as `[Tool: apply_patch]` for verbose mode.

### 4.4 `event_msg` — Lifecycle Events

#### 4.4.1 Task Started/Complete
```json
{"type": "event_msg", "payload": {"type": "task_started", "turn_id": "...", "model_context_window": 258400}}
{"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "...", "last_agent_message": "..."}}
```

#### 4.4.2 Agent Message (intermediate commentary)
```json
{
  "type": "event_msg",
  "payload": {
    "type": "agent_message",
    "message": "I'll load and follow the project steering docs..."
  }
}
```
**Action:** These duplicate assistant `response_item` messages with `phase: "commentary"`. Skip to avoid duplicates.

#### 4.4.3 Token Count
```json
{
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 8646,
        "cached_input_tokens": 7296,
        "output_tokens": 216,
        "reasoning_output_tokens": 108
      }
    }
  }
}
```
**Action:** Skip (internal metrics).

#### 4.4.4 Other Event Types
- `user_message` — duplicates `response_item` user messages
- `agent_reasoning` — duplicates `reasoning` response items
- `context_compacted` — context compression notification

**Action:** Skip all `event_msg` types for export purposes.

### 4.5 `turn_context` — Turn Metadata

Contains per-turn configuration (model, policies, user instructions). Not conversation content.
**Action:** Skip entirely.

### 4.6 `compacted` — Context Compaction

Marks where context was compressed.
**Action:** Skip entirely.

---

## 5. Filtering Rules Summary

### For Book/Markdown/Wiki Export (conversation only):

**INCLUDE:**
- `response_item` where `payload.type == "message"` AND `payload.role == "user"` — user messages
- `response_item` where `payload.type == "message"` AND `payload.role == "assistant"` — assistant responses

**EXCLUDE everything else:**
- `payload.role == "developer"` — system instructions
- `payload.type == "reasoning"` — encrypted thinking
- `payload.type == "function_call"` — tool invocations
- `payload.type == "function_call_output"` — tool results
- `payload.type == "custom_tool_call"` — apply_patch etc.
- `payload.type == "custom_tool_call_output"` — patch results
- All `event_msg` types — lifecycle events
- All `turn_context` — turn metadata
- `session_meta` — session header
- `compacted` — compression markers

### For Verbose/Raw Export:

Additionally include:
- `function_call` as `[Tool: <name>]` indicators
- `custom_tool_call` as `[Tool: <name>]` indicators

### Content Normalization:

User content: Extract `text` from `{"type": "input_text", "text": "..."}` blocks.
Assistant content: Extract `text` from `{"type": "output_text", "text": "..."}` blocks.

If multiple content blocks exist in one message, join with newlines.

---

## 6. Implementation Steps — Detailed

### Step 1: Update `src/models.py`

**File:** `src/models.py`
**Change:** Add `CODEX` to `ChatSource` enum.

```python
class ChatSource(Enum):
    """Identifies the source of a chat or project.

    Attributes:
        CLAUDE_DESKTOP: Chat from Claude Desktop application
        KIRO_IDE: Chat from Kiro IDE
        CODEX: Chat from OpenAI Codex CLI
        UNKNOWN: Unknown or unspecified source
    """
    CLAUDE_DESKTOP = "claude"
    KIRO_IDE = "kiro"
    CODEX = "codex"
    UNKNOWN = "unknown"
```

No other changes needed in models.py — the existing `ChatMessage` and `ProjectInfo` dataclasses already have all needed fields (`source`, `workspace_path`, `session_ids`).

---

### Step 2: Create `src/codex_parser.py`

**New file.** Pattern follows `src/kiro_parser.py`.

```python
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
from typing import Any, Dict, List, Optional, Tuple

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
```

#### Key Functions:

**`parse_codex_session_meta(file_path: Path) -> Dict[str, Any]`**

Reads only the first line of a rollout file to extract `session_meta`. Used for lightweight scanning during project discovery (no need to parse the entire file).

```python
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
```

**`parse_codex_rollout_file(file_path: Path) -> CodexSession`**

Full parser — reads entire JSONL file, extracts session_meta and all conversation messages.

```python
def parse_codex_rollout_file(file_path: Path) -> CodexSession:
    """Parse a Codex rollout JSONL file and return structured session data.

    Reads the entire file, extracting:
    - Session metadata from line 1 (session_meta)
    - User and assistant messages from response_item entries
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
                            'phase': payload.get('phase')  # "commentary" or None
                        })

                # Skip all other types: event_msg, turn_context, compacted, etc.

    except Exception as e:
        raise InvalidChatFileError(f"Failed to read rollout file {file_path}: {e}")

    if session_meta is None:
        raise InvalidChatFileError(f"No session_meta found in {file_path}")

    # Extract git info
    git_info = session_meta.get('git', {})

    return CodexSession(
        session_id=session_meta.get('id', file_path.stem),
        cwd=session_meta.get('cwd', ''),
        model=session_meta.get('model', 'unknown'),  # Note: model may be in turn_context
        timestamp=session_meta.get('timestamp', ''),
        cli_version=session_meta.get('cli_version', ''),
        model_provider=session_meta.get('model_provider', 'openai'),
        git_branch=git_info.get('branch'),
        git_repo_url=git_info.get('repository_url'),
        messages=messages,
        file_path=file_path
    )
```

**Note on model field:** The `session_meta` may not contain the model name directly — it may only appear in `turn_context` entries. The parser should check `turn_context` entries too if `session_meta` doesn't have it. In observed real files, the model was found in `turn_context.payload.model` as `"gpt-5.3-codex"`. Handle this gracefully:

```python
# Inside the JSONL parsing loop, also capture model from turn_context:
if entry_type == 'turn_context' and model_name is None:
    model_name = payload.get('model', '')
```

**`normalize_codex_content(content: Any) -> str`**

```python
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
```

**`extract_codex_messages(session: CodexSession) -> List[ChatMessage]`**

```python
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
```

---

### Step 3: Create `src/codex_projects.py`

**New file.** Pattern follows `src/kiro_projects.py`.

**Key design challenge:** Codex organizes sessions by date, not by project. We must scan all date directories, parse `session_meta` from each file, and group by `cwd`.

```python
"""OpenAI Codex CLI project discovery and session management.

This module provides functionality for discovering Codex CLI sessions,
grouping them by working directory (project), and listing sessions.

Codex stores sessions organized by date:
    ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl

Sessions are grouped into "projects" by their cwd (working directory)
from the session_meta header.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CodexSessionInfo:
    """Lightweight session info for project discovery.

    Attributes:
        session_id: UUID of the session
        file_path: Path to the rollout JSONL file
        cwd: Working directory where session was started
        timestamp: Session start timestamp
        model: Model used for the session
        git_branch: Git branch (optional)
    """
    session_id: str
    file_path: Path
    cwd: str
    timestamp: str
    model: str = ""
    git_branch: Optional[str] = None


@dataclass
class CodexWorkspace:
    """Represents a Codex project (sessions grouped by cwd).

    Attributes:
        workspace_path: Full cwd path (project directory)
        workspace_name: Human-readable name (basename of cwd)
        sessions: List of sessions in this project
        session_count: Number of sessions
        last_modified: Most recent session timestamp as formatted string
        codex_data_dir: Path to ~/.codex directory
    """
    workspace_path: str
    workspace_name: str
    sessions: List[CodexSessionInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    codex_data_dir: Optional[Path] = None
```

**Key functions:**

```python
def _scan_rollout_files(sessions_dir: Path) -> List[Path]:
    """Recursively find all rollout JSONL files under sessions directory.

    Scans the date-organized directory structure:
    sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl

    Args:
        sessions_dir: Path to ~/.codex/sessions/

    Returns:
        List of paths to rollout files, sorted by modification time (newest first)
    """
    rollout_files = []

    if not sessions_dir.exists():
        return rollout_files

    # Recursively find all .jsonl files matching rollout pattern
    for jsonl_file in sessions_dir.rglob('rollout-*.jsonl'):
        if jsonl_file.is_file():
            rollout_files.append(jsonl_file)

    # Sort by modification time, newest first
    rollout_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return rollout_files


def _parse_session_meta_lightweight(file_path: Path) -> Optional[CodexSessionInfo]:
    """Parse only the first line of a rollout file for project discovery.

    This is optimized for speed — reads only one line per file.

    Args:
        file_path: Path to rollout JSONL file

    Returns:
        CodexSessionInfo or None if parsing fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if not first_line:
                return None

            data = json.loads(first_line)

            if data.get('type') != 'session_meta':
                return None

            payload = data.get('payload', {})
            git_info = payload.get('git', {})

            return CodexSessionInfo(
                session_id=payload.get('id', file_path.stem),
                file_path=file_path,
                cwd=payload.get('cwd', ''),
                timestamp=payload.get('timestamp', ''),
                model=payload.get('model', ''),
                git_branch=git_info.get('branch')
            )
    except (json.JSONDecodeError, IOError, KeyError) as e:
        logger.warning(f"Failed to parse session meta from {file_path}: {e}")
        return None


def discover_codex_workspaces(codex_data_dir: Path) -> List[CodexWorkspace]:
    """Discover all Codex projects by scanning sessions and grouping by cwd.

    Scans all rollout files, reads their session_meta headers,
    and groups sessions by working directory.

    Args:
        codex_data_dir: Path to ~/.codex/ directory

    Returns:
        List of CodexWorkspace objects (one per unique cwd)
    """
    sessions_dir = codex_data_dir / 'sessions'

    if not sessions_dir.exists():
        logger.debug(f"Codex sessions directory not found: {sessions_dir}")
        return []

    # Scan all rollout files
    rollout_files = _scan_rollout_files(sessions_dir)
    logger.debug(f"Found {len(rollout_files)} Codex rollout files")

    # Parse session_meta from each file and group by cwd
    cwd_groups: dict[str, List[CodexSessionInfo]] = {}

    for file_path in rollout_files:
        session_info = _parse_session_meta_lightweight(file_path)
        if session_info and session_info.cwd:
            if session_info.cwd not in cwd_groups:
                cwd_groups[session_info.cwd] = []
            cwd_groups[session_info.cwd].append(session_info)

    # Convert groups to CodexWorkspace objects
    workspaces = []

    for cwd, sessions in cwd_groups.items():
        workspace_name = Path(cwd).name or cwd

        # Calculate last modified from session timestamps
        last_modified = "Unknown"
        latest_timestamp = None

        for session in sessions:
            if session.timestamp:
                try:
                    ts = datetime.fromisoformat(
                        session.timestamp.replace('Z', '+00:00')
                    )
                    if latest_timestamp is None or ts > latest_timestamp:
                        latest_timestamp = ts
                except (ValueError, TypeError):
                    pass

        if latest_timestamp:
            last_modified = latest_timestamp.strftime('%Y-%m-%d %H:%M:%S')

        workspaces.append(CodexWorkspace(
            workspace_path=cwd,
            workspace_name=workspace_name,
            sessions=sessions,
            session_count=len(sessions),
            last_modified=last_modified,
            codex_data_dir=codex_data_dir
        ))

    # Sort workspaces by last_modified (newest first)
    workspaces.sort(key=lambda w: w.last_modified, reverse=True)

    logger.info(f"Discovered {len(workspaces)} Codex projects from {len(rollout_files)} sessions")
    return workspaces


def get_codex_session_files(workspace: CodexWorkspace) -> List[Path]:
    """Get all rollout file paths for a Codex workspace/project.

    Unlike Claude (directory glob) or Kiro (session dir glob),
    Codex sessions are scattered across date directories. This function
    returns the pre-collected file paths from workspace discovery.

    Args:
        workspace: CodexWorkspace containing session info

    Returns:
        List of rollout file paths, sorted by modification time
    """
    paths = [s.file_path for s in workspace.sessions if s.file_path.exists()]
    paths.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return paths
```

---

### Step 4: Update `src/config.py`

**File:** `src/config.py`
**Changes:**

1. Add `_codex_dir` field in `__init__`
2. Load `CODEX_DATA_DIR` in `_load_config()`
3. Add `codex_data_dir` property
4. Add `validate_codex_directory()` method
5. Update `chat_source_filter` to handle `'codex'`

```python
# In __init__:
self._codex_dir: Optional[Path] = None

# In _load_config():
# Codex data directory
codex_dir_env = os.getenv('CODEX_DATA_DIR')
if codex_dir_env:
    self._codex_dir = Path(codex_dir_env)
    logger.info(f"Using CODEX_DATA_DIR from environment: {self._codex_dir}")
else:
    # Default: ~/.codex (same on all platforms, configurable via CODEX_HOME)
    codex_home = os.getenv('CODEX_HOME')
    if codex_home:
        self._codex_dir = Path(codex_home)
    else:
        self._codex_dir = Path.home() / '.codex'
    logger.debug(f"Using default Codex directory: {self._codex_dir}")

# New property:
@property
def codex_data_dir(self) -> Path:
    """Get the Codex data directory path.

    Returns:
        Path to Codex data directory (~/.codex by default).
    """
    return self._codex_dir

# New method:
def validate_codex_directory(self) -> bool:
    """Validate that the Codex data directory exists.

    Returns:
        True if directory exists and contains a sessions subdirectory.
    """
    if not self._codex_dir.exists():
        logger.warning(f"Codex data directory not found: {self._codex_dir}")
        return False
    if not self._codex_dir.is_dir():
        logger.warning(f"Codex data path is not a directory: {self._codex_dir}")
        return False
    sessions_dir = self._codex_dir / 'sessions'
    if not sessions_dir.exists():
        logger.warning(f"Codex sessions directory not found: {sessions_dir}")
        return False
    return True

# Update chat_source_filter property:
@property
def chat_source_filter(self) -> Optional[ChatSource]:
    source = os.getenv('CHAT_SOURCE', 'claude').lower()
    if source == 'claude':
        return ChatSource.CLAUDE_DESKTOP
    elif source == 'kiro':
        return ChatSource.KIRO_IDE
    elif source == 'codex':
        return ChatSource.CODEX
    elif source == 'all':
        return None
    else:
        logger.warning(f"Invalid CHAT_SOURCE: {source}, defaulting to 'claude'")
        return ChatSource.CLAUDE_DESKTOP
```

---

### Step 5: Update `src/projects.py`

**File:** `src/projects.py`
**Changes:** Add Codex scanning alongside Claude and Kiro in all functions.

#### In `list_all_projects()`:

```python
# Add at the top with other scan flags:
scan_codex = source_filter is None or source_filter == ChatSource.CODEX

# Add after the Kiro scanning block:
# Scan Codex CLI projects
if scan_codex:
    if config.validate_codex_directory():
        try:
            from .codex_projects import discover_codex_workspaces
            codex_workspaces = discover_codex_workspaces(config.codex_data_dir)

            for workspace in codex_workspaces:
                projects.append(ProjectInfo(
                    name=workspace.workspace_name,
                    path=config.codex_data_dir / 'sessions',  # Base sessions dir
                    file_count=workspace.session_count,
                    total_messages=0,  # Deferred: requires parsing all session files
                    last_modified=workspace.last_modified,
                    sort_timestamp=None,
                    source=ChatSource.CODEX,
                    workspace_path=workspace.workspace_path,
                    session_ids=[str(s.file_path) for s in workspace.sessions]
                ))
            logger.info(
                f"Found {len([p for p in projects if p.source == ChatSource.CODEX])} "
                f"Codex CLI projects"
            )
        except Exception as e:
            logger.warning(f"Error discovering Codex projects: {e}")
    else:
        logger.debug("Codex data directory not found, skipping Codex projects")
```

**Key design decision:** For Codex, `ProjectInfo.path` is set to the sessions root dir, and the actual file paths are stored in `session_ids` as string paths. This avoids needing a dedicated directory per project.

#### In `find_project_by_name()`:

```python
# Add after Kiro search block:
search_codex = source_filter is None or source_filter == ChatSource.CODEX

if search_codex:
    if config.validate_codex_directory():
        try:
            from .codex_projects import discover_codex_workspaces
            codex_workspaces = discover_codex_workspaces(config.codex_data_dir)

            for workspace in codex_workspaces:
                # Match against workspace name (directory basename)
                if workspace.workspace_name.lower() == project_name.lower():
                    return ProjectInfo(
                        name=workspace.workspace_name,
                        path=config.codex_data_dir / 'sessions',
                        file_count=workspace.session_count,
                        total_messages=0,
                        last_modified=workspace.last_modified,
                        source=ChatSource.CODEX,
                        workspace_path=workspace.workspace_path,
                        session_ids=[str(s.file_path) for s in workspace.sessions]
                    )

                # Also match against full path basename
                workspace_basename = Path(workspace.workspace_path).name
                if workspace_basename.lower() == project_name.lower():
                    return ProjectInfo(
                        name=workspace.workspace_name,
                        path=config.codex_data_dir / 'sessions',
                        file_count=workspace.session_count,
                        total_messages=0,
                        last_modified=workspace.last_modified,
                        source=ChatSource.CODEX,
                        workspace_path=workspace.workspace_path,
                        session_ids=[str(s.file_path) for s in workspace.sessions]
                    )
        except Exception as e:
            logger.warning(f"Error searching Codex projects: {e}")
```

#### In `get_project_chat_files()`:

```python
def get_project_chat_files(
    project_path: Path,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP,
    session_ids: Optional[List[str]] = None
) -> List[Path]:
    """Get all chat files in a project based on source type.

    Args:
        project_path: Path to the project directory.
        source: Chat source type.
        session_ids: For Codex: list of absolute file path strings.
    """
    if source == ChatSource.CODEX:
        # Codex sessions are stored as absolute paths in session_ids
        if session_ids:
            chat_files = [Path(p) for p in session_ids if Path(p).exists()]
            chat_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return chat_files
        return []
    elif source == ChatSource.KIRO_IDE:
        chat_files = list(project_path.glob('*.json'))
        chat_files = [f for f in chat_files if f.name != 'sessions.json']
    else:
        chat_files = list(project_path.glob('*.jsonl'))

    chat_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return chat_files
```

**Note:** The signature of `get_project_chat_files()` adds an optional `session_ids` parameter. All existing callers pass only `project_path` and `source`, so this is backward-compatible.

---

### Step 6: Update `src/exporters.py`

**File:** `src/exporters.py`

#### 6a. Update imports:

```python
from .codex_parser import (
    parse_codex_rollout_file,
    extract_codex_messages,
    normalize_codex_content
)
```

#### 6b. Update `_detect_chat_source()`:

```python
def _detect_chat_source(file_path: Path) -> ChatSource:
    """Detect whether a chat file is from Claude Desktop, Kiro IDE, or Codex CLI."""
    import json

    # First check: file extension
    if file_path.suffix == '.jsonl':
        # Could be Claude Desktop or Codex — check content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line:
                    data = json.loads(first_line)
                    # Codex rollout files start with session_meta
                    if isinstance(data, dict) and data.get('type') == 'session_meta':
                        return ChatSource.CODEX
        except (json.JSONDecodeError, IOError):
            pass
        # Default for .jsonl: Claude Desktop
        return ChatSource.CLAUDE_DESKTOP

    # ... rest of existing function for .chat/.json files ...
```

#### 6c. Add `_convert_codex_to_dict()`:

```python
def _convert_codex_to_dict(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Convert Codex ChatMessage objects to dict format for compatibility.

    Args:
        messages: List of ChatMessage objects from Codex parser

    Returns:
        List of message dicts compatible with export functions
    """
    chat_data = []
    for msg in messages:
        entry = {
            'message': {
                'role': msg.role,
                'content': msg.content
            },
            'timestamp': msg.timestamp,
            'source': ChatSource.CODEX
        }
        if msg.execution_id:
            entry['execution_id'] = msg.execution_id
        chat_data.append(entry)
    return chat_data
```

#### 6d. Update `_load_chat_data()`:

Add Codex branch in the source detection:

```python
if source == ChatSource.CODEX:
    # Parse Codex rollout file
    from .codex_parser import parse_codex_rollout_file, extract_codex_messages

    session = parse_codex_rollout_file(file_path)
    messages = extract_codex_messages(session)

    chat_data = _convert_codex_to_dict(messages)
    return chat_data, ChatSource.CODEX, errors

elif source == ChatSource.KIRO_IDE:
    # ... existing Kiro code ...
else:
    # ... existing Claude code ...
```

#### 6e. Update `export_project_chats()`:

Add Codex file handling:

```python
# Get chat files based on source type
if source == ChatSource.CODEX:
    # Codex: files are passed via session_ids, not globbed from a directory
    # The caller should provide the files list
    chat_files = list(project_path.glob('rollout-*.jsonl'))
    if not chat_files:
        # Try recursive glob for date-organized structure
        chat_files = list(project_path.rglob('rollout-*.jsonl'))
elif source == ChatSource.KIRO_IDE:
    chat_files = [f for f in project_path.glob('*.json') if f.name != 'sessions.json']
else:
    chat_files = list(project_path.glob('*.jsonl'))
```

---

### Step 7: Update `claude-chat-manager.py`

**File:** `claude-chat-manager.py`

#### 7a. Update argparse choices:

```python
parser.add_argument('--source', choices=['claude', 'kiro', 'codex', 'all'],
                    default='claude', help='Chat source to use: claude (default), kiro, codex, or all')
```

#### 7b. Update source_filter mapping:

```python
# Convert source argument to ChatSource enum
source_filter = None
if args.source == 'claude':
    source_filter = ChatSource.CLAUDE_DESKTOP
elif args.source == 'kiro':
    source_filter = ChatSource.KIRO_IDE
elif args.source == 'codex':
    source_filter = ChatSource.CODEX
elif args.source == 'all':
    source_filter = None  # None means all sources
```

#### 7c. Update usage examples in epilog:

```python
%(prog)s --source codex                          # List Codex CLI projects
%(prog)s --source codex "my-project"             # Browse Codex project
%(prog)s --source all                            # List all sources (Claude + Kiro + Codex)
```

---

### Step 8: Update `.env.example`

**File:** `.env.example`

Add after the Kiro IDE Settings section:

```
# ============================================================================
# Codex CLI Settings
# ============================================================================

# Codex data directory (default: ~/.codex)
# Can also be set via CODEX_HOME environment variable
# CODEX_DATA_DIR=/path/to/custom/codex/data

# Chat source filter (default: claude)
# Options: claude (Claude Desktop only), kiro (Kiro IDE only), codex (Codex CLI only), all (all sources)
# CHAT_SOURCE=claude
```

---

### Step 9: Create `tests/test_codex_parser.py`

**Pattern follows:** `tests/test_kiro_parser.py`

```python
"""Tests for codex_parser module."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.codex_parser import (
    CodexSession,
    parse_codex_session_meta,
    parse_codex_rollout_file,
    extract_codex_messages,
    normalize_codex_content
)
from src.exceptions import ChatFileNotFoundError, InvalidChatFileError
from src.models import ChatSource


# ============================================================================
# Test Fixtures
# ============================================================================

def _make_session_meta(
    session_id: str = "test-uuid",
    cwd: str = "/home/user/project",
    model: str = "gpt-5.3-codex",
    cli_version: str = "0.104.0",
    git_branch: str = "main"
) -> str:
    """Create a session_meta JSONL line."""
    return json.dumps({
        "timestamp": "2026-02-20T09:00:00.000Z",
        "type": "session_meta",
        "payload": {
            "id": session_id,
            "timestamp": "2026-02-20T09:00:00.000Z",
            "cwd": cwd,
            "originator": "codex_cli_rs",
            "cli_version": cli_version,
            "source": "cli",
            "model_provider": "openai",
            "git": {
                "branch": git_branch,
                "repository_url": "https://github.com/user/project.git"
            }
        }
    })


def _make_user_message(text: str, timestamp: str = "2026-02-20T09:01:00.000Z") -> str:
    """Create a user message JSONL line."""
    return json.dumps({
        "timestamp": timestamp,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}]
        }
    })


def _make_assistant_message(
    text: str,
    timestamp: str = "2026-02-20T09:01:30.000Z",
    phase: str = None
) -> str:
    """Create an assistant message JSONL line."""
    payload = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}]
    }
    if phase:
        payload["phase"] = phase
    return json.dumps({
        "timestamp": timestamp,
        "type": "response_item",
        "payload": payload
    })


def _make_developer_message(text: str = "system instructions") -> str:
    """Create a developer message JSONL line (should be filtered)."""
    return json.dumps({
        "timestamp": "2026-02-20T09:01:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": text}]
        }
    })


def _make_event_msg(event_type: str = "task_started") -> str:
    """Create an event_msg JSONL line (should be filtered)."""
    return json.dumps({
        "timestamp": "2026-02-20T09:01:00.000Z",
        "type": "event_msg",
        "payload": {"type": event_type, "turn_id": "test-turn"}
    })


def _make_reasoning() -> str:
    """Create a reasoning JSONL line (should be filtered)."""
    return json.dumps({
        "timestamp": "2026-02-20T09:01:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "thinking..."}],
            "encrypted_content": "gAAAA..."
        }
    })


def _make_function_call(name: str = "exec_command") -> str:
    """Create a function_call JSONL line (should be filtered)."""
    return json.dumps({
        "timestamp": "2026-02-20T09:01:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": name,
            "arguments": '{"cmd":"ls"}',
            "call_id": "call_test"
        }
    })


def _write_rollout_file(tmpdir: Path, lines: list, filename: str = "rollout-test.jsonl") -> Path:
    """Write a rollout JSONL file and return its path."""
    file_path = tmpdir / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
    return file_path


# ============================================================================
# Tests for normalize_codex_content
# ============================================================================

class TestNormalizeCodexContent:
    """Tests for normalize_codex_content function."""

    def test_normalize_string_content(self):
        """String content returns as-is."""
        assert normalize_codex_content("hello") == "hello"

    def test_normalize_empty_string(self):
        assert normalize_codex_content("") == ""

    def test_normalize_input_text_blocks(self):
        """User message content blocks."""
        content = [{"type": "input_text", "text": "Hello world"}]
        assert normalize_codex_content(content) == "Hello world"

    def test_normalize_output_text_blocks(self):
        """Assistant message content blocks."""
        content = [{"type": "output_text", "text": "Here is the answer"}]
        assert normalize_codex_content(content) == "Here is the answer"

    def test_normalize_multiple_blocks(self):
        """Multiple content blocks joined with newlines."""
        content = [
            {"type": "output_text", "text": "Part 1"},
            {"type": "output_text", "text": "Part 2"}
        ]
        assert normalize_codex_content(content) == "Part 1\nPart 2"

    def test_normalize_empty_list(self):
        assert normalize_codex_content([]) == ""

    def test_normalize_none(self):
        assert normalize_codex_content(None) == ""

    def test_normalize_unknown_block_type(self):
        """Unknown block types are skipped."""
        content = [
            {"type": "input_text", "text": "valid"},
            {"type": "unknown_type", "data": "ignored"}
        ]
        assert normalize_codex_content(content) == "valid"


# ============================================================================
# Tests for parse_codex_session_meta
# ============================================================================

class TestParseCodexSessionMeta:
    """Tests for parse_codex_session_meta function."""

    def test_parse_valid_meta(self):
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(
                Path(tmpdir),
                [_make_session_meta(session_id="abc-123", cwd="/home/user/myproject")]
            )
            meta = parse_codex_session_meta(file_path)
            assert meta['id'] == "abc-123"
            assert meta['cwd'] == "/home/user/myproject"

    def test_parse_missing_file(self):
        with pytest.raises(ChatFileNotFoundError):
            parse_codex_session_meta(Path("/nonexistent/file.jsonl"))

    def test_parse_empty_file(self):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.jsonl"
            file_path.write_text("")
            with pytest.raises(InvalidChatFileError, match="Empty"):
                parse_codex_session_meta(file_path)

    def test_parse_non_session_meta_first_line(self):
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(
                Path(tmpdir),
                [_make_event_msg("task_started")]
            )
            with pytest.raises(InvalidChatFileError, match="not session_meta"):
                parse_codex_session_meta(file_path)


# ============================================================================
# Tests for parse_codex_rollout_file
# ============================================================================

class TestParseCodexRolloutFile:
    """Tests for parse_codex_rollout_file function."""

    def test_parse_basic_conversation(self):
        """Parse a simple user-assistant conversation."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(session_id="test-1", cwd="/home/user/project"),
                _make_user_message("Hello"),
                _make_assistant_message("Hi there!"),
            ])
            session = parse_codex_rollout_file(file_path)

            assert session.session_id == "test-1"
            assert session.cwd == "/home/user/project"
            assert len(session.messages) == 2
            assert session.messages[0]['role'] == 'user'
            assert session.messages[1]['role'] == 'assistant'

    def test_filters_developer_messages(self):
        """Developer messages should be filtered out."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_developer_message("system instructions"),
                _make_user_message("Hello"),
                _make_developer_message("more system stuff"),
                _make_assistant_message("Hi!"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 2  # Only user + assistant

    def test_filters_reasoning(self):
        """Reasoning items should be filtered out."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_user_message("Hello"),
                _make_reasoning(),
                _make_assistant_message("Hi!"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 2

    def test_filters_function_calls(self):
        """Function calls should be filtered out."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_user_message("List files"),
                _make_function_call("exec_command"),
                _make_assistant_message("Here are the files"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 2

    def test_filters_event_messages(self):
        """Event messages should be filtered out."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_event_msg("task_started"),
                _make_user_message("Hello"),
                _make_event_msg("token_count"),
                _make_assistant_message("Hi!"),
                _make_event_msg("task_complete"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 2

    def test_extracts_git_info(self):
        """Git branch and repo URL should be extracted."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(git_branch="feat/new-feature"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert session.git_branch == "feat/new-feature"

    def test_missing_file_raises(self):
        with pytest.raises(ChatFileNotFoundError):
            parse_codex_rollout_file(Path("/nonexistent.jsonl"))

    def test_no_session_meta_raises(self):
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_user_message("Hello"),
            ])
            with pytest.raises(InvalidChatFileError, match="No session_meta"):
                parse_codex_rollout_file(file_path)

    def test_preserves_timestamps(self):
        """Timestamps from JSONL lines should be preserved."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_user_message("Hello", timestamp="2026-02-20T10:00:00.000Z"),
                _make_assistant_message("Hi!", timestamp="2026-02-20T10:00:30.000Z"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert session.messages[0]['timestamp'] == "2026-02-20T10:00:00.000Z"
            assert session.messages[1]['timestamp'] == "2026-02-20T10:00:30.000Z"


# ============================================================================
# Tests for extract_codex_messages
# ============================================================================

class TestExtractCodexMessages:
    """Tests for extract_codex_messages function."""

    def test_extract_basic_messages(self):
        """Extract ChatMessage objects from session."""
        session = CodexSession(
            session_id="test-1",
            cwd="/project",
            model="gpt-5.3-codex",
            timestamp="2026-02-20T09:00:00.000Z",
            cli_version="0.104.0",
            messages=[
                {
                    'role': 'user',
                    'content': [{"type": "input_text", "text": "Hello"}],
                    'timestamp': "2026-02-20T09:01:00.000Z",
                    'phase': None
                },
                {
                    'role': 'assistant',
                    'content': [{"type": "output_text", "text": "Hi there!"}],
                    'timestamp': "2026-02-20T09:01:30.000Z",
                    'phase': None
                }
            ]
        )
        messages = extract_codex_messages(session)

        assert len(messages) == 2
        assert messages[0].role == 'user'
        assert messages[0].content == 'Hello'
        assert messages[0].source == ChatSource.CODEX
        assert messages[0].timestamp == "2026-02-20T09:01:00.000Z"

        assert messages[1].role == 'assistant'
        assert messages[1].content == 'Hi there!'
        assert messages[1].source == ChatSource.CODEX

    def test_skips_empty_messages(self):
        """Messages with empty content should be skipped."""
        session = CodexSession(
            session_id="test-1",
            cwd="/project",
            model="gpt-5.3-codex",
            timestamp="2026-02-20T09:00:00.000Z",
            cli_version="0.104.0",
            messages=[
                {'role': 'user', 'content': [{"type": "input_text", "text": "Hello"}],
                 'timestamp': None, 'phase': None},
                {'role': 'assistant', 'content': [], 'timestamp': None, 'phase': None},
                {'role': 'assistant', 'content': [{"type": "output_text", "text": "Response"}],
                 'timestamp': None, 'phase': None},
            ]
        )
        messages = extract_codex_messages(session)
        assert len(messages) == 2  # Empty assistant message skipped

    def test_sets_execution_id_to_session_id(self):
        """execution_id should be set to session_id."""
        session = CodexSession(
            session_id="my-session-uuid",
            cwd="/project",
            model="gpt-5.3-codex",
            timestamp="2026-02-20T09:00:00.000Z",
            cli_version="0.104.0",
            messages=[
                {'role': 'user', 'content': [{"type": "input_text", "text": "Test"}],
                 'timestamp': None, 'phase': None},
            ]
        )
        messages = extract_codex_messages(session)
        assert messages[0].execution_id == "my-session-uuid"
```

---

### Step 10: Create `tests/test_codex_projects.py`

**Pattern follows:** `tests/test_kiro_projects.py`

```python
"""Tests for codex_projects module."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.codex_projects import (
    CodexSessionInfo,
    CodexWorkspace,
    discover_codex_workspaces,
    get_codex_session_files
)


def _create_rollout_file(
    base_dir: Path,
    date_path: str,
    filename: str,
    cwd: str,
    session_id: str = "test-uuid",
    timestamp: str = "2026-02-20T09:00:00.000Z"
) -> Path:
    """Create a minimal rollout file with session_meta."""
    dir_path = base_dir / 'sessions' / date_path
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / filename
    session_meta = json.dumps({
        "timestamp": timestamp,
        "type": "session_meta",
        "payload": {
            "id": session_id,
            "timestamp": timestamp,
            "cwd": cwd,
            "cli_version": "0.104.0",
            "model_provider": "openai",
            "git": {"branch": "main"}
        }
    })
    file_path.write_text(session_meta + '\n')
    return file_path


class TestDiscoverCodexWorkspaces:
    """Tests for discover_codex_workspaces function."""

    def test_discover_single_project(self):
        """Single cwd should produce single workspace."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1
            assert workspaces[0].workspace_name == "project-a"
            assert workspaces[0].workspace_path == "/home/user/project-a"
            assert workspaces[0].session_count == 1

    def test_discover_multiple_projects(self):
        """Sessions with different cwds should produce separate workspaces."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T10-00-00-uuid2.jsonl",
                cwd="/home/user/project-b",
                session_id="uuid2"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 2
            names = {w.workspace_name for w in workspaces}
            assert "project-a" in names
            assert "project-b" in names

    def test_group_sessions_by_cwd(self):
        """Multiple sessions with same cwd should be grouped."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/19",
                "rollout-2026-02-19T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1",
                timestamp="2026-02-19T09:00:00.000Z"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid2.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid2",
                timestamp="2026-02-20T09:00:00.000Z"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1
            assert workspaces[0].session_count == 2

    def test_empty_sessions_dir(self):
        """Empty sessions directory returns empty list."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            (codex_dir / 'sessions').mkdir()

            workspaces = discover_codex_workspaces(codex_dir)
            assert workspaces == []

    def test_missing_sessions_dir(self):
        """Missing sessions directory returns empty list."""
        with TemporaryDirectory() as tmpdir:
            workspaces = discover_codex_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_invalid_rollout_file_skipped(self):
        """Files with invalid JSON should be skipped gracefully."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            sessions_dir = codex_dir / 'sessions' / '2026' / '02' / '20'
            sessions_dir.mkdir(parents=True)

            # Invalid JSON file
            invalid_file = sessions_dir / 'rollout-invalid.jsonl'
            invalid_file.write_text('not valid json\n')

            # Valid file
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project",
                session_id="uuid1"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1  # Only valid file processed


class TestGetCodexSessionFiles:
    """Tests for get_codex_session_files function."""

    def test_returns_existing_files(self):
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            file1 = _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-1.jsonl", cwd="/project"
            )
            file2 = _create_rollout_file(
                codex_dir, "2026/02/19",
                "rollout-2.jsonl", cwd="/project"
            )

            workspace = CodexWorkspace(
                workspace_path="/project",
                workspace_name="project",
                sessions=[
                    CodexSessionInfo(
                        session_id="1", file_path=file1,
                        cwd="/project", timestamp=""
                    ),
                    CodexSessionInfo(
                        session_id="2", file_path=file2,
                        cwd="/project", timestamp=""
                    ),
                ],
                session_count=2
            )

            files = get_codex_session_files(workspace)
            assert len(files) == 2

    def test_filters_missing_files(self):
        workspace = CodexWorkspace(
            workspace_path="/project",
            workspace_name="project",
            sessions=[
                CodexSessionInfo(
                    session_id="1",
                    file_path=Path("/nonexistent/file.jsonl"),
                    cwd="/project", timestamp=""
                ),
            ],
            session_count=1
        )

        files = get_codex_session_files(workspace)
        assert len(files) == 0
```

---

### Step 11: Update `tests/test_cli_source_flag.py`

Add Codex-specific tests following the existing Claude and Kiro patterns:

```python
def test_list_all_projects_codex_only(self):
    """Test --source codex lists only Codex CLI projects."""
    with patch('src.projects.config') as mock_config:
        mock_config.claude_projects_dir = Path('/mock/claude')
        mock_config.kiro_data_dir = Path('/mock/kiro')
        mock_config.codex_data_dir = Path('/mock/codex')
        mock_config.validate_kiro_directory.return_value = False
        mock_config.validate_codex_directory.return_value = True

        mock_workspace = Mock()
        mock_workspace.workspace_name = 'codex-project'
        mock_workspace.workspace_path = '/path/to/project'
        mock_workspace.session_count = 3
        mock_workspace.last_modified = '2026-02-20 10:00'
        mock_workspace.sessions = [Mock(session_id='s1', file_path=Path('/mock/s1.jsonl'))]

        with patch('src.codex_projects.discover_codex_workspaces', return_value=[mock_workspace]), \
             patch('pathlib.Path.exists', return_value=False):

            projects = list_all_projects(ChatSource.CODEX)
            assert len(projects) > 0
            assert all(p.source == ChatSource.CODEX for p in projects)
```

---

## 7. Key Design Decisions

### 7.1 Project Grouping by `cwd`

Unlike Claude (projects = directories) and Kiro (projects = workspace-sessions), Codex stores sessions by date. Sessions are grouped into "projects" by their `cwd` field from `session_meta`. This is the most natural grouping since `cwd` represents which codebase was being worked on.

### 7.2 File Path Storage via `session_ids`

Since Codex sessions are scattered across date directories, the existing `ProjectInfo.session_ids` field is reused to store absolute file paths as strings. The `get_project_chat_files()` function resolves these to `Path` objects for Codex sources.

### 7.3 No Execution Log Enrichment

Unlike Kiro (which stores brief responses in session files and full responses in execution logs), Codex rollout files contain the complete conversation. No enrichment step is needed.

### 7.4 Source Detection for .jsonl Files

Both Claude Desktop and Codex use `.jsonl` files. Detection is based on the first line content:
- If first line has `"type": "session_meta"` → Codex
- Otherwise → Claude Desktop

### 7.5 Timestamp Availability

Codex provides per-line timestamps (ISO-8601 format), unlike Kiro which has no per-message timestamps. These are carried through to exports.

---

## 8. Files Changed Summary

| File | Action | Description |
|------|--------|-------------|
| `src/models.py` | Modify | Add `CODEX = "codex"` to ChatSource enum |
| `src/codex_parser.py` | **Create** | Codex rollout JSONL parser |
| `src/codex_projects.py` | **Create** | Codex project discovery (group by cwd) |
| `src/config.py` | Modify | Add Codex directory config, validate, source filter |
| `src/projects.py` | Modify | Integrate Codex into unified project listing/search |
| `src/exporters.py` | Modify | Add Codex detection, loading, dict conversion |
| `claude-chat-manager.py` | Modify | Add `--source codex` CLI flag |
| `.env.example` | Modify | Document Codex settings |
| `tests/test_codex_parser.py` | **Create** | Parser unit tests |
| `tests/test_codex_projects.py` | **Create** | Project discovery unit tests |
| `tests/test_cli_source_flag.py` | Modify | Add Codex source filtering test |
| `docs/ARCHITECTURE.md` | Modify | Add Codex data layer section |

---

## 9. Verification Checklist

1. `pytest tests/test_codex_parser.py -v` — all parser tests pass
2. `pytest tests/test_codex_projects.py -v` — all project tests pass
3. `pytest tests/test_cli_source_flag.py -v` — source filtering tests pass (including new Codex test)
4. `pytest tests/ -v` — all existing tests still pass (no regressions)
5. `python claude-chat-manager.py --source codex -l` — lists Codex projects grouped by cwd
6. `python claude-chat-manager.py --source codex "<project-name>"` — browses sessions
7. `python claude-chat-manager.py --source codex "<project-name>" -f book -e /tmp/codex-test/` — exports to book format
8. `python claude-chat-manager.py --source all -l` — shows Claude + Kiro + Codex projects
9. Source indicators display correctly: `[Claude]`, `[Kiro]`, `[Codex]`

---

## 10. Real Codex Files Reference

Located at: `~/.codex/sessions/`

**Available test files:**
- `~/.codex/sessions/2026/02/19/rollout-2026-02-19T11-30-37-019c7573-9f8f-7302-95f9-721d91bd6275.jsonl` (16 lines, minimal session)
- `~/.codex/sessions/2026/02/20/rollout-2026-02-20T10-00-26-019c7a47-6a4c-78d2-9fb1-27fda2245dd9.jsonl` (1679 lines, full session with cwd `/Users/eobomik/src/eodhd_realtime_candles`)

**`history.jsonl`** — 44 lines of user input history (not used for conversation export).

---

## 11. Event Type Frequency (from real 1679-line session)

```
 363  event_msg:token_count
 181  turn_context
 178  response_item:function_call
 178  response_item:function_call_output
 133  response_item:reasoning
 133  event_msg:agent_message
 133  response_item:message/assistant
 127  event_msg:agent_reasoning
  47  response_item:message/user
  43  event_msg:task_started
  43  event_msg:user_message
  43  event_msg:task_complete
  36  response_item:custom_tool_call
  36  response_item:custom_tool_call_output
   2  response_item:message/developer
   1  session_meta
   1  compacted
   1  event_msg:context_compacted
```

Only `response_item:message/user` (47) and `response_item:message/assistant` (133) are included in exports. Everything else is filtered.

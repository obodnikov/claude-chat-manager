"""Integration tests for the full Cline VS Code export pipeline (Phase E2E).

These are cross-module tests that exercise the complete chain:
  discover → projects → load_chat_data → export_project_chats / export_chat_*

Each test builds a realistic temporary globalStorage fixture and asserts
clean end-to-end behavior without mocking any internal layer.
"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
from unittest.mock import patch, MagicMock

import pytest

from src.exporters import export_project_chats, _detect_chat_source, _load_chat_data
from src.models import ChatSource, ProjectInfo
from src.projects import list_all_projects, find_project_by_name, get_project_chat_files


# ============================================================================
# Shared fixture helpers
# ============================================================================

def _ui_messages(user_text: str, assistant_text: str, ts_base: int = 1_700_000_000_000) -> list:
    """Minimal ui_messages.json payload with one user + one assistant + follow-up turn."""
    return [
        {"ts": ts_base,        "type": "say", "say": "task",            "text": user_text},
        {"ts": ts_base + 1000, "type": "say", "say": "text",            "text": assistant_text},
        {"ts": ts_base + 2000, "type": "say", "say": "user_feedback",   "text": "Thanks, that helps!"},
        {"ts": ts_base + 3000, "type": "say", "say": "api_req_started", "text": ""},  # noise
        {"ts": ts_base + 4000, "type": "say", "say": "tool",            "text": ""},  # noise
    ]


def _api_history(user_text: str, assistant_text: str) -> list:
    """Minimal api_conversation_history.json payload."""
    return [
        {"role": "user", "content": [
            {"type": "text", "text": f"<task>{user_text}</task>"},
            {"type": "tool_result", "content": []},        # should be skipped
        ]},
        {"role": "assistant", "content": [
            {"type": "text",      "text": assistant_text},
            {"type": "tool_use",  "name": "write_file"},  # should be skipped
        ]},
    ]


def _build_globalStorage(
    base: Path,
    tasks: List[dict],
    include_ui: bool = True,
    include_api: bool = False,
) -> Path:
    """Build a minimal globalStorage structure under `base`.

    Args:
        base: Root directory (used as cline_vscode_data_dir).
        tasks: List of dicts with keys: task_id, cwd, ts, user, assistant.
        include_ui: Write ui_messages.json for each task.
        include_api: Write api_conversation_history.json for each task.

    Returns:
        Path to the cline_vscode_data_dir (same as base).
    """
    state_dir = base / "state"
    state_dir.mkdir(parents=True)
    tasks_dir = base / "tasks"
    tasks_dir.mkdir(parents=True)

    history_entries = []
    for t in tasks:
        task_dir = tasks_dir / t["task_id"]
        task_dir.mkdir(parents=True, exist_ok=True)

        if include_ui:
            (task_dir / "ui_messages.json").write_text(
                json.dumps(_ui_messages(t["user"], t["assistant"], t["ts"])),
                encoding="utf-8",
            )

        if include_api:
            (task_dir / "api_conversation_history.json").write_text(
                json.dumps(_api_history(t["user"], t["assistant"])),
                encoding="utf-8",
            )

        history_entries.append({
            "id": t["task_id"],
            "ts": t["ts"],
            "task": t["user"],
            "cwdOnTaskInitialization": t["cwd"],
            "modelId": "claude-opus-4.6",
            "totalCost": 0.01,
        })

    (state_dir / "taskHistory.json").write_text(
        json.dumps(history_entries), encoding="utf-8"
    )
    return base


def _cfg_mock(cline_dir: Path) -> MagicMock:
    """Config mock that enables only Cline VS Code, disables everything else."""
    m = MagicMock()
    m.cline_vscode_data_dir = cline_dir
    m.validate_cline_vscode_directory.return_value = True
    m.validate_kiro_directory.return_value = False
    m.validate_codex_directory.return_value = False
    empty = cline_dir / "_no_claude"
    empty.mkdir(exist_ok=True)
    m.claude_projects_dir = empty
    return m


# ============================================================================
# E2E — Full export pipeline (ui_messages.json primary)
# ============================================================================

class TestClineExportPipelineUiMessages:
    """Full export pipeline driven by ui_messages.json (primary source)."""

    _TASKS = [
        {"task_id": "1000", "cwd": "/home/user/proj-a", "ts": 1_700_000_000_000,
         "user": "How do I sort a list in Python?",
         "assistant": "Use the sorted() function or list.sort() method."},
        {"task_id": "2000", "cwd": "/home/user/proj-a", "ts": 1_700_100_000_000,
         "user": "What is a decorator?",
         "assistant": "A decorator wraps a function to add behaviour."},
    ]

    def test_markdown_export_contains_conversation(self):
        """Exported markdown contains the actual user + assistant text."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), self._TASKS)
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 2
            for path in exported:
                content = path.read_text(encoding="utf-8")
                assert "# Claude Chat Export" in content

    def test_no_tool_noise_in_markdown(self):
        """api_req_started and tool entries do not appear in the export."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), self._TASKS[:1])
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            content = exported[0].read_text(encoding="utf-8")
            # The noise subtypes (api_req_started, tool) should not appear
            assert "api_req_started" not in content
            assert '"tool"' not in content

    def test_book_format_exports(self):
        """book format works end-to-end for Cline tasks with enough content."""
        # Use varied, realistic content that passes all book trivial-chat filters:
        # min 3 messages, min 75 words, no warmup keywords
        user_text = (
            "Can you explain how Python's async/await model works compared to "
            "traditional threading? I want to understand the event loop and "
            "when to use each approach in production code."
        )
        assistant_text = (
            "Python's async/await uses a single-threaded event loop that "
            "multiplexes I/O-bound coroutines without the overhead of OS threads. "
            "You should use asyncio for I/O-bound work (network calls, file I/O) "
            "and threading or multiprocessing for CPU-bound tasks. The event loop "
            "runs coroutines cooperatively — a coroutine yields control at every "
            "await point, letting other coroutines run. This is more efficient than "
            "threads for high-concurrency I/O but requires an async-first codebase."
        )
        tasks = [
            {"task_id": "3000", "cwd": "/home/user/proj", "ts": 1_700_000_000_000,
             "user": user_text, "assistant": assistant_text},
            {"task_id": "3001", "cwd": "/home/user/proj", "ts": 1_700_000_001_000,
             "user": "Follow-up: how does asyncio.gather work?",
             "assistant": "asyncio.gather runs multiple coroutines concurrently and returns their results as a list once all complete."},
            {"task_id": "3002", "cwd": "/home/user/proj", "ts": 1_700_000_002_000,
             "user": "What about error handling inside gather?",
             "assistant": "By default gather raises the first exception. Pass return_exceptions=True to collect exceptions as values instead."},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="book",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) >= 1
            for path in exported:
                content = path.read_text(encoding="utf-8")
                assert "USER" in content or "asyncio" in content

    def test_user_content_appears_in_export(self):
        """The user's message text is present in the exported file."""
        tasks = [
            {"task_id": "4000", "cwd": "/home/user/proj", "ts": 1_700_000_000_000,
             "user": "unique-sentinel-user-message-xyz",
             "assistant": "unique-sentinel-assistant-reply-abc"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            content = exported[0].read_text(encoding="utf-8")
            assert "unique-sentinel-user-message-xyz" in content
            assert "unique-sentinel-assistant-reply-abc" in content


# ============================================================================
# E2E — API history fallback
# ============================================================================

class TestClineExportApiFallback:
    """When ui_messages.json is absent, the API history fallback is used."""

    def test_api_fallback_exports_conversation(self):
        """Export succeeds using api_conversation_history.json when no ui_messages.json."""
        tasks = [
            {"task_id": "5000", "cwd": "/home/user/proj", "ts": 1_700_000_000_000,
             "user": "fallback-user-content",
             "assistant": "fallback-assistant-content"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(
                Path(tmpdir), tasks, include_ui=False, include_api=True
            )
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            content = exported[0].read_text(encoding="utf-8")
            assert "fallback-user-content" in content
            assert "fallback-assistant-content" in content

    def test_api_fallback_strips_task_wrapper(self):
        """<task>...</task> wrapper in api_history user messages is unwrapped."""
        tasks = [
            {"task_id": "5001", "cwd": "/home/user/proj", "ts": 1_700_000_000_000,
             "user": "inner-user-text", "assistant": "answer"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(
                Path(tmpdir), tasks, include_ui=False, include_api=True
            )
            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            content = exported[0].read_text(encoding="utf-8")
            # The raw <task> tag must not appear; the inner text should
            assert "<task>" not in content
            assert "inner-user-text" in content

    def test_api_fallback_preferred_when_renamed_ui_messages(self):
        """Renaming ui_messages.json triggers api fallback."""
        tasks = [
            {"task_id": "5002", "cwd": "/home/user/proj", "ts": 1_700_000_000_000,
             "user": "renamed-ui-test", "assistant": "renamed-answer"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(
                Path(tmpdir), tasks, include_ui=True, include_api=True
            )
            # Rename ui_messages.json to simulate its absence
            task_dir = cline_dir / "tasks" / "5002"
            ui_path = task_dir / "ui_messages.json"
            ui_path.rename(task_dir / "ui_messages.json.bak")

            tasks_dir = cline_dir / "tasks"
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            content = exported[0].read_text(encoding="utf-8")
            assert "renamed-answer" in content


# ============================================================================
# E2E — projects.py ↔ exporters.py wiring
# ============================================================================

class TestClineProjectsToExportersWiring:
    """list_all_projects → get_project_chat_files → export_project_chats chain."""

    def test_session_ids_from_projects_feed_export(self):
        """session_ids returned by list_all_projects can be resolved and exported."""
        tasks = [
            {"task_id": "6000", "cwd": "/home/user/myproject", "ts": 1_700_000_000_000,
             "user": "wiring-test-user", "assistant": "wiring-test-assistant"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            cfg = _cfg_mock(cline_dir)

            with patch("src.projects.config", cfg):
                projects = list_all_projects(ChatSource.CLINE_VSCODE)

            assert len(projects) == 1
            project = projects[0]
            assert project.source == ChatSource.CLINE_VSCODE

            # Resolve session_ids → task dirs via get_project_chat_files
            task_dirs = get_project_chat_files(
                project.path, ChatSource.CLINE_VSCODE, project.session_ids
            )
            assert len(task_dirs) == 1

            # Export the resolved task dirs
            export_dir = Path(tmpdir) / "export"
            exported = export_project_chats(
                project.path, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            content = exported[0].read_text(encoding="utf-8")
            assert "wiring-test-user" in content

    def test_find_project_by_name_then_export(self):
        """find_project_by_name → export_project_chats end-to-end."""
        tasks = [
            {"task_id": "7000", "cwd": "/home/user/coolproject", "ts": 1_700_000_000_000,
             "user": "find-by-name-test", "assistant": "found-and-exported"},
        ]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            cfg = _cfg_mock(cline_dir)

            with patch("src.projects.config", cfg):
                project = find_project_by_name("coolproject", ChatSource.CLINE_VSCODE)

            assert project is not None
            assert project.name == "coolproject"
            assert project.source == ChatSource.CLINE_VSCODE

            export_dir = Path(tmpdir) / "export"
            exported = export_project_chats(
                project.path, export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            content = exported[0].read_text(encoding="utf-8")
            assert "find-by-name-test" in content


# ============================================================================
# E2E — _detect_chat_source + _load_chat_data individual routing
# ============================================================================

class TestClineDetectAndLoad:
    """_detect_chat_source and _load_chat_data route Cline paths correctly."""

    def test_detect_returns_cline_for_task_dir(self):
        """_detect_chat_source returns CLINE_VSCODE for a task directory."""
        tasks = [{"task_id": "8000", "cwd": "/proj", "ts": 1_700_000_000_000,
                  "user": "hi", "assistant": "hello"}]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            task_dir = cline_dir / "tasks" / "8000"
            assert _detect_chat_source(task_dir) == ChatSource.CLINE_VSCODE

    def test_detect_returns_cline_for_ui_messages_file(self):
        """_detect_chat_source returns CLINE_VSCODE for ui_messages.json."""
        tasks = [{"task_id": "8001", "cwd": "/proj", "ts": 1_700_000_000_000,
                  "user": "hi", "assistant": "hello"}]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            ui_file = cline_dir / "tasks" / "8001" / "ui_messages.json"
            assert _detect_chat_source(ui_file) == ChatSource.CLINE_VSCODE

    def test_load_chat_data_returns_cline_source(self):
        """_load_chat_data returns (data, CLINE_VSCODE, []) for a task dir."""
        tasks = [{"task_id": "8002", "cwd": "/proj", "ts": 1_700_000_000_000,
                  "user": "load-test", "assistant": "loaded"}]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            task_dir = cline_dir / "tasks" / "8002"

            chat_data, source, errors = _load_chat_data(task_dir)

        assert source == ChatSource.CLINE_VSCODE
        assert errors == []
        assert len(chat_data) >= 2
        roles = [e["message"]["role"] for e in chat_data]
        assert "user" in roles
        assert "assistant" in roles

    def test_load_chat_data_no_tool_noise(self):
        """_load_chat_data drops api_req_started and tool-type say entries."""
        tasks = [{"task_id": "8003", "cwd": "/proj", "ts": 1_700_000_000_000,
                  "user": "no-noise", "assistant": "clean"}]
        with TemporaryDirectory() as tmpdir:
            cline_dir = _build_globalStorage(Path(tmpdir), tasks)
            task_dir = cline_dir / "tasks" / "8003"

            chat_data, _, _ = _load_chat_data(task_dir)

        # Only user + assistant messages; tool noise is dropped by the parser
        for entry in chat_data:
            assert entry["message"]["role"] in ("user", "assistant")

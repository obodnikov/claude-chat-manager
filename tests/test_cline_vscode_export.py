"""Tests for Cline VS Code export wiring in exporters.py (Step 6).

Covers:
- _detect_chat_source() for Cline task directories and conversation files
- _convert_cline_vscode_to_dict() output shape
- _load_chat_data() routing through parse_cline_vscode_task
- export_project_chats() with source=ChatSource.CLINE_VSCODE
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.exporters import (
    _convert_cline_vscode_to_dict,
    _detect_chat_source,
    _load_chat_data,
    export_project_chats,
)
from src.models import ChatMessage, ChatSource


# ============================================================================
# Test fixture helpers
# ============================================================================

def _make_ui_messages(entries: list = None) -> list:
    """Return a minimal ui_messages.json payload."""
    if entries is not None:
        return entries
    return [
        {"ts": 1_700_000_000_000, "type": "say", "say": "task",
         "text": "Implement the feature"},
        {"ts": 1_700_000_001_000, "type": "say", "say": "text",
         "text": "Sure, I will implement that for you."},
        {"ts": 1_700_000_002_000, "type": "say", "say": "user_feedback",
         "text": "Thanks!"},
    ]


def _make_api_history(entries: list = None) -> list:
    """Return a minimal api_conversation_history.json payload."""
    if entries is not None:
        return entries
    return [
        {"role": "user",
         "content": [{"type": "text", "text": "Hello from API history"}]},
        {"role": "assistant",
         "content": [{"type": "text", "text": "Hello back"}]},
    ]


def _setup_task_dir(
    base_dir: Path,
    task_id: str = "1781697826685",
    ui_messages: list = None,
    api_history: list = None,
    include_ui: bool = True,
    include_api: bool = False,
) -> Path:
    """Create a fake Cline task directory under base_dir/tasks/<task_id>/.

    Args:
        base_dir: Root temp directory (the tasks/ parent).
        task_id: Task directory name.
        ui_messages: Content for ui_messages.json (uses default if None).
        api_history: Content for api_conversation_history.json.
        include_ui: Create ui_messages.json.
        include_api: Create api_conversation_history.json.

    Returns:
        Path to the task directory.
    """
    task_dir = base_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    if include_ui:
        payload = ui_messages if ui_messages is not None else _make_ui_messages()
        (task_dir / "ui_messages.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    if include_api:
        payload = api_history if api_history is not None else _make_api_history()
        (task_dir / "api_conversation_history.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    return task_dir


# ============================================================================
# _detect_chat_source — Cline VS Code
# ============================================================================

class TestDetectChatSourceClineVscode:
    """_detect_chat_source() recognises Cline VS Code paths."""

    def test_task_directory_with_ui_messages(self):
        """A directory containing ui_messages.json → CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir), include_ui=True)
            assert _detect_chat_source(task_dir) == ChatSource.CLINE_VSCODE

    def test_task_directory_with_only_api_history(self):
        """A directory with only api_conversation_history.json → CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(
                Path(tmpdir), include_ui=False, include_api=True
            )
            assert _detect_chat_source(task_dir) == ChatSource.CLINE_VSCODE

    def test_ui_messages_file_directly(self):
        """Passing ui_messages.json as the path → CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir), include_ui=True)
            assert _detect_chat_source(task_dir / "ui_messages.json") == ChatSource.CLINE_VSCODE

    def test_api_history_file_directly(self):
        """Passing api_conversation_history.json as the path → CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(
                Path(tmpdir), include_ui=False, include_api=True
            )
            assert (
                _detect_chat_source(task_dir / "api_conversation_history.json")
                == ChatSource.CLINE_VSCODE
            )

    def test_plain_directory_without_cline_files_is_not_cline(self):
        """A directory with no Cline files is not detected as CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            plain_dir = Path(tmpdir) / "plain"
            plain_dir.mkdir()
            (plain_dir / "other.json").write_text("{}", encoding="utf-8")
            # Falls through to KIRO or CLAUDE detection — not CLINE_VSCODE
            result = _detect_chat_source(plain_dir)
            assert result != ChatSource.CLINE_VSCODE

    def test_jsonl_file_not_detected_as_cline(self):
        """A plain .jsonl file is still detected as Claude Desktop or Codex."""
        with TemporaryDirectory() as tmpdir:
            jsonl_file = Path(tmpdir) / "chat.jsonl"
            jsonl_file.write_text(
                json.dumps({"type": "human", "text": "hello"}) + "\n",
                encoding="utf-8",
            )
            result = _detect_chat_source(jsonl_file)
            assert result == ChatSource.CLAUDE_DESKTOP

    def test_kiro_json_file_not_detected_as_cline(self):
        """A Kiro .json session file is not detected as CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            kiro_file = Path(tmpdir) / "session.json"
            kiro_file.write_text(
                json.dumps({"chat": [], "executionId": "exec-1"}),
                encoding="utf-8",
            )
            result = _detect_chat_source(kiro_file)
            assert result == ChatSource.KIRO_IDE


# ============================================================================
# _convert_cline_vscode_to_dict
# ============================================================================

class TestConvertClineVscodeToDictt:
    """_convert_cline_vscode_to_dict() produces export-compatible dicts."""

    def _make_messages(self) -> list:
        return [
            ChatMessage(
                role="user",
                content="Hello from user",
                timestamp=1_700_000_000_000,
                source=ChatSource.CLINE_VSCODE,
                execution_id="task-abc",
            ),
            ChatMessage(
                role="assistant",
                content="Hello from assistant",
                timestamp=1_700_000_001_000,
                source=ChatSource.CLINE_VSCODE,
                execution_id="task-abc",
            ),
        ]

    def test_output_length_matches_input(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        assert len(result) == 2

    def test_message_role_preserved(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        assert result[0]["message"]["role"] == "user"
        assert result[1]["message"]["role"] == "assistant"

    def test_message_content_preserved(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        assert result[0]["message"]["content"] == "Hello from user"
        assert result[1]["message"]["content"] == "Hello from assistant"

    def test_timestamp_preserved(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        assert result[0]["timestamp"] == 1_700_000_000_000

    def test_source_set_to_cline_vscode(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        for entry in result:
            assert entry["source"] == ChatSource.CLINE_VSCODE

    def test_execution_id_included(self):
        result = _convert_cline_vscode_to_dict(self._make_messages())
        for entry in result:
            assert entry.get("execution_id") == "task-abc"

    def test_empty_input_returns_empty(self):
        assert _convert_cline_vscode_to_dict([]) == []


# ============================================================================
# _load_chat_data — Cline VS Code routing
# ============================================================================

class TestLoadChatDataClineVscode:
    """_load_chat_data() routes Cline task dirs through parse_cline_vscode_task."""

    def test_task_directory_returns_cline_source(self):
        """Passing a task directory returns ChatSource.CLINE_VSCODE."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir))
            chat_data, source, errors = _load_chat_data(task_dir)

        assert source == ChatSource.CLINE_VSCODE
        assert errors == []

    def test_messages_extracted_from_ui_messages(self):
        """Messages from ui_messages.json appear in the returned chat_data."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir))
            chat_data, source, errors = _load_chat_data(task_dir)

        assert len(chat_data) >= 2  # at least user + assistant
        roles = [e["message"]["role"] for e in chat_data]
        assert "user" in roles
        assert "assistant" in roles

    def test_chat_data_shape_is_export_compatible(self):
        """Each entry has the message/timestamp/source shape used by exporters."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir))
            chat_data, _, _ = _load_chat_data(task_dir)

        for entry in chat_data:
            assert "message" in entry
            assert "role" in entry["message"]
            assert "content" in entry["message"]
            assert "timestamp" in entry
            assert "source" in entry

    def test_ui_messages_file_path_resolves_to_task_dir(self):
        """Passing ui_messages.json directly also works via parent resolution."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(Path(tmpdir))
            ui_file = task_dir / "ui_messages.json"
            chat_data, source, errors = _load_chat_data(ui_file)

        assert source == ChatSource.CLINE_VSCODE
        assert len(chat_data) >= 1

    def test_fallback_to_api_history_when_no_ui_messages(self):
        """With no ui_messages.json, falls back to api_conversation_history.json."""
        with TemporaryDirectory() as tmpdir:
            task_dir = _setup_task_dir(
                Path(tmpdir), include_ui=False, include_api=True
            )
            chat_data, source, errors = _load_chat_data(task_dir)

        assert source == ChatSource.CLINE_VSCODE
        assert len(chat_data) >= 1

    def test_no_conversation_files_raises_export_error(self):
        """A task dir with no conversation files raises an error.

        An empty directory has no ui_messages.json or api_conversation_history.json,
        so _detect_chat_source() does not recognise it as CLINE_VSCODE and the
        Claude Desktop path raises an error instead. Either way the caller gets
        an exception — the important thing is it never silently returns data.
        """
        from src.exceptions import ExportError, InvalidJSONLError

        with TemporaryDirectory() as tmpdir:
            empty_task = Path(tmpdir) / "empty-task"
            empty_task.mkdir()
            with pytest.raises((ExportError, InvalidJSONLError)):
                _load_chat_data(empty_task)


# ============================================================================
# export_project_chats — Cline VS Code
# ============================================================================

class TestExportProjectChatsClineVscode:
    """export_project_chats() with source=ChatSource.CLINE_VSCODE."""

    def _setup_tasks_dir(self, base_dir: Path, count: int = 1) -> Path:
        """Create a tasks/ directory with `count` task subdirectories."""
        tasks_dir = base_dir / "tasks"
        tasks_dir.mkdir()
        for i in range(count):
            _setup_task_dir(tasks_dir, task_id=f"100{i}")
        return tasks_dir

    def test_exports_single_task(self):
        """A single task directory is exported to one markdown file."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = self._setup_tasks_dir(Path(tmpdir), count=1)
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            assert exported[0].suffix == ".md"
            assert exported[0].exists()

    def test_exports_multiple_tasks(self):
        """Multiple task directories each produce an exported file."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = self._setup_tasks_dir(Path(tmpdir), count=3)
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

        assert len(exported) == 3

    def test_exported_markdown_contains_conversation(self):
        """Exported markdown contains the conversation text."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            _setup_task_dir(
                tasks_dir,
                task_id="task-001",
                ui_messages=[
                    {"ts": 1_000_000_000_000, "type": "say", "say": "task",
                     "text": "unique-user-content-xyz"},
                    {"ts": 1_000_000_001_000, "type": "say", "say": "text",
                     "text": "unique-assistant-reply-abc"},
                ],
            )
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            content = exported[0].read_text(encoding="utf-8")

        assert "unique-user-content-xyz" in content
        assert "unique-assistant-reply-abc" in content

    def test_skips_non_task_files_in_tasks_dir(self):
        """Non-directory entries in tasks/ are ignored."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            # A stray file — should not be treated as a task
            (tasks_dir / "stray.json").write_text('{"junk": true}', encoding="utf-8")
            _setup_task_dir(tasks_dir, task_id="real-task")
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

        assert len(exported) == 1

    def test_skips_dirs_without_conversation_files(self):
        """Directories that lack ui_messages.json and api_history are skipped."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            # Empty task dir — no conversation files
            empty_dir = tasks_dir / "empty-task"
            empty_dir.mkdir()
            # Valid task dir
            _setup_task_dir(tasks_dir, task_id="valid-task")
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

        assert len(exported) == 1

    def test_empty_tasks_dir_returns_empty_list(self):
        """No tasks → empty exported list (no error)."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

        assert exported == []

    def test_api_history_fallback_is_exported(self):
        """Tasks with only api_conversation_history.json are still exported."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            _setup_task_dir(
                tasks_dir, task_id="api-only",
                include_ui=False, include_api=True
            )
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="markdown",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            assert exported[0].exists()

    def test_book_format_exports_successfully(self):
        """book format export works for Cline VS Code tasks."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            # Provide enough content to pass the book trivial-chat filter
            long_text = "word " * 30
            _setup_task_dir(
                tasks_dir,
                task_id="book-task",
                ui_messages=[
                    {"ts": 1_700_000_000_000, "type": "say", "say": "task",
                     "text": long_text},
                    {"ts": 1_700_000_001_000, "type": "say", "say": "text",
                     "text": long_text},
                    {"ts": 1_700_000_002_000, "type": "say", "say": "user_feedback",
                     "text": long_text},
                ],
            )
            export_dir = Path(tmpdir) / "export"

            exported = export_project_chats(
                tasks_dir,
                export_dir,
                format_type="book",
                source=ChatSource.CLINE_VSCODE,
            )

            assert len(exported) == 1
            assert exported[0].exists()

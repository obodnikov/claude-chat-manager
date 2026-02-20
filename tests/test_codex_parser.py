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


def _make_turn_context(model: str = "gpt-5.3-codex") -> str:
    """Create a turn_context JSONL line with model info."""
    return json.dumps({
        "timestamp": "2026-02-20T09:01:00.000Z",
        "type": "turn_context",
        "payload": {
            "model": model,
            "policies": {}
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

    def test_normalize_non_dict_blocks_skipped(self):
        """Non-dict items in content list are skipped."""
        content = [
            {"type": "input_text", "text": "valid"},
            "not a dict",
            42
        ]
        assert normalize_codex_content(content) == "valid"

    def test_normalize_empty_text_blocks_skipped(self):
        """Blocks with empty text are skipped."""
        content = [
            {"type": "input_text", "text": ""},
            {"type": "output_text", "text": "actual content"}
        ]
        assert normalize_codex_content(content) == "actual content"


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

    def test_parse_extracts_git_info(self):
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(
                Path(tmpdir),
                [_make_session_meta(git_branch="feat/test")]
            )
            meta = parse_codex_session_meta(file_path)
            assert meta['git']['branch'] == "feat/test"

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

    def test_parse_invalid_json(self):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "bad.jsonl"
            file_path.write_text("not valid json\n")
            with pytest.raises(InvalidChatFileError, match="Invalid JSON"):
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
            assert len(session.messages) == 2

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
            assert session.git_repo_url == "https://github.com/user/project.git"

    def test_extracts_model_from_turn_context(self):
        """Model should be extracted from turn_context if not in session_meta."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),  # No model in session_meta
                _make_turn_context(model="gpt-5.3-codex"),
                _make_user_message("Hello"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert session.model == "gpt-5.3-codex"

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

    def test_skips_invalid_json_lines(self):
        """Invalid JSON lines should be skipped gracefully."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "rollout-test.jsonl"
            with open(file_path, 'w') as f:
                f.write(_make_session_meta() + '\n')
                f.write('not valid json\n')
                f.write(_make_user_message("Hello") + '\n')
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 1

    def test_empty_session_no_messages(self):
        """Session with only meta and no messages."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
            ])
            session = parse_codex_rollout_file(file_path)
            assert len(session.messages) == 0

    def test_preserves_phase_field(self):
        """Phase field (commentary) should be preserved in messages."""
        with TemporaryDirectory() as tmpdir:
            file_path = _write_rollout_file(Path(tmpdir), [
                _make_session_meta(),
                _make_assistant_message("Thinking...", phase="commentary"),
                _make_assistant_message("Final answer"),
            ])
            session = parse_codex_rollout_file(file_path)
            assert session.messages[0]['phase'] == "commentary"
            assert session.messages[1]['phase'] is None


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
        assert len(messages) == 2

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

    def test_handles_string_content(self):
        """String content (not array) should be handled."""
        session = CodexSession(
            session_id="test-1",
            cwd="/project",
            model="gpt-5.3-codex",
            timestamp="2026-02-20T09:00:00.000Z",
            cli_version="0.104.0",
            messages=[
                {'role': 'user', 'content': "plain string message",
                 'timestamp': None, 'phase': None},
            ]
        )
        messages = extract_codex_messages(session)
        assert len(messages) == 1
        assert messages[0].content == "plain string message"

    def test_multiple_content_blocks_joined(self):
        """Multiple content blocks should be joined with newlines."""
        session = CodexSession(
            session_id="test-1",
            cwd="/project",
            model="gpt-5.3-codex",
            timestamp="2026-02-20T09:00:00.000Z",
            cli_version="0.104.0",
            messages=[
                {
                    'role': 'assistant',
                    'content': [
                        {"type": "output_text", "text": "First part"},
                        {"type": "output_text", "text": "Second part"}
                    ],
                    'timestamp': None,
                    'phase': None
                },
            ]
        )
        messages = extract_codex_messages(session)
        assert messages[0].content == "First part\nSecond part"

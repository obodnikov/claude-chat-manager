"""Tests for cline_vscode_parser module."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.cline_vscode_parser import (
    ClineVscodeSession,
    parse_cline_vscode_task,
    _parse_ui_messages,
    _parse_api_history,
    _strip_api_wrapper_noise,
    extract_cline_vscode_messages,
)
from src.cline_messages import decode_ask_text, normalize_cline_content
from src.exceptions import ChatFileNotFoundError, InvalidChatFileError
from src.models import ChatSource


# ============================================================================
# Test Fixtures / Helpers
# ============================================================================

def _make_ui_say(say_subtype: str, text: str, ts: int = 1781697826689) -> dict:
    """Create a say-type ui_messages entry."""
    return {"ts": ts, "type": "say", "say": say_subtype, "text": text}


def _make_ui_ask(ask_subtype: str, text: str, ts: int = 1781697826700) -> dict:
    """Create an ask-type ui_messages entry."""
    return {"ts": ts, "type": "ask", "ask": ask_subtype, "text": text}


def _write_ui_messages(task_dir: Path, entries: list) -> Path:
    """Write ui_messages.json in task_dir and return the file path."""
    ui_path = task_dir / "ui_messages.json"
    with open(ui_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f)
    return ui_path


def _write_api_history(task_dir: Path, entries: list) -> Path:
    """Write api_conversation_history.json in task_dir."""
    api_path = task_dir / "api_conversation_history.json"
    with open(api_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f)
    return api_path


# ============================================================================
# Tests for _parse_ui_messages
# ============================================================================

class TestParseUiMessages:
    """Tests for _parse_ui_messages function."""

    def test_keeps_say_task_as_user(self):
        """say:task entries are kept as user messages."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Build a REST API"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'user'
            assert msgs[0]['content'] == "Build a REST API"

    def test_keeps_say_user_feedback_as_user(self):
        """say:user_feedback entries are kept as user messages."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("user_feedback", "Please also add tests"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'user'

    def test_keeps_say_text_as_assistant(self):
        """say:text entries are kept as assistant messages."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("text", "Here is the implementation"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'assistant'
            assert msgs[0]['content'] == "Here is the implementation"

    def test_keeps_say_completion_result_as_assistant(self):
        """say:completion_result entries are kept as assistant."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("completion_result", "Task completed successfully"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'assistant'

    def test_skips_reasoning(self):
        """say:reasoning entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("reasoning", "Let me think..."),
                _make_ui_say("text", "Response"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2
            assert all(m['subtype'] != 'reasoning' for m in msgs)

    def test_skips_api_req_started(self):
        """say:api_req_started entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("api_req_started", '{"model":"claude"}'),
                _make_ui_say("text", "Response"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_skips_checkpoint_created(self):
        """say:checkpoint_created entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("checkpoint_created", ""),
                _make_ui_say("text", "Done"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_skips_task_progress(self):
        """say:task_progress entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("task_progress", "- [x] Step 1"),
                _make_ui_say("text", "Done"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_skips_tool_and_mcp(self):
        """say:tool and say:use_mcp_server entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("tool", '{"tool":"read_file"}'),
                _make_ui_say("use_mcp_server", "mcp data"),
                _make_ui_say("mcp_server_request_started", "req"),
                _make_ui_say("mcp_server_response", "resp"),
                _make_ui_say("text", "Done"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_keeps_ask_plan_mode_respond(self):
        """ask:plan_mode_respond entries are kept as assistant."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            text = json.dumps({"response": "Here is my plan"})
            _write_ui_messages(task_dir, [_make_ui_ask("plan_mode_respond", text)])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'assistant'
            assert msgs[0]['content'] == "Here is my plan"

    def test_keeps_ask_followup(self):
        """ask:followup entries are kept as assistant."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            text = json.dumps({"question": "Which file?", "options": ["a.py", "b.py"]})
            _write_ui_messages(task_dir, [_make_ui_ask("followup", text)])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'assistant'
            assert "Which file?" in msgs[0]['content']
            assert "- a.py" in msgs[0]['content']

    def test_skips_ask_tool(self):
        """ask:tool entries are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            text = json.dumps({"tool": "read_file", "path": "/test.py"})
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_ask("tool", text),
                _make_ui_say("text", "Done"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_skips_ask_resume_task(self):
        """ask:resume_task and resume_completed_task are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_ask("resume_task", ""),
                _make_ui_ask("resume_completed_task", ""),
                _make_ui_say("text", "Done"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 2

    def test_skips_empty_text_messages(self):
        """Messages with empty or whitespace-only text are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", ""),
                _make_ui_say("task", "   "),
                _make_ui_say("task", "Real message"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "Real message"

    def test_invalid_json_raises(self):
        """Invalid JSON file raises InvalidChatFileError."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            ui_path = task_dir / "ui_messages.json"
            ui_path.write_text("not json")
            with pytest.raises(InvalidChatFileError):
                _parse_ui_messages(ui_path)

    def test_missing_file_raises(self):
        """Missing file raises ChatFileNotFoundError."""
        with pytest.raises(ChatFileNotFoundError):
            _parse_ui_messages(Path("/nonexistent/ui_messages.json"))


# ============================================================================
# Tests for decode_ask_text
# ============================================================================

class TestDecodeAskText:
    """Tests for decode_ask_text function."""

    def test_plan_mode_respond_extracts_response(self):
        """plan_mode_respond extracts the 'response' field."""
        raw = json.dumps({"response": "My plan is..."})
        assert decode_ask_text("plan_mode_respond", raw) == "My plan is..."

    def test_followup_extracts_question(self):
        """followup extracts the 'question' field."""
        raw = json.dumps({"question": "Which approach?"})
        assert decode_ask_text("followup", raw) == "Which approach?"

    def test_followup_with_options(self):
        """followup includes options as a list."""
        raw = json.dumps({"question": "Choose:", "options": ["A", "B"]})
        result = decode_ask_text("followup", raw)
        assert "Choose:" in result
        assert "- A" in result
        assert "- B" in result

    def test_followup_options_only(self):
        """followup with only options (no question)."""
        raw = json.dumps({"question": "", "options": ["X", "Y"]})
        result = decode_ask_text("followup", raw)
        assert "- X" in result
        assert "- Y" in result

    def test_completion_result_extracts_response(self):
        """completion_result extracts the 'response' field."""
        raw = json.dumps({"response": "All done"})
        assert decode_ask_text("completion_result", raw) == "All done"

    def test_malformed_json_returns_raw(self):
        """Invalid JSON returns raw text unchanged."""
        assert decode_ask_text("plan_mode_respond", "not json") == "not json"

    def test_non_dict_json_returns_str(self):
        """Non-dict JSON (e.g., array, number) returns str()."""
        raw = json.dumps([1, 2, 3])
        result = decode_ask_text("plan_mode_respond", raw)
        assert result == str([1, 2, 3])

    def test_none_input_returns_empty_string(self):
        """None input returns empty string (TypeError caught, coerced to str)."""
        assert decode_ask_text("plan_mode_respond", None) == ""


# ============================================================================
# Tests for _parse_api_history (fallback)
# ============================================================================

class TestParseApiHistory:
    """Tests for _parse_api_history fallback function."""

    def test_basic_user_assistant(self):
        """Parses basic user/assistant messages."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "user", "content": [
                    {"type": "text", "text": "<task>\nHello world\n</task>"}
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "Hi there!"}
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 2
            assert msgs[0]['role'] == 'user'
            assert "Hello world" in msgs[0]['content']
            assert msgs[1]['role'] == 'assistant'
            assert msgs[1]['content'] == "Hi there!"

    def test_strips_environment_details(self):
        """Removes <environment_details> blocks from user messages."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "user", "content": [
                    {"type": "text", "text": "<task>\nDo something\n</task>"},
                    {"type": "text", "text": "<environment_details>\nOS: darwin\n</environment_details>"},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert "environment_details" not in msgs[0]['content']
            assert "Do something" in msgs[0]['content']

    def test_drops_tool_use_blocks(self):
        """tool_use blocks are filtered out."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "assistant", "content": [
                    {"type": "text", "text": "Let me check"},
                    {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "Let me check"

    def test_skips_pure_tool_result_turns(self):
        """User turns with only tool results (no text after stripping) are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "file contents"},
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "Got it"},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert msgs[0]['role'] == 'assistant'

    def test_missing_file_raises(self):
        """Missing file raises ChatFileNotFoundError."""
        with pytest.raises(ChatFileNotFoundError):
            _parse_api_history(Path("/nonexistent/api_conversation_history.json"))

    def test_invalid_json_raises(self):
        """Invalid JSON raises InvalidChatFileError."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            api_path = task_dir / "api_conversation_history.json"
            api_path.write_text("not json")
            with pytest.raises(InvalidChatFileError):
                _parse_api_history(api_path)


# ============================================================================
# Tests for parse_cline_vscode_task (primary + fallback orchestrator)
# ============================================================================

class TestParseClineTask:
    """Tests for parse_cline_vscode_task function."""

    def test_parses_primary_ui_messages(self):
        """Primary path: parses ui_messages.json."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                _make_ui_say("task", "Hello"),
                _make_ui_say("text", "Hi there"),
            ])
            session = parse_cline_vscode_task(task_dir, task_id="123", cwd="/proj")
            assert len(session.messages) == 2
            assert session.task_id == "123"
            assert session.cwd == "/proj"

    def test_fallback_to_api_history(self):
        """When ui_messages.json is missing, falls back to api_history."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "user", "content": [
                    {"type": "text", "text": "<task>\nHello\n</task>"}
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "Response"}
                ]},
            ])
            session = parse_cline_vscode_task(task_dir, task_id="456")
            assert len(session.messages) == 2

    def test_fallback_on_empty_ui_messages(self):
        """Empty ui_messages (no conversation) triggers fallback."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            # Write ui_messages with only skippable content
            _write_ui_messages(task_dir, [
                _make_ui_say("reasoning", "thinking"),
            ])
            _write_api_history(task_dir, [
                {"role": "user", "content": [
                    {"type": "text", "text": "<task>\nFallback\n</task>"}
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "From API"}
                ]},
            ])
            session = parse_cline_vscode_task(task_dir)
            assert len(session.messages) == 2
            assert "Fallback" in session.messages[0]['content']

    def test_missing_task_dir_raises(self):
        """Non-existent task dir raises ChatFileNotFoundError."""
        with pytest.raises(ChatFileNotFoundError):
            parse_cline_vscode_task(Path("/nonexistent/task/dir"))

    def test_no_conversation_files_raises(self):
        """Task dir with no conversation files raises InvalidChatFileError."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            # Don't create either file
            with pytest.raises(InvalidChatFileError):
                parse_cline_vscode_task(task_dir)

    def test_metadata_passed_through(self):
        """Metadata args populate the session correctly."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [_make_ui_say("task", "Hello")])
            session = parse_cline_vscode_task(
                task_dir,
                task_id="999",
                cwd="/workspace",
                title="Test task",
                timestamp="1781697826685",
                model="claude-opus-4.6",
                total_cost=0.05,
            )
            assert session.task_id == "999"
            assert session.cwd == "/workspace"
            assert session.title == "Test task"
            assert session.timestamp == "1781697826685"
            assert session.model == "claude-opus-4.6"
            assert session.total_cost == 0.05

    def test_task_id_defaults_to_dir_name(self):
        """If task_id not provided, defaults to directory name."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir) / "1781697826685"
            task_dir.mkdir()
            _write_ui_messages(task_dir, [_make_ui_say("task", "Hello")])
            session = parse_cline_vscode_task(task_dir)
            assert session.task_id == "1781697826685"


# ============================================================================
# Tests for normalize_cline_content
# ============================================================================

class TestNormalizeClineContent:
    """Tests for normalize_cline_content function."""

    def test_string_content(self):
        assert normalize_cline_content("hello") == "hello"

    def test_strips_whitespace(self):
        assert normalize_cline_content("  hello  ") == "hello"

    def test_empty_string(self):
        assert normalize_cline_content("") == ""

    def test_none(self):
        assert normalize_cline_content(None) == ""

    def test_list_of_text_blocks(self):
        content = [{"type": "text", "text": "Part 1"}, {"type": "text", "text": "Part 2"}]
        assert normalize_cline_content(content) == "Part 1\nPart 2"

    def test_list_of_strings(self):
        content = ["Hello", "World"]
        assert normalize_cline_content(content) == "Hello\nWorld"


# ============================================================================
# Tests for extract_cline_messages
# ============================================================================

class TestExtractClineMessages:
    """Tests for extract_cline_messages function."""

    def test_basic_extraction(self):
        """Extracts ChatMessage objects from session."""
        session = ClineVscodeSession(
            task_id="test-1",
            cwd="/project",
            title="Test",
            timestamp="1781697826685",
            messages=[
                {'role': 'user', 'content': 'Hello', 'timestamp': 1000, 'subtype': 'task'},
                {'role': 'assistant', 'content': 'Hi!', 'timestamp': 2000, 'subtype': 'text'},
            ]
        )
        msgs = extract_cline_vscode_messages(session)
        assert len(msgs) == 2
        assert msgs[0].role == 'user'
        assert msgs[0].content == 'Hello'
        assert msgs[0].source == ChatSource.CLINE_VSCODE
        assert msgs[0].execution_id == "test-1"
        assert msgs[1].role == 'assistant'
        assert msgs[1].content == 'Hi!'

    def test_skips_empty_content(self):
        """Messages with empty content after normalization are skipped."""
        session = ClineVscodeSession(
            task_id="test-1",
            cwd="/project",
            title="Test",
            timestamp="1000",
            messages=[
                {'role': 'user', 'content': 'Hello', 'timestamp': 1000, 'subtype': 'task'},
                {'role': 'assistant', 'content': '', 'timestamp': 2000, 'subtype': 'text'},
                {'role': 'assistant', 'content': '   ', 'timestamp': 3000, 'subtype': 'text'},
            ]
        )
        msgs = extract_cline_vscode_messages(session)
        assert len(msgs) == 1
        assert msgs[0].content == 'Hello'

    def test_execution_id_is_task_id(self):
        """execution_id is set to session task_id."""
        session = ClineVscodeSession(
            task_id="my-task-id",
            cwd="/project",
            title="Test",
            timestamp="1000",
            messages=[
                {'role': 'user', 'content': 'Test', 'timestamp': 1000, 'subtype': 'task'},
            ]
        )
        msgs = extract_cline_vscode_messages(session)
        assert msgs[0].execution_id == "my-task-id"


# ============================================================================
# Tests for _strip_api_wrapper_noise
# ============================================================================

class TestStripApiWrapperNoise:
    """Tests for _strip_api_wrapper_noise function."""

    def test_unwraps_task_tags(self):
        """<task>...</task> wrappers are unwrapped."""
        text = "<task>\nHello world\n</task>"
        assert _strip_api_wrapper_noise(text) == "Hello world"

    def test_removes_environment_details(self):
        """<environment_details> blocks are removed entirely."""
        text = "Hello <environment_details>\nOS info\n</environment_details> world"
        result = _strip_api_wrapper_noise(text)
        assert "environment_details" not in result
        assert "OS info" not in result

    def test_plain_text_unchanged(self):
        """Plain text without wrappers passes through."""
        assert _strip_api_wrapper_noise("just text") == "just text"


# ============================================================================
# Robustness tests for malformed-but-valid JSON
# ============================================================================

class TestParserRobustness:
    """Tests for malformed-but-valid JSON structures."""

    def test_ui_messages_null_text_skipped(self):
        """say entry with text: null is skipped gracefully."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                {"ts": 1000, "type": "say", "say": "task", "text": None},
                _make_ui_say("task", "Real message"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "Real message"

    def test_ui_messages_numeric_text_converted(self):
        """say entry with numeric text is converted to string."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                {"ts": 1000, "type": "say", "say": "task", "text": 42},
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "42"

    def test_ui_messages_non_dict_entries_skipped(self):
        """Non-dict entries in ui_messages array are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [
                "not a dict",
                42,
                None,
                _make_ui_say("task", "Valid"),
            ])
            msgs = _parse_ui_messages(task_dir / "ui_messages.json")
            assert len(msgs) == 1

    def test_api_history_null_text_block_skipped(self):
        """API history text block with text: null is skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "assistant", "content": [
                    {"type": "text", "text": None},
                    {"type": "text", "text": "Valid text"},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "Valid text"

    def test_api_history_numeric_text_block(self):
        """API history text block with numeric text is handled."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "assistant", "content": [
                    {"type": "text", "text": 123},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "123"

    def test_api_history_non_dict_content_blocks_skipped(self):
        """Non-dict content blocks in API history are skipped."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_api_history(task_dir, [
                {"role": "assistant", "content": [
                    "not a dict",
                    42,
                    {"type": "text", "text": "Valid"},
                ]},
            ])
            msgs = _parse_api_history(task_dir / "api_conversation_history.json")
            assert len(msgs) == 1
            assert msgs[0]['content'] == "Valid"

    def test_ui_messages_not_array_raises(self):
        """ui_messages.json that is not an array raises error."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            ui_path = task_dir / "ui_messages.json"
            ui_path.write_text('{"not": "an array"}')
            with pytest.raises(InvalidChatFileError):
                _parse_ui_messages(ui_path)

    def test_api_history_not_array_raises(self):
        """api_conversation_history.json that is not an array raises error."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            api_path = task_dir / "api_conversation_history.json"
            api_path.write_text('{"not": "an array"}')
            with pytest.raises(InvalidChatFileError):
                _parse_api_history(api_path)


    def testdecode_ask_text_numeric_response(self):
        """ask with numeric response returns string."""
        raw = json.dumps({"response": 42})
        result = decode_ask_text("plan_mode_respond", raw)
        assert result == "42"

    def testdecode_ask_text_null_response(self):
        """ask with null response returns empty string."""
        raw = json.dumps({"response": None})
        result = decode_ask_text("plan_mode_respond", raw)
        assert result == ""

    def testdecode_ask_text_non_list_options(self):
        """followup with non-list options still returns question."""
        raw = json.dumps({"question": "Pick one", "options": "not a list"})
        result = decode_ask_text("followup", raw)
        assert result == "Pick one"

    def test_task_metadata_as_list_ignored(self):
        """task_metadata.json that is a list (not dict) doesn't crash."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [_make_ui_say("task", "Hello")])
            metadata_path = task_dir / "task_metadata.json"
            metadata_path.write_text("[]")
            session = parse_cline_vscode_task(task_dir)
            assert session.cline_version == ""

    def test_task_metadata_env_history_non_list(self):
        """task_metadata with non-list environment_history doesn't crash."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [_make_ui_say("task", "Hello")])
            metadata_path = task_dir / "task_metadata.json"
            metadata_path.write_text(json.dumps({"environment_history": "bad"}))
            session = parse_cline_vscode_task(task_dir)
            assert session.cline_version == ""

    def test_task_metadata_env_history_with_non_dict_items(self):
        """task_metadata with non-dict items in env_history doesn't crash."""
        with TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            _write_ui_messages(task_dir, [_make_ui_say("task", "Hello")])
            metadata_path = task_dir / "task_metadata.json"
            metadata_path.write_text(json.dumps({"environment_history": [None, 42]}))
            session = parse_cline_vscode_task(task_dir)
            assert session.cline_version == ""

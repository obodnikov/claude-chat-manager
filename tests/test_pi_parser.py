"""Tests for pi coding agent session parser (src/pi_parser.py)."""

import json
import pytest
from pathlib import Path

from src.pi_parser import (
    PiSession,
    parse_pi_session_meta,
    parse_pi_session_file,
    normalize_pi_content,
    extract_pi_messages,
)
from src.models import ChatSource
from src.exceptions import ChatFileNotFoundError, InvalidChatFileError
from src.parser import count_pi_messages_in_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_HEADER = {
    "type": "session",
    "version": 3,
    "id": "019ef0c5-fdf8-7626-ad4d-da7ee350c408",
    "timestamp": "2026-06-22T19:19:27.993Z",
    "cwd": "/Users/test/src/my-project",
}

USER_MSG_ENTRY = {
    "type": "message",
    "id": "aaa1",
    "parentId": "root",
    "timestamp": "2026-06-22T19:20:00.000Z",
    "message": {"role": "user", "content": "Hello, world!"},
}

ASSISTANT_MSG_ENTRY = {
    "type": "message",
    "id": "aaa2",
    "parentId": "aaa1",
    "timestamp": "2026-06-22T19:20:01.000Z",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Hi there!"},
            {"type": "thinking", "thinking": "internal thought"},
        ],
    },
}

TOOL_MSG_ENTRY = {
    "type": "message",
    "id": "aaa3",
    "parentId": "aaa2",
    "timestamp": "2026-06-22T19:20:02.000Z",
    "message": {"role": "toolResult", "content": "tool output"},
}

LIFECYCLE_ENTRY = {
    "type": "model_change",
    "id": "aaa4",
    "parentId": "aaa3",
    "timestamp": "2026-06-22T19:20:03.000Z",
}


def _write_session(path: Path, lines: list) -> None:
    """Write a list of dicts as JSONL to path."""
    with open(path, "w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")


# ---------------------------------------------------------------------------
# parse_pi_session_meta
# ---------------------------------------------------------------------------


class TestParsePiSessionMeta:
    def test_returns_header_dict(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [VALID_HEADER, USER_MSG_ENTRY])
        result = parse_pi_session_meta(f)
        assert result["id"] == VALID_HEADER["id"]
        assert result["cwd"] == VALID_HEADER["cwd"]
        assert result["version"] == 3

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(ChatFileNotFoundError):
            parse_pi_session_meta(tmp_path / "missing.jsonl")

    def test_empty_file_raises(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        with pytest.raises(InvalidChatFileError):
            parse_pi_session_meta(f)

    def test_wrong_type_raises(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        _write_session(f, [{"type": "session_meta", "id": "x"}])
        with pytest.raises(InvalidChatFileError, match="type="):
            parse_pi_session_meta(f)

    def test_invalid_json_raises(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text("{not valid json}\n")
        with pytest.raises(InvalidChatFileError):
            parse_pi_session_meta(f)

    def test_non_dict_json_raises(self, tmp_path):
        """Valid JSON that is not a dict (list, string, number) must raise."""
        for value in (["a", "b"], "just a string", 42):
            f = tmp_path / "nondic.jsonl"
            f.write_text(json.dumps(value) + "\n")
            with pytest.raises(InvalidChatFileError):
                parse_pi_session_meta(f)


# ---------------------------------------------------------------------------
# normalize_pi_content
# ---------------------------------------------------------------------------


class TestNormalizePiContent:
    def test_bare_string_passthrough(self):
        assert normalize_pi_content("hello") == "hello"

    def test_empty_string(self):
        assert normalize_pi_content("") == ""

    def test_list_of_text_blocks(self):
        content = [
            {"type": "text", "text": "line one"},
            {"type": "text", "text": "line two"},
        ]
        result = normalize_pi_content(content)
        assert result == "line one\nline two"

    def test_thinking_blocks_dropped(self):
        content = [
            {"type": "thinking", "thinking": "internal"},
            {"type": "text", "text": "visible"},
        ]
        assert normalize_pi_content(content) == "visible"

    def test_tool_call_blocks_dropped(self):
        content = [
            {"type": "toolCall", "name": "bash", "input": {}},
            {"type": "text", "text": "result"},
        ]
        assert normalize_pi_content(content) == "result"

    def test_image_blocks_dropped(self):
        content = [
            {"type": "image", "source": {"type": "base64", "data": "..."}},
        ]
        assert normalize_pi_content(content) == ""

    def test_mixed_keeps_only_text(self):
        content = [
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": "kept"},
            {"type": "toolCall", "name": "read"},
        ]
        assert normalize_pi_content(content) == "kept"

    def test_image_only_returns_empty(self):
        content = [{"type": "image", "source": {}}]
        assert normalize_pi_content(content) == ""

    def test_non_dict_list_items_ignored(self):
        content = ["bare string item", {"type": "text", "text": "ok"}]
        assert normalize_pi_content(content) == "ok"


# ---------------------------------------------------------------------------
# parse_pi_session_file
# ---------------------------------------------------------------------------


class TestParsePiSessionFile:
    def test_basic_parse(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [VALID_HEADER, USER_MSG_ENTRY, ASSISTANT_MSG_ENTRY])
        session = parse_pi_session_file(f)
        assert session.session_id == VALID_HEADER["id"]
        assert session.cwd == VALID_HEADER["cwd"]
        assert session.version == 3
        assert session.timestamp == VALID_HEADER["timestamp"]
        assert session.file_path == f

    def test_keeps_user_and_assistant(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [VALID_HEADER, USER_MSG_ENTRY, ASSISTANT_MSG_ENTRY])
        session = parse_pi_session_file(f)
        assert len(session.messages) == 2
        roles = [m["role"] for m in session.messages]
        assert roles == ["user", "assistant"]

    def test_skips_tool_result_role(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [VALID_HEADER, USER_MSG_ENTRY, TOOL_MSG_ENTRY])
        session = parse_pi_session_file(f)
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"

    def test_skips_lifecycle_entries(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f, [VALID_HEADER, USER_MSG_ENTRY, LIFECYCLE_ENTRY, ASSISTANT_MSG_ENTRY]
        )
        session = parse_pi_session_file(f)
        assert len(session.messages) == 2

    def test_malformed_line_skipped_not_aborted(self, tmp_path):
        f = tmp_path / "session.jsonl"
        with open(f, "w") as fh:
            fh.write(json.dumps(VALID_HEADER) + "\n")
            fh.write("{bad json line\n")  # malformed
            fh.write(json.dumps(USER_MSG_ENTRY) + "\n")
        session = parse_pi_session_file(f)
        assert len(session.messages) == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ChatFileNotFoundError):
            parse_pi_session_file(tmp_path / "missing.jsonl")

    def test_missing_header_raises(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [USER_MSG_ENTRY])  # no session header
        with pytest.raises(InvalidChatFileError):
            parse_pi_session_file(f)

    def test_empty_messages(self, tmp_path):
        f = tmp_path / "session.jsonl"
        _write_session(f, [VALID_HEADER])
        session = parse_pi_session_file(f)
        assert session.messages == []

    def test_version_1_tolerated(self, tmp_path):
        header_v1 = {**VALID_HEADER, "version": 1}
        f = tmp_path / "session.jsonl"
        _write_session(f, [header_v1, USER_MSG_ENTRY])
        session = parse_pi_session_file(f)
        assert session.version == 1

    def test_leading_blank_line_tolerated(self, tmp_path):
        """A file with a leading blank line before the header must parse correctly."""
        f = tmp_path / "session_blank.jsonl"
        with open(f, "w") as fh:
            fh.write("\n")  # leading blank line
            fh.write(json.dumps(VALID_HEADER) + "\n")
            fh.write(json.dumps(USER_MSG_ENTRY) + "\n")
        session = parse_pi_session_file(f)
        assert session.session_id == VALID_HEADER["id"]
        assert len(session.messages) == 1

    def test_parse_session_meta_leading_blank_line(self, tmp_path):
        """parse_pi_session_meta tolerates a leading blank line before the header."""
        f = tmp_path / "session_blank_meta.jsonl"
        with open(f, "w") as fh:
            fh.write("\n")
            fh.write(json.dumps(VALID_HEADER) + "\n")
        result = parse_pi_session_meta(f)
        assert result["id"] == VALID_HEADER["id"]

    def test_invalid_version_defaults_to_1(self, tmp_path):
        """Non-int version value (e.g. 'v3', None) must default to 1 without raising."""
        for i, bad_version in enumerate(("v3", "", None)):
            header = {**VALID_HEADER, "version": bad_version}
            f = tmp_path / f"session_bad_version_{i}.jsonl"
            _write_session(f, [header, USER_MSG_ENTRY])
            session = parse_pi_session_file(f)
            assert session.version == 1, f"Expected version=1 for {bad_version!r}"


# ---------------------------------------------------------------------------
# extract_pi_messages
# ---------------------------------------------------------------------------


class TestExtractPiMessages:
    def _make_session(self, messages: list) -> PiSession:
        return PiSession(
            session_id="test-uuid-1234",
            cwd="/tmp/project",
            timestamp="2026-06-22T19:19:27.993Z",
            version=3,
            messages=messages,
            file_path=None,
        )

    def test_source_is_pi(self):
        session = self._make_session(
            [{"role": "user", "content": "hello", "timestamp": None}]
        )
        msgs = extract_pi_messages(session)
        assert all(m.source == ChatSource.PI for m in msgs)

    def test_execution_id_is_session_uuid(self):
        session = self._make_session(
            [{"role": "user", "content": "hello", "timestamp": None}]
        )
        msgs = extract_pi_messages(session)
        assert all(m.execution_id == "test-uuid-1234" for m in msgs)

    def test_empty_after_normalize_skipped(self):
        # Image-only content → empty after normalisation → dropped
        session = self._make_session(
            [
                {
                    "role": "assistant",
                    "content": [{"type": "image", "source": {}}],
                    "timestamp": None,
                }
            ]
        )
        msgs = extract_pi_messages(session)
        assert msgs == []

    def test_bare_string_content(self):
        session = self._make_session(
            [{"role": "user", "content": "plain text", "timestamp": "2026-01-01T00:00:00Z"}]
        )
        msgs = extract_pi_messages(session)
        assert len(msgs) == 1
        assert msgs[0].content == "plain text"
        assert msgs[0].role == "user"

    def test_list_content_normalised(self):
        content = [
            {"type": "text", "text": "part one"},
            {"type": "thinking", "thinking": "skip me"},
            {"type": "text", "text": "part two"},
        ]
        session = self._make_session(
            [{"role": "assistant", "content": content, "timestamp": None}]
        )
        msgs = extract_pi_messages(session)
        assert len(msgs) == 1
        assert msgs[0].content == "part one\npart two"

    def test_timestamp_preserved(self):
        ts = "2026-06-22T19:20:00.000Z"
        session = self._make_session(
            [{"role": "user", "content": "hi", "timestamp": ts}]
        )
        msgs = extract_pi_messages(session)
        assert msgs[0].timestamp == ts

    def test_empty_session_returns_empty_list(self):
        session = self._make_session([])
        assert extract_pi_messages(session) == []


# ---------------------------------------------------------------------------
# count_pi_messages_in_file
# ---------------------------------------------------------------------------


class TestCountPiMessagesInFile:
    def _write_lines(self, path: Path, lines: list) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for obj in lines:
                if isinstance(obj, str):
                    fh.write(obj + "\n")
                else:
                    fh.write(json.dumps(obj) + "\n")

    def test_counts_user_and_assistant(self, tmp_path):
        f = tmp_path / "s.jsonl"
        self._write_lines(f, [
            VALID_HEADER,
            USER_MSG_ENTRY,
            ASSISTANT_MSG_ENTRY,
        ])
        assert count_pi_messages_in_file(f) == 2

    def test_does_not_count_tool_result(self, tmp_path):
        f = tmp_path / "s.jsonl"
        self._write_lines(f, [VALID_HEADER, USER_MSG_ENTRY, TOOL_MSG_ENTRY])
        assert count_pi_messages_in_file(f) == 1

    def test_does_not_count_lifecycle_entries(self, tmp_path):
        f = tmp_path / "s.jsonl"
        self._write_lines(f, [VALID_HEADER, LIFECYCLE_ENTRY, USER_MSG_ENTRY])
        assert count_pi_messages_in_file(f) == 1

    def test_invalid_json_lines_ignored(self, tmp_path):
        f = tmp_path / "s.jsonl"
        with open(f, "w") as fh:
            fh.write(json.dumps(VALID_HEADER) + "\n")
            fh.write("{bad json\n")
            fh.write(json.dumps(USER_MSG_ENTRY) + "\n")
        assert count_pi_messages_in_file(f) == 1

    def test_non_dict_json_lines_ignored(self, tmp_path):
        """Valid JSON but not a dict (list, number, string) must not crash or count."""
        f = tmp_path / "s.jsonl"
        with open(f, "w") as fh:
            fh.write(json.dumps(VALID_HEADER) + "\n")
            fh.write(json.dumps(["list", "value"]) + "\n")  # valid JSON, not a dict
            fh.write(json.dumps(42) + "\n")                 # valid JSON number
            fh.write(json.dumps(USER_MSG_ENTRY) + "\n")
        assert count_pi_messages_in_file(f) == 1

    def test_empty_file_returns_zero(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert count_pi_messages_in_file(f) == 0

    def test_missing_file_returns_zero(self, tmp_path):
        assert count_pi_messages_in_file(tmp_path / "missing.jsonl") == 0

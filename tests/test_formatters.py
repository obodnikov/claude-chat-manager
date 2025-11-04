"""Tests for formatters module."""

import pytest
from src.formatters import (
    format_timestamp,
    clean_project_name,
    format_content,
    format_tool_use
)


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_format_timestamp_none(self):
        """Test formatting None timestamp."""
        assert format_timestamp(None) == 'No timestamp'

    def test_format_timestamp_iso_string(self):
        """Test formatting ISO format timestamp string."""
        result = format_timestamp("2025-09-20T12:28:46.794Z")
        assert "2025-09-20" in result
        assert "12:28:46" in result

    def test_format_timestamp_milliseconds(self):
        """Test formatting milliseconds timestamp."""
        # 1695217726000 = 2023-09-20 12:28:46
        result = format_timestamp(1695217726000)
        assert "2023-09-20" in result

    def test_format_timestamp_seconds(self):
        """Test formatting seconds timestamp."""
        result = format_timestamp(1695217726)
        assert "2023-09-20" in result

    def test_format_timestamp_invalid(self):
        """Test formatting invalid timestamp."""
        result = format_timestamp("invalid")
        assert result == "invalid"


class TestCleanProjectName:
    """Tests for clean_project_name function."""

    def test_clean_project_name_with_dash(self):
        """Test cleaning project name with leading dash."""
        assert clean_project_name("-my-project-name") == "My Project Name"

    def test_clean_project_name_without_dash(self):
        """Test cleaning project name without leading dash."""
        assert clean_project_name("my-project-name") == "My Project Name"

    def test_clean_project_name_single_word(self):
        """Test cleaning single word project name."""
        assert clean_project_name("project") == "Project"


class TestFormatContent:
    """Tests for format_content function."""

    def test_format_content_string(self):
        """Test formatting string content."""
        result = format_content("Hello world", "user")
        assert result == "Hello world"

    def test_format_content_empty_string(self):
        """Test formatting empty string content."""
        result = format_content("", "user")
        # Empty strings are treated as "no content"
        assert "[No content in user message]" in result or "[Empty user message]" in result

    def test_format_content_none(self):
        """Test formatting None content."""
        result = format_content(None, "assistant")
        assert "[Empty assistant message]" in result

    def test_format_content_list_with_text(self):
        """Test formatting list content with text."""
        content = [{"type": "text", "text": "Hello"}]
        result = format_content(content, "user")
        assert "Hello" in result

    def test_format_content_dict_with_text(self):
        """Test formatting dict content with text."""
        content = {"text": "Hello world"}
        result = format_content(content, "user")
        assert "Hello world" in result


class TestFormatToolUse:
    """Tests for format_tool_use function."""

    def test_format_tool_use_file_path(self):
        """Test formatting tool use with file_path."""
        tool_input = {"file_path": "/path/to/file.txt"}
        result = format_tool_use(tool_input)
        assert any("File:" in line for line in result)
        assert any("/path/to/file.txt" in line for line in result)

    def test_format_tool_use_todos(self):
        """Test formatting tool use with todos."""
        tool_input = {
            "todos": [
                {"content": "Task 1", "status": "pending"},
                {"content": "Task 2", "status": "completed"}
            ]
        }
        result = format_tool_use(tool_input)
        assert any("Todos:" in line for line in result)
        assert any("Task 1" in line for line in result)

    def test_format_tool_use_edits(self):
        """Test formatting tool use with edits."""
        tool_input = {"edits": [{"old": "a", "new": "b"}]}
        result = format_tool_use(tool_input)
        assert any("Edits:" in line for line in result)

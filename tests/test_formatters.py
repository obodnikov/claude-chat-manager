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

    def test_format_content_kiro_image_url(self):
        """Test formatting Kiro image_url blocks."""
        content = [
            {"type": "text", "text": "Check this image:"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        ]
        result = format_content(content, "user")
        assert "Check this image:" in result
        assert "[Image]" in result

    def test_format_content_kiro_tool_use(self):
        """Test formatting Kiro tool use blocks."""
        content = [
            {"type": "text", "text": "Running tool"},
            {"type": "tool_use", "name": "readFile", "input": {"file_path": "test.py"}}
        ]
        result = format_content(content, "assistant")
        assert "Running tool" in result
        assert "[Tool Use: readFile]" in result

    def test_format_content_kiro_mixed_blocks(self):
        """Test formatting mixed Kiro content blocks."""
        content = [
            {"type": "text", "text": "First part"},
            {"type": "image_url", "image_url": {"url": "..."}},
            {"type": "text", "text": "Second part"},
            {"type": "tool_use", "name": "execute", "input": {}}
        ]
        result = format_content(content, "user")
        assert "First part" in result
        assert "[Image]" in result
        assert "Second part" in result
        assert "[Tool Use: execute]" in result

    def test_format_content_malformed_tool_use_missing_name(self):
        """Test formatting tool use block with missing name key."""
        content = [
            {"type": "tool_use", "input": {"param": "value"}}
        ]
        result = format_content(content, "assistant")
        # Should use 'unknown' as fallback
        assert "[Tool Use: unknown]" in result

    def test_format_content_malformed_tool_use_missing_input(self):
        """Test formatting tool use block with missing input key."""
        content = [
            {"type": "tool_use", "name": "myTool"}
        ]
        result = format_content(content, "assistant")
        # Should still format the tool name
        assert "[Tool Use: myTool]" in result

    def test_format_content_malformed_image_url_missing_key(self):
        """Test formatting image_url block with missing image_url key."""
        content = [
            {"type": "image_url"}
        ]
        result = format_content(content, "user")
        # Should still indicate image presence
        assert "[Image]" in result

    def test_format_content_malformed_image_url_invalid_structure(self):
        """Test formatting image_url block with invalid structure."""
        content = [
            {"type": "image_url", "image_url": "not-a-dict"}
        ]
        result = format_content(content, "user")
        # Should still indicate image presence
        assert "[Image]" in result

    def test_format_content_text_block_missing_text_key(self):
        """Test formatting text block with missing text key."""
        content = [
            {"type": "text"}
        ]
        result = format_content(content, "user")
        # Should handle gracefully - empty text is filtered out
        # Result should be empty message indicator
        assert "[Empty user message]" in result or result == ""


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

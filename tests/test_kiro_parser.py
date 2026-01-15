"""Tests for kiro_parser module."""

import json
import pytest
from pathlib import Path
from src.kiro_parser import (
    KiroChatSession,
    parse_kiro_chat_file,
    extract_kiro_messages,
    normalize_kiro_content
)
from src.exceptions import ChatFileNotFoundError, InvalidChatFileError
from src.models import ChatSource


class TestNormalizeKiroContent:
    """Tests for normalize_kiro_content function."""

    def test_normalize_string_content(self):
        """Test normalizing string content returns as-is."""
        content = "Hello, this is a test message"
        result = normalize_kiro_content(content)
        assert result == content

    def test_normalize_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_kiro_content("")
        assert result == ""

    def test_normalize_text_blocks(self):
        """Test normalizing array of text blocks."""
        content = [
            {"type": "text", "text": "First block"},
            {"type": "text", "text": "Second block"}
        ]
        result = normalize_kiro_content(content)
        assert result == "First block\nSecond block"

    def test_normalize_tool_use_block(self):
        """Test normalizing tool use blocks."""
        content = [
            {"type": "text", "text": "Using a tool"},
            {"type": "tool_use", "name": "readFile", "input": {"path": "test.py"}}
        ]
        result = normalize_kiro_content(content)
        assert "Using a tool" in result
        assert "[Tool: readFile]" in result

    def test_normalize_image_url_block(self):
        """Test normalizing image_url blocks."""
        content = [
            {"type": "text", "text": "Here's an image"},
            {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}}
        ]
        result = normalize_kiro_content(content)
        assert "Here's an image" in result
        assert "[Image]" in result

    def test_normalize_image_block(self):
        """Test normalizing image blocks."""
        content = [
            {"type": "image", "source": {"data": "base64data"}}
        ]
        result = normalize_kiro_content(content)
        assert "[Image]" in result

    def test_normalize_mixed_blocks(self):
        """Test normalizing mixed content blocks."""
        content = [
            {"type": "text", "text": "Text before"},
            {"type": "tool_use", "name": "execute"},
            {"type": "text", "text": "Text after"},
            {"type": "image_url", "image_url": {"url": "img.png"}}
        ]
        result = normalize_kiro_content(content)
        assert "Text before" in result
        assert "[Tool: execute]" in result
        assert "Text after" in result
        assert "[Image]" in result

    def test_normalize_empty_list(self):
        """Test normalizing empty list."""
        result = normalize_kiro_content([])
        assert result == ""

    def test_normalize_list_with_non_dict_items(self):
        """Test normalizing list with non-dict items."""
        content = [
            {"type": "text", "text": "Valid block"},
            "invalid item",
            {"type": "text", "text": "Another valid"}
        ]
        result = normalize_kiro_content(content)
        assert "Valid block" in result
        assert "Another valid" in result

    def test_normalize_none_content(self):
        """Test normalizing None content."""
        result = normalize_kiro_content(None)
        assert result == ""

    def test_normalize_numeric_content(self):
        """Test normalizing numeric content."""
        result = normalize_kiro_content(123)
        assert result == "123"


class TestParseKiroChatFile:
    """Tests for parse_kiro_chat_file function."""

    def test_parse_nonexistent_file(self, tmp_path):
        """Test parsing a file that doesn't exist."""
        file_path = tmp_path / "nonexistent.chat"
        with pytest.raises(ChatFileNotFoundError) as exc_info:
            parse_kiro_chat_file(file_path)
        assert "not found" in str(exc_info.value).lower()

    def test_parse_invalid_json(self, tmp_path):
        """Test parsing a file with invalid JSON."""
        file_path = tmp_path / "invalid.chat"
        file_path.write_text("{ invalid json }", encoding='utf-8')
        with pytest.raises(InvalidChatFileError) as exc_info:
            parse_kiro_chat_file(file_path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_parse_valid_simple_chat(self, tmp_path):
        """Test parsing a valid simple chat file."""
        chat_data = {
            "executionId": "exec-123",
            "context": [],
            "chat": [
                {"role": "human", "content": "Hello"},
                {"role": "bot", "content": "Hi there"}
            ]
        }
        file_path = tmp_path / "test-session.chat"
        file_path.write_text(json.dumps(chat_data), encoding='utf-8')
        
        result = parse_kiro_chat_file(file_path)
        
        assert isinstance(result, KiroChatSession)
        assert result.session_id == "test-session"
        assert result.execution_id == "exec-123"
        assert len(result.messages) == 2
        assert result.context == []

    def test_parse_chat_with_structured_content(self, tmp_path):
        """Test parsing chat with structured content."""
        chat_data = {
            "executionId": "exec-456",
            "context": [{"type": "fileTree"}],
            "chat": [
                {
                    "role": "human",
                    "content": [
                        {"type": "text", "text": "Structured message"}
                    ]
                }
            ]
        }
        file_path = tmp_path / "structured.chat"
        file_path.write_text(json.dumps(chat_data), encoding='utf-8')
        
        result = parse_kiro_chat_file(file_path)
        
        assert result.session_id == "structured"
        assert len(result.context) == 1
        assert result.title == "Structured message"

    def test_parse_chat_extracts_title_from_first_message(self, tmp_path):
        """Test that title is extracted from first human message."""
        chat_data = {
            "chat": [
                {"role": "human", "content": "This is the first message that should become the title"}
            ]
        }
        file_path = tmp_path / "title-test.chat"
        file_path.write_text(json.dumps(chat_data), encoding='utf-8')
        
        result = parse_kiro_chat_file(file_path)
        
        # Title should be truncated to 50 characters
        assert len(result.title) == 50
        assert result.title.startswith("This is the first message")

    def test_parse_chat_with_no_messages(self, tmp_path):
        """Test parsing chat with no messages."""
        chat_data = {
            "executionId": "exec-789",
            "chat": []
        }
        file_path = tmp_path / "empty.chat"
        file_path.write_text(json.dumps(chat_data), encoding='utf-8')
        
        result = parse_kiro_chat_file(file_path)
        
        assert result.title == "Untitled Session"
        assert len(result.messages) == 0

    def test_parse_chat_missing_optional_fields(self, tmp_path):
        """Test parsing chat with missing optional fields."""
        chat_data = {
            "chat": [
                {"role": "human", "content": "Test"}
            ]
        }
        file_path = tmp_path / "minimal.chat"
        file_path.write_text(json.dumps(chat_data), encoding='utf-8')
        
        result = parse_kiro_chat_file(file_path)
        
        assert result.execution_id is None
        assert result.context == []
        assert result.created_at is None


class TestExtractKiroMessages:
    """Tests for extract_kiro_messages function."""

    def test_extract_simple_messages(self):
        """Test extracting simple string messages."""
        chat_data = {
            "chat": [
                {"role": "human", "content": "Hello"},
                {"role": "bot", "content": "Hi"}
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        assert len(messages) == 2
        assert messages[0].role == "human"
        assert messages[0].content == "Hello"
        assert messages[0].source == ChatSource.KIRO_IDE
        assert messages[1].role == "bot"
        assert messages[1].content == "Hi"

    def test_extract_messages_with_structured_content(self):
        """Test extracting messages with structured content."""
        chat_data = {
            "chat": [
                {
                    "role": "human",
                    "content": [
                        {"type": "text", "text": "First part"},
                        {"type": "text", "text": "Second part"}
                    ]
                }
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        assert len(messages) == 1
        assert "First part" in messages[0].content
        assert "Second part" in messages[0].content

    def test_extract_messages_preserves_execution_id(self):
        """Test that execution_id is preserved in messages."""
        chat_data = {
            "executionId": "exec-999",
            "chat": [
                {"role": "human", "content": "Test"}
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        assert messages[0].execution_id == "exec-999"

    def test_extract_messages_preserves_context(self):
        """Test that context is preserved in messages."""
        context = [{"type": "file", "path": "test.py"}]
        chat_data = {
            "context": context,
            "chat": [
                {"role": "human", "content": "Test"}
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        assert messages[0].context_items == context

    def test_extract_empty_chat(self):
        """Test extracting from empty chat."""
        chat_data = {"chat": []}
        
        messages = extract_kiro_messages(chat_data)
        
        assert len(messages) == 0

    def test_extract_messages_with_missing_role(self):
        """Test extracting messages with missing role."""
        chat_data = {
            "chat": [
                {"content": "Message without role"}
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        assert len(messages) == 1
        assert messages[0].role == "unknown"

    def test_extract_messages_source_is_kiro(self):
        """Test that all extracted messages have KIRO_IDE source."""
        chat_data = {
            "chat": [
                {"role": "human", "content": "Test 1"},
                {"role": "bot", "content": "Test 2"}
            ]
        }
        
        messages = extract_kiro_messages(chat_data)
        
        for msg in messages:
            assert msg.source == ChatSource.KIRO_IDE

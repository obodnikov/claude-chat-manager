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


# Import additional functions for enrichment tests
from src.kiro_parser import (
    find_execution_log_dirs,
    build_execution_log_index,
    parse_execution_log,
    extract_bot_responses_from_execution_log,
    enrich_chat_with_execution_log,
    extract_kiro_messages_enriched
)


class TestFindExecutionLogDirs:
    """Tests for find_execution_log_dirs function."""

    def test_find_dirs_with_extensionless_files(self, tmp_path):
        """Test finding directories containing extensionless files."""
        # Create a hash-named directory with extensionless file
        hash_dir = tmp_path / "abc123def456"
        hash_dir.mkdir()
        (hash_dir / "execution-id-1").write_text('{"executionId": "test"}')
        
        result = find_execution_log_dirs(tmp_path)
        
        assert len(result) == 1
        assert result[0] == hash_dir

    def test_skip_dirs_without_extensionless_files(self, tmp_path):
        """Test that directories with only extension files are skipped."""
        # Create directory with only .json files
        json_dir = tmp_path / "json_only"
        json_dir.mkdir()
        (json_dir / "file.json").write_text('{}')
        
        result = find_execution_log_dirs(tmp_path)
        
        assert len(result) == 0

    def test_nonexistent_directory(self, tmp_path):
        """Test with nonexistent directory."""
        result = find_execution_log_dirs(tmp_path / "nonexistent")
        assert result == []

    def test_empty_directory(self, tmp_path):
        """Test with empty directory."""
        result = find_execution_log_dirs(tmp_path)
        assert result == []


class TestBuildExecutionLogIndex:
    """Tests for build_execution_log_index function."""

    def test_build_index_single_file(self, tmp_path):
        """Test building index with single execution log."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({"executionId": "exec-001", "data": "test"}))
        
        index = build_execution_log_index(tmp_path)
        
        assert "exec-001" in index
        assert index["exec-001"] == log_file

    def test_build_index_multiple_files(self, tmp_path):
        """Test building index with multiple execution logs."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        
        for i in range(3):
            log_file = hash_dir / f"exec-{i:03d}"
            log_file.write_text(json.dumps({"executionId": f"exec-{i:03d}"}))
        
        index = build_execution_log_index(tmp_path)
        
        assert len(index) == 3
        assert "exec-000" in index
        assert "exec-001" in index
        assert "exec-002" in index

    def test_skip_invalid_json(self, tmp_path):
        """Test that invalid JSON files are skipped."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        (hash_dir / "invalid").write_text("not json")
        (hash_dir / "valid").write_text(json.dumps({"executionId": "valid-id"}))
        
        index = build_execution_log_index(tmp_path)
        
        assert len(index) == 1
        assert "valid-id" in index

    def test_skip_files_without_execution_id(self, tmp_path):
        """Test that files without executionId are skipped."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        (hash_dir / "no-id").write_text(json.dumps({"data": "no execution id"}))
        
        index = build_execution_log_index(tmp_path)
        
        assert len(index) == 0


class TestParseExecutionLog:
    """Tests for parse_execution_log function."""

    def test_parse_valid_log(self, tmp_path):
        """Test parsing valid execution log."""
        log_data = {
            "executionId": "test-123",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Hello"}]}
            ]
        }
        log_file = tmp_path / "test-log"
        log_file.write_text(json.dumps(log_data))
        
        result = parse_execution_log(log_file)
        
        assert result is not None
        assert result["executionId"] == "test-123"

    def test_parse_nonexistent_file(self, tmp_path):
        """Test parsing nonexistent file returns None."""
        result = parse_execution_log(tmp_path / "nonexistent")
        assert result is None

    def test_parse_invalid_json(self, tmp_path):
        """Test parsing invalid JSON returns None."""
        log_file = tmp_path / "invalid"
        log_file.write_text("not valid json")
        
        result = parse_execution_log(log_file)
        assert result is None


class TestExtractBotResponsesFromExecutionLog:
    """Tests for extract_bot_responses_from_execution_log function."""

    def test_extract_single_text_response(self):
        """Test extracting single text response."""
        execution_log = {
            "messagesFromExecutionId": [
                {
                    "role": "bot",
                    "entries": [{"type": "text", "text": "Hello, I can help!"}]
                }
            ]
        }
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 1
        assert responses[0] == "Hello, I can help!"

    def test_extract_multiple_responses(self):
        """Test extracting multiple bot responses."""
        execution_log = {
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "First response"}]},
                {"role": "user", "entries": [{"type": "text", "text": "User message"}]},
                {"role": "bot", "entries": [{"type": "text", "text": "Second response"}]}
            ]
        }
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 2
        assert responses[0] == "First response"
        assert responses[1] == "Second response"

    def test_extract_response_with_tool_use(self):
        """Test extracting response with tool use markers."""
        execution_log = {
            "messagesFromExecutionId": [
                {
                    "role": "bot",
                    "entries": [
                        {"type": "text", "text": "Let me check that file"},
                        {"type": "toolUse", "name": "readFile"}
                    ]
                }
            ]
        }
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 1
        assert "Let me check that file" in responses[0]
        assert "[Tool: readFile]" in responses[0]

    def test_skip_non_bot_messages(self):
        """Test that non-bot messages are skipped."""
        execution_log = {
            "messagesFromExecutionId": [
                {"role": "user", "entries": [{"type": "text", "text": "User message"}]},
                {"role": "system", "entries": [{"type": "text", "text": "System message"}]}
            ]
        }
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 0

    def test_empty_messages_array(self):
        """Test with empty messages array."""
        execution_log = {"messagesFromExecutionId": []}
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 0

    def test_missing_messages_key(self):
        """Test with missing messagesFromExecutionId key."""
        execution_log = {"executionId": "test"}
        
        responses = extract_bot_responses_from_execution_log(execution_log)
        
        assert len(responses) == 0


class TestEnrichChatWithExecutionLog:
    """Tests for enrich_chat_with_execution_log function."""

    def test_enrich_replaces_bot_content(self, tmp_path):
        """Test that bot content is replaced with full response."""
        # Create execution log
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Full detailed response here"}]}
            ]
        }))
        
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Help me"},
                {"role": "bot", "content": "On it."}
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        assert len(errors) == 0
        assert enriched["chat"][1]["content"] == "Full detailed response here"
        assert enriched["chat"][0]["content"] == "Help me"  # User message unchanged

    def test_error_when_no_execution_id(self, tmp_path):
        """Test error when chat has no executionId."""
        chat_data = {"chat": [{"role": "bot", "content": "Test"}]}
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        assert len(errors) == 1
        assert "No executionId" in errors[0]

    def test_error_when_log_not_found(self, tmp_path):
        """Test error when execution log is not found."""
        chat_data = {
            "executionId": "nonexistent-id",
            "chat": [{"role": "bot", "content": "Test"}]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_warning_when_message_count_mismatch(self, tmp_path):
        """Test warning when bot message counts don't match."""
        # Create execution log with 1 bot response
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Only one response"}]}
            ]
        }))
        
        # Chat has 2 bot messages
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "First question"},
                {"role": "bot", "content": "Brief 1"},
                {"role": "human", "content": "Second question"},
                {"role": "bot", "content": "Brief 2"}
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        # Should have mismatch warning
        assert any("mismatch" in e.lower() for e in errors)
        # First bot message should be enriched
        assert enriched["chat"][1]["content"] == "Only one response"
        # Second bot message should keep original (no more responses available)
        assert enriched["chat"][3]["content"] == "Brief 2"

    def test_preserves_user_messages(self, tmp_path):
        """Test that user messages are not modified."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Response"}]}
            ]
        }))
        
        original_user_content = "Original user message with special chars: @#$%"
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": original_user_content},
                {"role": "bot", "content": "Brief"}
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        assert enriched["chat"][0]["content"] == original_user_content


class TestExtractKiroMessagesEnriched:
    """Tests for extract_kiro_messages_enriched function."""

    def test_enriched_extraction_with_workspace(self, tmp_path):
        """Test enriched extraction when workspace is provided."""
        # Create execution log
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Full response"}]}
            ]
        }))
        
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Question"},
                {"role": "bot", "content": "On it."}
            ]
        }
        
        messages, errors = extract_kiro_messages_enriched(chat_data, workspace_dir=tmp_path)
        
        assert len(messages) == 2
        assert messages[1].content == "Full response"

    def test_extraction_without_workspace(self):
        """Test extraction without workspace uses original content."""
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Question"},
                {"role": "bot", "content": "Brief response"}
            ]
        }
        
        messages, errors = extract_kiro_messages_enriched(chat_data, workspace_dir=None)
        
        assert len(messages) == 2
        assert messages[1].content == "Brief response"

    def test_skips_empty_content_after_enrichment(self, tmp_path):
        """Test that messages with empty content after normalization are skipped."""
        chat_data = {
            "chat": [
                {"role": "human", "content": "Question"},
                {"role": "bot", "content": ""}  # Empty content
            ]
        }
        
        messages, errors = extract_kiro_messages_enriched(chat_data, workspace_dir=tmp_path)
        
        # Empty bot message should be skipped
        assert len(messages) == 1
        assert messages[0].role == "human"

    def test_uses_prebuilt_index(self, tmp_path):
        """Test that prebuilt index is used for faster lookups."""
        # Create execution log
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Indexed response"}]}
            ]
        }))
        
        # Build index
        index = {"exec-001": log_file}
        
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "bot", "content": "Brief"}
            ]
        }
        
        messages, errors = extract_kiro_messages_enriched(
            chat_data, 
            workspace_dir=tmp_path,
            execution_log_index=index
        )
        
        assert len(messages) == 1
        assert messages[0].content == "Indexed response"


    def test_strict_mode_skips_on_mismatch(self, tmp_path):
        """Test that strict mode skips enrichment when counts don't match."""
        # Create execution log with 1 bot response
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Only one"}]}
            ]
        }))
        
        # Chat has 2 bot messages
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Q1"},
                {"role": "bot", "content": "Brief 1"},
                {"role": "human", "content": "Q2"},
                {"role": "bot", "content": "Brief 2"}
            ]
        }
        
        # With strict=True, should skip enrichment entirely
        enriched, errors = enrich_chat_with_execution_log(
            chat_data, tmp_path, strict=True
        )
        
        # Should have error about strict mode
        assert any("strict mode" in e.lower() for e in errors)
        # Original content should be preserved (not enriched)
        assert enriched["chat"][1]["content"] == "Brief 1"
        assert enriched["chat"][3]["content"] == "Brief 2"

    def test_execution_id_mismatch_skips_enrichment(self, tmp_path):
        """Test that executionId mismatch in log file skips enrichment."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        # Log file has different executionId
        log_file.write_text(json.dumps({
            "executionId": "different-id",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Response"}]}
            ]
        }))
        
        chat_data = {
            "executionId": "exec-001",
            "chat": [{"role": "bot", "content": "Brief"}]
        }
        
        # Build index pointing to the mismatched file
        index = {"exec-001": log_file}
        
        enriched, errors = enrich_chat_with_execution_log(
            chat_data, tmp_path, execution_log_index=index
        )
        
        # Should have mismatch error
        assert any("mismatch" in e.lower() for e in errors)
        # Original content preserved
        assert enriched["chat"][0]["content"] == "Brief"

    def test_extra_responses_in_log_ignored(self, tmp_path):
        """Test that extra bot responses in execution log are ignored."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        # Log has 3 bot responses
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Response 1"}]},
                {"role": "bot", "entries": [{"type": "text", "text": "Response 2"}]},
                {"role": "bot", "entries": [{"type": "text", "text": "Response 3"}]}
            ]
        }))
        
        # Chat has only 2 bot messages
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Q1"},
                {"role": "bot", "content": "Brief 1"},
                {"role": "human", "content": "Q2"},
                {"role": "bot", "content": "Brief 2"}
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        # Should have mismatch warning
        assert any("mismatch" in e.lower() for e in errors)
        # Both bot messages should be enriched
        assert enriched["chat"][1]["content"] == "Response 1"
        assert enriched["chat"][3]["content"] == "Response 2"
        # Third response is ignored (no corresponding chat message)



class TestValidateEnrichment:
    """Tests for _validate_enrichment function."""

    def test_empty_original_always_valid(self):
        """Test that empty original content is always valid to replace."""
        from src.kiro_parser import _validate_enrichment
        
        assert _validate_enrichment("", "Full response here") is True
        assert _validate_enrichment("   ", "Full response here") is True
        assert _validate_enrichment(None, "Full response here") is True

    def test_brief_acknowledgments_valid(self):
        """Test that common brief acknowledgments are valid to replace."""
        from src.kiro_parser import _validate_enrichment
        
        assert _validate_enrichment("On it.", "I'll help you with that...") is True
        assert _validate_enrichment("I'll help with that", "Full detailed response") is True
        assert _validate_enrichment("Let me check", "Full response") is True
        assert _validate_enrichment("Sure, I can help", "Full response") is True
        assert _validate_enrichment("Looking at the code", "Full response") is True

    def test_short_content_valid(self):
        """Test that short content (< 100 chars) is valid to replace."""
        from src.kiro_parser import _validate_enrichment
        
        short_content = "This is a short message"
        assert _validate_enrichment(short_content, "Full detailed response") is True

    def test_original_in_full_response_valid(self):
        """Test that original content appearing in full response is valid."""
        from src.kiro_parser import _validate_enrichment
        
        original = "I'll analyze the code for you"
        full = "I'll analyze the code for you. Here's what I found..."
        assert _validate_enrichment(original, full) is True

    def test_matching_start_words_valid(self):
        """Test that matching start words indicate valid enrichment."""
        from src.kiro_parser import _validate_enrichment
        
        original = "The function appears to have a bug in the loop"
        full = "The function appears to have several issues. Let me explain..."
        assert _validate_enrichment(original, full) is True

    def test_long_mismatched_content_invalid(self):
        """Test that long mismatched content is flagged as invalid."""
        from src.kiro_parser import _validate_enrichment
        
        # Long original that doesn't match the full response
        original = "x" * 150  # > 100 chars, doesn't match any pattern
        full = "Completely different response about something else entirely"
        assert _validate_enrichment(original, full) is False


class TestEnrichmentWithValidation:
    """Tests for enrichment with content validation."""

    def test_validation_prevents_mismatched_enrichment(self, tmp_path):
        """Test that validation prevents obviously wrong enrichments."""
        # Create execution log
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Response about Python"}]}
            ]
        }))
        
        # Chat has a long, specific message that doesn't match
        long_original = "This is a very long and specific message about JavaScript " * 5
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Question"},
                {"role": "bot", "content": long_original}
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        # Should have validation error
        assert any("validation failed" in e.lower() for e in errors)
        # Original content should be preserved (not replaced with mismatched response)
        assert long_original in enriched["chat"][1]["content"]

    def test_brief_acknowledgment_enriched_successfully(self, tmp_path):
        """Test that brief acknowledgments are enriched without validation errors."""
        hash_dir = tmp_path / "hash123"
        hash_dir.mkdir()
        log_file = hash_dir / "exec-001"
        log_file.write_text(json.dumps({
            "executionId": "exec-001",
            "messagesFromExecutionId": [
                {"role": "bot", "entries": [{"type": "text", "text": "Here's the full detailed response"}]}
            ]
        }))
        
        chat_data = {
            "executionId": "exec-001",
            "chat": [
                {"role": "human", "content": "Help me"},
                {"role": "bot", "content": "On it."}  # Brief acknowledgment
            ]
        }
        
        enriched, errors = enrich_chat_with_execution_log(chat_data, tmp_path)
        
        # Should not have validation errors
        assert not any("validation failed" in e.lower() for e in errors)
        # Should be enriched
        assert enriched["chat"][1]["content"] == "Here's the full detailed response"

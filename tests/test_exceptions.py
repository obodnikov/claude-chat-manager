"""Tests for custom exceptions."""

import pytest
from src.exceptions import (
    ClaudeReaderError,
    ProjectNotFoundError,
    ChatFileNotFoundError,
    InvalidJSONLError,
    ConfigurationError,
    ExportError
)


class TestExceptions:
    """Tests for custom exception classes."""

    def test_claude_reader_error(self):
        """Test ClaudeReaderError exception."""
        error = ClaudeReaderError("Test error")
        assert error.message == "Test error"
        assert str(error) == "Test error"

    def test_project_not_found_error(self):
        """Test ProjectNotFoundError exception."""
        error = ProjectNotFoundError("Project not found")
        assert error.message == "Project not found"
        assert isinstance(error, ClaudeReaderError)

    def test_chat_file_not_found_error(self):
        """Test ChatFileNotFoundError exception."""
        error = ChatFileNotFoundError("File not found")
        assert error.message == "File not found"
        assert isinstance(error, ClaudeReaderError)

    def test_invalid_jsonl_error(self):
        """Test InvalidJSONLError exception."""
        error = InvalidJSONLError("Invalid JSON")
        assert error.message == "Invalid JSON"
        assert isinstance(error, ClaudeReaderError)

    def test_configuration_error(self):
        """Test ConfigurationError exception."""
        error = ConfigurationError("Config error")
        assert error.message == "Config error"
        assert isinstance(error, ClaudeReaderError)

    def test_export_error(self):
        """Test ExportError exception."""
        error = ExportError("Export failed")
        assert error.message == "Export failed"
        assert isinstance(error, ClaudeReaderError)

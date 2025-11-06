"""Tests for wiki generator module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from src.wiki_generator import WikiGenerator


class TestWikiGenerator:
    """Test cases for WikiGenerator class."""

    def test_initialization_without_llm(self):
        """Test wiki generator initialization without LLM client."""
        wiki_gen = WikiGenerator()
        assert wiki_gen.llm_client is None

    def test_initialization_with_llm(self):
        """Test wiki generator initialization with LLM client."""
        mock_client = Mock()
        wiki_gen = WikiGenerator(llm_client=mock_client)
        assert wiki_gen.llm_client == mock_client

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_fallback_title_from_user_question(self, mock_parse):
        """Test fallback title generation uses first user question."""
        mock_parse.return_value = [
            {
                'message': {
                    'role': 'user',
                    'content': 'How do I add custom exception handling?'
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator()
        mock_file = Mock()
        mock_file.stem = "test-chat-id"

        title = wiki_gen._generate_fallback_title(mock_parse.return_value, mock_file)

        assert "How do I add custom exception handling" in title or "exception handling" in title.lower()

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_extract_chat_date(self, mock_parse):
        """Test chat date extraction from timestamp."""
        wiki_gen = WikiGenerator()

        chat_data = [
            {
                'message': {'role': 'user', 'content': 'Test'},
                'timestamp': 1609459200  # 2021-01-01 00:00:00 UTC
            }
        ]

        date_str = wiki_gen._extract_chat_date(chat_data)

        # Should contain year 2021
        assert '2021' in date_str

    def test_extract_clean_content_string(self):
        """Test extracting clean content from string."""
        wiki_gen = WikiGenerator()

        content = "This is a test message"
        clean_text, files = wiki_gen._extract_clean_content(content)

        assert clean_text == "This is a test message"
        assert files == []

    def test_extract_clean_content_with_code_block(self):
        """Test extracting content with code blocks preserved."""
        wiki_gen = WikiGenerator()

        content = [
            {'type': 'text', 'text': 'Here is the code:'},
            {'type': 'text', 'text': '```python\ndef test():\n    pass\n```'}
        ]

        clean_text, files = wiki_gen._extract_clean_content(content)

        assert 'Here is the code:' in clean_text
        assert '```python' in clean_text
        assert 'def test():' in clean_text

    def test_extract_clean_content_filters_tool_use(self):
        """Test that tool_use messages are filtered out."""
        wiki_gen = WikiGenerator()

        content = [
            {'type': 'text', 'text': 'Let me check the file'},
            {'type': 'tool_use', 'name': 'Read', 'input': {'file': 'test.py'}}
        ]

        clean_text, files = wiki_gen._extract_clean_content(content)

        assert 'Let me check the file' in clean_text
        assert 'tool_use' not in clean_text.lower()
        assert 'Read' not in clean_text or 'reading' in clean_text.lower()

    def test_extract_clean_content_filters_tool_result(self):
        """Test that tool_result messages are filtered out."""
        wiki_gen = WikiGenerator()

        content = [
            {'type': 'tool_result', 'content': 'File contents here'}
        ]

        clean_text, files = wiki_gen._extract_clean_content(content)

        # Tool results should be filtered out
        assert 'tool_result' not in clean_text.lower()

    def test_extract_clean_content_preserves_file_references(self):
        """Test that file references from tool_use are extracted."""
        wiki_gen = WikiGenerator()

        content = [
            {'type': 'text', 'text': 'I updated the config file'},
            {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'src/config.py'}}
        ]

        clean_text, files = wiki_gen._extract_clean_content(content)

        assert 'I updated the config file' in clean_text
        assert 'src/config.py' in files

    def test_extract_text_only(self):
        """Test extracting text without file references."""
        wiki_gen = WikiGenerator()

        content = [
            {'type': 'text', 'text': 'This is a test message'},
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'test.py'}}
        ]

        text = wiki_gen._extract_text_only(content)
        assert 'This is a test message' in text

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_chat_content(self, mock_parse):
        """Test chat content generation."""
        mock_parse.return_value = [
            {
                'message': {
                    'role': 'user',
                    'content': 'What is the best way to add tests?'
                },
                'timestamp': 1234567890
            },
            {
                'message': {
                    'role': 'assistant',
                    'content': 'You should use pytest for testing.'
                },
                'timestamp': 1234567891
            }
        ]

        wiki_gen = WikiGenerator()
        content = wiki_gen._generate_chat_content(mock_parse.return_value)

        assert 'What is the best way to add tests?' in content
        assert 'pytest' in content

    def test_create_anchor(self):
        """Test anchor creation from title."""
        wiki_gen = WikiGenerator()

        anchor = wiki_gen._create_anchor(1, "Adding Test Suite")
        assert anchor == "1-adding-test-suite"

        anchor2 = wiki_gen._create_anchor(2, "Custom Exception Handling!")
        assert anchor2 == "2-custom-exception-handling"

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_build_wiki_document(self, mock_parse):
        """Test complete wiki document building."""
        wiki_gen = WikiGenerator()

        chat_sections = [
            {
                'title': 'Test Chat',
                'date': '2024-01-01',
                'chat_id': 'abc12345',
                'content': '> User question\n\nAssistant response',
                'timestamp': 1234567890
            }
        ]

        wiki = wiki_gen._build_wiki_document('Test Project', chat_sections)

        assert 'Project Wiki: Test Project' in wiki
        assert 'Test Chat' in wiki
        assert '2024-01-01' in wiki
        assert 'User question' in wiki
        assert 'Assistant response' in wiki
        # Should have table of contents
        assert 'Table of Contents' in wiki or 'Contents' in wiki

    @patch('src.wiki_generator.parse_jsonl_file')
    @patch('src.wiki_generator.OpenRouterClient')
    def test_generate_wiki_with_llm(self, mock_client_class, mock_parse):
        """Test wiki generation with LLM-powered titles."""
        # Setup mock LLM client
        mock_client = Mock()
        mock_client.generate_chat_title.return_value = "Setting Up Testing Infrastructure"

        # Setup mock chat data
        mock_parse.return_value = [
            {
                'message': {
                    'role': 'user',
                    'content': 'How do I add pytest?'
                },
                'timestamp': 1234567890
            },
            {
                'message': {
                    'role': 'assistant',
                    'content': 'Install pytest with pip install pytest'
                },
                'timestamp': 1234567891
            }
        ]

        # Create wiki generator with mock client
        wiki_gen = WikiGenerator(llm_client=mock_client)

        # Create mock file
        mock_file = Mock()
        mock_file.stem = "abc12345-test-chat"
        mock_file.name = "abc12345-test-chat.jsonl"

        # Generate wiki
        wiki, stats = wiki_gen.generate_wiki(
            chat_files=[mock_file],
            project_name="Test Project",
            use_llm_titles=True
        )

        # Verify LLM was called
        assert mock_client.generate_chat_title.called

        # Verify wiki contains LLM-generated title
        assert "Setting Up Testing Infrastructure" in wiki

        # Verify stats
        assert stats.total_chats == 1
        assert stats.titles_generated == 1

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_wiki_without_llm(self, mock_parse):
        """Test wiki generation with fallback titles."""
        # Setup mock chat data
        mock_parse.return_value = [
            {
                'message': {
                    'role': 'user',
                    'content': 'How do I add pytest?'
                },
                'timestamp': 1234567890
            },
            {
                'message': {
                    'role': 'assistant',
                    'content': 'Install pytest with pip'
                },
                'timestamp': 1234567891
            }
        ]

        # Create wiki generator without LLM
        wiki_gen = WikiGenerator(llm_client=None)

        # Create mock file
        mock_file = Mock()
        mock_file.stem = "abc12345-test-chat"
        mock_file.name = "abc12345-test-chat.jsonl"

        # Generate wiki
        wiki, stats = wiki_gen.generate_wiki(
            chat_files=[mock_file],
            project_name="Test Project",
            use_llm_titles=False
        )

        # Verify wiki contains project name and content
        assert "Project Wiki: Test Project" in wiki
        assert "pytest" in wiki.lower()

        # Verify stats
        assert stats.total_chats == 1

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_wiki_sorts_chronologically(self, mock_parse):
        """Test that wiki chats are sorted chronologically."""
        # Setup mock chat data with different timestamps
        def parse_side_effect(file_path):
            if 'older' in str(file_path):
                return [{'message': {'role': 'user', 'content': 'Older chat'}, 'timestamp': 1000}]
            else:
                return [{'message': {'role': 'user', 'content': 'Newer chat'}, 'timestamp': 2000}]

        mock_parse.side_effect = parse_side_effect

        wiki_gen = WikiGenerator(llm_client=None)

        # Create mock files
        older_file = Mock()
        older_file.stem = "older-chat"
        older_file.name = "older-chat.jsonl"

        newer_file = Mock()
        newer_file.stem = "newer-chat"
        newer_file.name = "newer-chat.jsonl"

        # Generate wiki (pass newer first to test sorting)
        wiki, stats = wiki_gen.generate_wiki(
            chat_files=[newer_file, older_file],
            project_name="Test Project",
            use_llm_titles=False
        )

        # Find positions of content in wiki
        older_pos = wiki.find('Older chat')
        newer_pos = wiki.find('Newer chat')

        # Older should come before newer
        assert older_pos < newer_pos

    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_wiki_handles_empty_files(self, mock_parse):
        """Test that empty chat files are skipped."""
        mock_parse.return_value = []

        wiki_gen = WikiGenerator(llm_client=None)

        mock_file = Mock()
        mock_file.stem = "empty-chat"
        mock_file.name = "empty-chat.jsonl"

        # Should not raise an error
        wiki, stats = wiki_gen.generate_wiki(
            chat_files=[mock_file],
            project_name="Test Project",
            use_llm_titles=False
        )

        # Wiki should still be generated but with no chat sections
        assert "Project Wiki: Test Project" in wiki
        assert "Total Chats:** 0" in wiki

        # Verify stats
        assert stats.total_chats == 0

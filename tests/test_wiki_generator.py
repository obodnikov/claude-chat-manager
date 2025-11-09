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
        content, user_questions = wiki_gen._generate_chat_content(mock_parse.return_value, 1)

        assert 'What is the best way to add tests?' in content
        assert 'pytest' in content
        assert len(user_questions) == 1
        assert 'What is the best way to add tests?' in user_questions[0]

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

        # Chat sections now need chat_data instead of content
        chat_sections = [
            {
                'title': 'Test Chat',
                'date': '2024-01-01',
                'chat_id': 'abc12345',
                'chat_data': [
                    {
                        'message': {
                            'role': 'user',
                            'content': 'User question'
                        },
                        'timestamp': 1234567890
                    },
                    {
                        'message': {
                            'role': 'assistant',
                            'content': 'Assistant response'
                        },
                        'timestamp': 1234567891
                    }
                ],
                'timestamp': 1234567890
            }
        ]

        wiki = wiki_gen._build_wiki_document('Test Project', chat_sections)

        assert 'Project Wiki: Test Project' in wiki
        assert 'Test Chat' in wiki
        assert '2024-01-01' in wiki
        assert 'User question' in wiki
        assert 'Assistant response' in wiki
        # Should have hierarchical table of contents
        assert 'Table of Contents' in wiki or 'Contents' in wiki
        # Should have user marker
        assert '👤 **USER:**' in wiki

    @patch('src.wiki_generator.config')
    @patch('src.wiki_generator.parse_jsonl_file')
    @patch('src.wiki_generator.OpenRouterClient')
    def test_generate_wiki_with_llm(self, mock_client_class, mock_parse, mock_config):
        """Test wiki generation with LLM-powered titles."""
        # Disable filtering for this test
        mock_config.wiki_skip_trivial = False

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

    @patch('src.wiki_generator.config')
    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_wiki_without_llm(self, mock_parse, mock_config):
        """Test wiki generation with fallback titles."""
        # Disable filtering for this test
        mock_config.wiki_skip_trivial = False

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

    @patch('src.wiki_generator.config')
    @patch('src.wiki_generator.parse_jsonl_file')
    def test_generate_wiki_sorts_chronologically(self, mock_parse, mock_config):
        """Test that wiki chats are sorted chronologically."""
        # Disable filtering for this test
        mock_config.wiki_skip_trivial = False

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

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_disabled_filtering(self, mock_config):
        """Test that filtering can be disabled."""
        mock_config.wiki_skip_trivial = False

        wiki_gen = WikiGenerator()

        # Even a very short chat should not be filtered if disabled
        chat_data = [
            {'message': {'role': 'user', 'content': 'hi'}, 'timestamp': 1000}
        ]

        assert not wiki_gen._is_pointless_chat(chat_data)

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_too_few_messages(self, mock_config):
        """Test filtering based on message count."""
        mock_config.wiki_skip_trivial = True
        mock_config.wiki_min_messages = 3
        mock_config.wiki_min_words = 0  # Disable word count check
        mock_config.wiki_skip_keywords = []
        mock_config.wiki_require_content = False

        wiki_gen = WikiGenerator()

        # Chat with only 2 messages (less than minimum)
        chat_data = [
            {'message': {'role': 'user', 'content': 'Hello there'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': 'Hi!'}, 'timestamp': 1001}
        ]

        assert wiki_gen._is_pointless_chat(chat_data)

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_too_few_words(self, mock_config):
        """Test filtering based on word count."""
        mock_config.wiki_skip_trivial = True
        mock_config.wiki_min_messages = 1
        mock_config.wiki_min_words = 50
        mock_config.wiki_skip_keywords = []
        mock_config.wiki_require_content = False

        wiki_gen = WikiGenerator()

        # Chat with few messages but also few words
        chat_data = [
            {'message': {'role': 'user', 'content': 'Hi'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': 'Hello'}, 'timestamp': 1001},
            {'message': {'role': 'user', 'content': 'Ready?'}, 'timestamp': 1002}
        ]

        assert wiki_gen._is_pointless_chat(chat_data)

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_keyword_detection(self, mock_config):
        """Test filtering based on keywords in first message."""
        mock_config.wiki_skip_trivial = True
        mock_config.wiki_min_messages = 1
        mock_config.wiki_min_words = 0
        mock_config.wiki_skip_keywords = ['warmup', 'test', 'hello']
        mock_config.wiki_require_content = False

        wiki_gen = WikiGenerator()

        # Chat starting with warmup keyword
        chat_data = [
            {'message': {'role': 'user', 'content': 'warmup'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': 'Ready to help!'}, 'timestamp': 1001}
        ]

        assert wiki_gen._is_pointless_chat(chat_data)

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_passes_filters(self, mock_config):
        """Test that substantial chat passes all filters."""
        mock_config.wiki_skip_trivial = True
        mock_config.wiki_min_messages = 3
        mock_config.wiki_min_words = 50  # Set lower to accommodate test data (has 73 words)
        mock_config.wiki_skip_keywords = ['warmup', 'test']
        mock_config.wiki_require_content = False

        wiki_gen = WikiGenerator()

        # Substantial chat with enough messages and words
        chat_data = [
            {'message': {'role': 'user', 'content': 'How do I implement a custom exception handler in Python? I need detailed steps and examples.'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': 'To implement a custom exception handler, you need to create a class that inherits from Exception. Here is a detailed example with multiple approaches and best practices.'}, 'timestamp': 1001},
            {'message': {'role': 'user', 'content': 'That helps, can you show me how to use it with decorators?'}, 'timestamp': 1002},
            {'message': {'role': 'assistant', 'content': 'Certainly! Here is how you can use decorators with custom exceptions to handle errors gracefully in your application.'}, 'timestamp': 1003}
        ]

        assert not wiki_gen._is_pointless_chat(chat_data)

    @patch('src.wiki_generator.config')
    def test_is_pointless_chat_require_content(self, mock_config):
        """Test content requirement filtering."""
        mock_config.wiki_skip_trivial = True
        mock_config.wiki_min_messages = 1
        mock_config.wiki_min_words = 0
        mock_config.wiki_skip_keywords = []
        mock_config.wiki_require_content = True

        wiki_gen = WikiGenerator()

        # Chat without code blocks or file references
        chat_data = [
            {'message': {'role': 'user', 'content': 'What do you think about this idea?'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': 'It sounds interesting but needs more detail.'}, 'timestamp': 1001}
        ]

        assert wiki_gen._is_pointless_chat(chat_data)

        # Chat with code block should pass
        chat_data_with_code = [
            {'message': {'role': 'user', 'content': 'Can you help me with this?'}, 'timestamp': 1000},
            {'message': {'role': 'assistant', 'content': [
                {'type': 'text', 'text': 'Sure, here is the code:'},
                {'type': 'text', 'text': '```python\ndef test():\n    pass\n```'}
            ]}, 'timestamp': 1001}
        ]

        assert not wiki_gen._is_pointless_chat(chat_data_with_code)

    # Note: Integration test for filtering is challenging to mock properly
    # The unit tests above (test_is_pointless_chat_*) thoroughly test the filtering logic
    # Manual/integration testing should be used to verify end-to-end filtering works

    def test_strip_system_tags_ide_opened_file(self):
        """Test stripping IDE opened file tags."""
        wiki_gen = WikiGenerator()

        text = "<ide_opened_file>The user opened file.py</ide_opened_file>\n\nActual user question here"
        cleaned = wiki_gen._strip_system_tags(text)

        assert "<ide_opened_file>" not in cleaned
        assert "Actual user question here" in cleaned
        assert "The user opened file.py" not in cleaned

    def test_strip_system_tags_system_reminder(self):
        """Test stripping system reminder tags."""
        wiki_gen = WikiGenerator()

        text = "My question\n\n<system-reminder>Note: This is a reminder</system-reminder>"
        cleaned = wiki_gen._strip_system_tags(text)

        assert "<system-reminder>" not in cleaned
        assert "My question" in cleaned
        assert "This is a reminder" not in cleaned

    def test_strip_system_tags_multiple(self):
        """Test stripping multiple system tags."""
        wiki_gen = WikiGenerator()

        text = "<ide_opened_file>Opened file</ide_opened_file>\n\nReal question\n\n<system-reminder>Reminder</system-reminder>"
        cleaned = wiki_gen._strip_system_tags(text)

        assert cleaned == "Real question"
        assert "<ide_opened_file>" not in cleaned
        assert "<system-reminder>" not in cleaned

    def test_clean_user_message_pure_system(self):
        """Test that pure system messages return None."""
        wiki_gen = WikiGenerator()

        text = "<ide_opened_file>The user opened the file /path/to/file.py in the IDE.</ide_opened_file>"
        cleaned = wiki_gen._clean_user_message(text)

        assert cleaned is None

    def test_clean_user_message_mixed_content(self):
        """Test that mixed content returns cleaned text."""
        wiki_gen = WikiGenerator()

        text = "<ide_opened_file>Opened file</ide_opened_file>\n\nHow do I fix this bug?"
        cleaned = wiki_gen._clean_user_message(text)

        assert cleaned == "How do I fix this bug?"
        assert "<ide_opened_file>" not in cleaned

    def test_clean_user_message_no_system_tags(self):
        """Test that text without system tags is returned as-is."""
        wiki_gen = WikiGenerator()

        text = "This is a normal user question"
        cleaned = wiki_gen._clean_user_message(text)

        assert cleaned == text

    @patch('src.wiki_generator.config')
    def test_clean_user_message_filtering_disabled(self, mock_config):
        """Test that filtering can be disabled."""
        mock_config.wiki_filter_system_tags = False

        wiki_gen = WikiGenerator()

        text = "<ide_opened_file>Opened file</ide_opened_file>\n\nQuestion"
        cleaned = wiki_gen._clean_user_message(text)

        # Should return original text when filtering is disabled
        assert cleaned == text
        assert "<ide_opened_file>" in cleaned

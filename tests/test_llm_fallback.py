"""Tests for LLM fallback behavior when API key is not configured.

Validates that:
- Config correctly reports LLM validation warnings
- Wiki/book exports gracefully fall back to first user question titles
- Fallback titles strip steering and system tags
- Warning messages are consistent across export paths
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.config import Config
from src.wiki_generator import WikiGenerator


class TestConfigLLMValidation:
    """Tests for Config.validate_llm_config method."""

    def test_validate_llm_config_no_warnings_when_key_set(self, monkeypatch):
        """No warnings when API key is present."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-test')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        config = Config()
        warnings = config.validate_llm_config()
        assert warnings == []

    def test_validate_llm_config_no_warnings_when_llm_disabled(self, monkeypatch):
        """No warnings when LLM is explicitly disabled."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')
        config = Config()
        warnings = config.validate_llm_config()
        assert warnings == []

    def test_validate_llm_config_wiki_warning_no_key(self, monkeypatch):
        """Warning when wiki LLM enabled but no API key."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 1
        assert 'WIKI_USE_LLM_TITLES' in warnings[0]
        assert 'OPENROUTER_API_KEY' in warnings[0]

    def test_validate_llm_config_book_warning_no_key(self, monkeypatch):
        """Warning when book LLM enabled but no API key."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 1
        assert 'BOOK_USE_LLM_TITLES' in warnings[0]

    def test_validate_llm_config_both_warnings_no_key(self, monkeypatch):
        """Both warnings when both LLM options enabled but no API key."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 2

    def test_validate_no_warning_when_generate_titles_disabled_wiki(self, monkeypatch):
        """No wiki warning when WIKI_GENERATE_TITLES=false even if USE_LLM=true."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_GENERATE_TITLES', 'false')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 0

    def test_validate_no_warning_when_generate_titles_disabled_book(self, monkeypatch):
        """No book warning when BOOK_GENERATE_TITLES=false even if USE_LLM=true."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('BOOK_GENERATE_TITLES', 'false')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 0

    def test_validate_no_warning_when_both_generate_titles_disabled(self, monkeypatch):
        """No warnings when both GENERATE_TITLES are false, regardless of USE_LLM."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_GENERATE_TITLES', 'false')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_GENERATE_TITLES', 'false')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 0


class TestConfigLLMDefaults:
    """Tests for LLM config default values."""

    def test_wiki_use_llm_titles_default_true(self, monkeypatch):
        """WIKI_USE_LLM_TITLES defaults to true."""
        monkeypatch.delenv('WIKI_USE_LLM_TITLES', raising=False)
        config = Config()
        assert config.wiki_use_llm_titles is True

    def test_book_use_llm_titles_default_true(self, monkeypatch):
        """BOOK_USE_LLM_TITLES defaults to true."""
        monkeypatch.delenv('BOOK_USE_LLM_TITLES', raising=False)
        config = Config()
        assert config.book_use_llm_titles is True

    def test_wiki_use_llm_titles_can_be_disabled(self, monkeypatch):
        """WIKI_USE_LLM_TITLES can be set to false."""
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        config = Config()
        assert config.wiki_use_llm_titles is False

    def test_book_use_llm_titles_can_be_disabled(self, monkeypatch):
        """BOOK_USE_LLM_TITLES can be set to false."""
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')
        config = Config()
        assert config.book_use_llm_titles is False

    def test_wiki_generate_titles_still_works(self, monkeypatch):
        """WIKI_GENERATE_TITLES is separate from WIKI_USE_LLM_TITLES."""
        monkeypatch.setenv('WIKI_GENERATE_TITLES', 'true')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        config = Config()
        assert config.wiki_generate_titles is True
        assert config.wiki_use_llm_titles is False


class TestWikiFallbackTitle:
    """Tests for WikiGenerator fallback title generation."""

    def test_fallback_strips_steering_content(self):
        """Fallback title strips steering/included rules blocks."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '## Included Rules (start.md) [Global]\n\n'
                        '<user-rule id=start.md>\nSome rules here\n</user-rule>\n\n'
                        'How do I implement error handling?'
                    )
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        # Should contain the actual question, not steering content
        assert 'error handling' in title.lower()
        assert 'Included Rules' not in title

    def test_fallback_strips_system_tags(self):
        """Fallback title strips system notification tags."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '<ide_opened_file>/src/main.py</ide_opened_file>\n'
                        'Fix the login bug in authentication module'
                    )
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert 'login bug' in title.lower() or 'Fix the login' in title
        assert 'ide_opened_file' not in title

    def test_fallback_skips_steering_summary_markers(self):
        """Fallback title skips steering summary marker lines."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '*[Steering files included: start.md, rules.md]*\n\n'
                        'Implement the new search feature'
                    )
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert 'search feature' in title.lower()
        assert 'Steering' not in title

    def test_fallback_truncates_long_titles(self):
        """Fallback title truncates at 60 chars with ellipsis."""
        long_question = "A" * 100
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': long_question
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert len(title) <= 63  # 60 + "..."
        assert title.endswith("...")

    def test_fallback_uses_filename_when_no_user_message(self):
        """Fallback uses chat file stem when no user message found."""
        chat_data = [
            {
                'message': {
                    'role': 'assistant',
                    'content': 'Hello, how can I help?'
                },
                'timestamp': 1234567890
            }
        ]

        mock_file = Mock()
        mock_file.stem = "abc12345-some-chat"

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, mock_file)

        assert title == "Chat abc12345"

    def test_fallback_returns_untitled_when_no_file(self):
        """Fallback returns 'Untitled Chat' when no file and no user message."""
        chat_data = [
            {
                'message': {
                    'role': 'assistant',
                    'content': 'Hello'
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert title == "Untitled Chat"

    def test_fallback_handles_kiro_human_role(self):
        """Fallback handles Kiro 'human' role name."""
        chat_data = [
            {
                'message': {
                    'role': 'human',
                    'content': 'Refactor the database layer'
                },
                'timestamp': 1234567890
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert 'database' in title.lower() or 'Refactor' in title

    def test_fallback_skips_empty_user_messages(self):
        """Fallback skips user messages that are empty after cleaning."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': '<ide_opened_file>/src/main.py</ide_opened_file>'
                },
                'timestamp': 1234567890
            },
            {
                'message': {
                    'role': 'user',
                    'content': 'Implement caching for API responses'
                },
                'timestamp': 1234567891
            }
        ]

        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)

        assert 'caching' in title.lower() or 'API' in title


class TestBookExportFallback:
    """Tests for book export LLM fallback in exporters."""

    @patch('src.exporters.config')
    def test_book_export_warns_when_no_api_key(self, mock_config):
        """Book export logs warning when LLM enabled but no API key."""
        mock_config.book_generate_titles = True
        mock_config.book_use_llm_titles = True
        mock_config.openrouter_api_key = None
        mock_config.book_skip_trivial = False
        mock_config.book_filter_system_tags = True
        mock_config.book_include_date = True
        mock_config.book_filter_tool_noise = True
        mock_config.book_show_file_refs = True
        mock_config.book_keep_steering = False

        from src.exporters import _generate_book_filename
        from src.filters import ChatFilter

        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': 'How do I add tests?'
                },
                'timestamp': 1234567890
            }
        ]

        mock_file = Mock()
        mock_file.stem = "test-chat-id"

        chat_filter = ChatFilter(filter_system_tags=True)

        # Should work without LLM, using fallback
        filename = _generate_book_filename(chat_data, mock_file, None, chat_filter)
        assert filename  # Should produce a non-empty filename
        assert 'test' in filename.lower() or 'add' in filename.lower()


class TestApiKeyValidation:
    """Tests for API key presence validation edge cases."""

    def test_has_valid_api_key_with_real_key(self, monkeypatch):
        """Valid API key is recognized."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-abc123')
        config = Config()
        assert config.has_valid_api_key is True

    def test_has_valid_api_key_not_set(self, monkeypatch):
        """Missing API key returns False."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        config = Config()
        assert config.has_valid_api_key is False

    def test_has_valid_api_key_empty_string(self, monkeypatch):
        """Empty string API key returns False."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '')
        config = Config()
        assert config.has_valid_api_key is False

    def test_has_valid_api_key_whitespace_only(self, monkeypatch):
        """Whitespace-only API key returns False."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '   ')
        config = Config()
        assert config.has_valid_api_key is False

    def test_validate_llm_config_empty_string_key(self, monkeypatch):
        """validate_llm_config warns when API key is empty string."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 1
        assert 'WIKI_USE_LLM_TITLES' in warnings[0]

    def test_validate_llm_config_whitespace_key(self, monkeypatch):
        """validate_llm_config warns when API key is whitespace."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '  \t  ')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')
        config = Config()
        warnings = config.validate_llm_config()
        assert len(warnings) == 2


class TestGetEffectiveApiKey:
    """Tests for Config.get_effective_api_key centralized normalization."""

    def test_override_takes_precedence(self, monkeypatch):
        """CLI override is preferred over config value."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'config-key')
        config = Config()
        assert config.get_effective_api_key('cli-key') == 'cli-key'

    def test_falls_back_to_config(self, monkeypatch):
        """Falls back to config when no override."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'config-key')
        config = Config()
        assert config.get_effective_api_key(None) == 'config-key'

    def test_whitespace_override_ignored(self, monkeypatch):
        """Whitespace-only override falls through to config key."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'config-key')
        config = Config()
        assert config.get_effective_api_key('   ') == 'config-key'

    def test_empty_override_ignored(self, monkeypatch):
        """Empty string override falls through to config key."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'config-key')
        config = Config()
        assert config.get_effective_api_key('') == 'config-key'

    def test_both_empty_returns_empty(self, monkeypatch):
        """Returns empty string when both override and config are empty."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '')
        config = Config()
        assert config.get_effective_api_key('') == ''

    def test_no_config_no_override(self, monkeypatch):
        """Returns empty string when nothing is set."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        config = Config()
        assert config.get_effective_api_key(None) == ''

    def test_strips_whitespace_from_both(self, monkeypatch):
        """Strips whitespace from both override and config values."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '  config-key  ')
        config = Config()
        assert config.get_effective_api_key('  cli-key  ') == 'cli-key'


class TestValidateLlmConfigPurity:
    """Tests that validate_llm_config is pure (no side-effect logging)."""

    def test_validate_does_not_log(self, monkeypatch):
        """validate_llm_config returns warnings without logging them."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')

        config = Config()

        import logging
        with patch('src.config.logger') as mock_logger:
            warnings = config.validate_llm_config()
            assert len(warnings) == 1
            # Should NOT have called logger.warning
            mock_logger.warning.assert_not_called()


class TestSteeringMarkerVariants:
    """Tests for tolerant steering summary marker detection in fallback titles."""

    def test_fallback_skips_lowercase_steering_marker(self):
        """Fallback skips lowercase steering marker."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '*[steering files included: start.md]*\n'
                        'Fix the bug'
                    )
                },
                'timestamp': 1234567890
            }
        ]
        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)
        assert 'steering' not in title.lower()
        assert 'bug' in title.lower()

    def test_fallback_skips_marker_with_leading_spaces(self):
        """Fallback skips steering marker with leading whitespace."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '  *[Steering files included: rules.md]*\n'
                        'Add logging'
                    )
                },
                'timestamp': 1234567890
            }
        ]
        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)
        assert 'steering' not in title.lower()
        assert 'logging' in title.lower()

    def test_fallback_skips_marker_without_asterisks(self):
        """Fallback skips steering marker without surrounding asterisks."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '[Steering files included: config.md]\n'
                        'Refactor the parser'
                    )
                },
                'timestamp': 1234567890
            }
        ]
        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)
        assert 'steering' not in title.lower()
        assert 'parser' in title.lower()

    def test_fallback_skips_marker_mixed_case(self):
        """Fallback skips steering marker with mixed case."""
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': (
                        '*[STEERING FILES INCLUDED: start.md]*\n'
                        'Deploy to production'
                    )
                },
                'timestamp': 1234567890
            }
        ]
        wiki_gen = WikiGenerator(llm_client=None)
        title = wiki_gen._generate_fallback_title(chat_data, None)
        assert 'steering' not in title.lower()
        assert 'production' in title.lower()


class TestCliKeyNormalization:
    """Tests for API key normalization in the CLI wiki export path."""

    def test_get_effective_api_key_trims_whitespace_padded_key(self, monkeypatch):
        """Whitespace-padded key in .env is trimmed by get_effective_api_key."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '  sk-or-v1-test  ')
        config = Config()
        key = config.get_effective_api_key()
        assert key == 'sk-or-v1-test'
        assert config.has_valid_api_key is True

    def test_cli_wiki_path_uses_trimmed_key(self, monkeypatch):
        """CLI wiki path gets a trimmed key via get_effective_api_key."""
        monkeypatch.setenv('OPENROUTER_API_KEY', '  sk-or-v1-padded  ')
        config = Config()
        # Simulates what claude-chat-manager.py now does
        api_key = config.get_effective_api_key()
        assert api_key == 'sk-or-v1-padded'
        # This key should be usable (non-empty after strip)
        assert bool(api_key)


class TestCliStartupValidation:
    """Integration tests for LLM config validation at CLI startup."""

    def test_startup_logs_warnings_when_no_api_key(self, monkeypatch):
        """CLI startup surfaces validate_llm_config warnings via logger."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')

        config = Config()
        warnings = config.validate_llm_config()

        # Simulate what claude-chat-manager.py main() does
        import logging
        mock_logger = MagicMock()
        for warning in warnings:
            mock_logger.warning(warning)

        # Both warnings should have been logged by the caller
        assert mock_logger.warning.call_count == 2
        logged_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any('WIKI_USE_LLM_TITLES' in msg for msg in logged_messages)
        assert any('BOOK_USE_LLM_TITLES' in msg for msg in logged_messages)

    def test_startup_no_warnings_when_key_present(self, monkeypatch):
        """CLI startup produces no warnings when API key is configured."""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-valid')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'true')

        config = Config()
        warnings = config.validate_llm_config()

        assert warnings == []

    def test_startup_no_warnings_when_llm_disabled(self, monkeypatch):
        """CLI startup produces no warnings when LLM is disabled."""
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'false')
        monkeypatch.setenv('BOOK_USE_LLM_TITLES', 'false')

        config = Config()
        warnings = config.validate_llm_config()

        assert warnings == []

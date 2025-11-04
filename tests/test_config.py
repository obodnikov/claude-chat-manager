"""Tests for config module."""

import pytest
import os
from pathlib import Path
from src.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_config_default_claude_dir(self):
        """Test default Claude projects directory."""
        config = Config()
        expected = Path.home() / '.claude' / 'projects'
        assert config.claude_projects_dir == expected

    def test_config_default_export_format(self):
        """Test default export format."""
        config = Config()
        assert config.default_export_format == 'pretty'

    def test_config_default_page_height(self):
        """Test default terminal page height."""
        config = Config()
        assert config.terminal_page_height == 24

    def test_config_default_log_level(self):
        """Test default log level."""
        config = Config()
        assert config.log_level == 'INFO'

    def test_config_custom_log_level(self, monkeypatch):
        """Test custom log level from environment."""
        monkeypatch.setenv('CLAUDE_LOG_LEVEL', 'DEBUG')
        config = Config()
        assert config.log_level == 'DEBUG'

    def test_config_invalid_page_height(self, monkeypatch):
        """Test invalid page height falls back to default."""
        monkeypatch.setenv('CLAUDE_PAGE_HEIGHT', 'invalid')
        config = Config()
        assert config.terminal_page_height == 24

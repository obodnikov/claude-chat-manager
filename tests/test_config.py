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


class TestKiroConfig:
    """Tests for Kiro-specific configuration."""

    def test_kiro_data_dir_default_windows(self, monkeypatch):
        """Test default Kiro directory on Windows."""
        monkeypatch.setattr('sys.platform', 'win32')
        monkeypatch.setenv('APPDATA', r'C:\Users\TestUser\AppData\Roaming')
        config = Config()
        expected = Path(r'C:\Users\TestUser\AppData\Roaming\Kiro\User\globalStorage\kiro.kiroagent')
        assert config.kiro_data_dir == expected

    def test_kiro_data_dir_windows_no_appdata(self, monkeypatch):
        """Test that missing APPDATA on Windows raises ValueError."""
        monkeypatch.setattr('sys.platform', 'win32')
        monkeypatch.delenv('APPDATA', raising=False)
        with pytest.raises(ValueError, match='APPDATA environment variable not set on Windows'):
            Config()

    def test_kiro_data_dir_default_macos(self, monkeypatch):
        """Test default Kiro directory on macOS."""
        monkeypatch.setattr('sys.platform', 'darwin')
        config = Config()
        expected = Path.home() / 'Library' / 'Application Support' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        assert config.kiro_data_dir == expected

    def test_kiro_data_dir_default_linux(self, monkeypatch):
        """Test default Kiro directory on Linux."""
        monkeypatch.setattr('sys.platform', 'linux')
        config = Config()
        expected = Path.home() / '.config' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        assert config.kiro_data_dir == expected

    def test_kiro_data_dir_custom_env(self, monkeypatch):
        """Test custom Kiro directory from environment variable."""
        custom_path = '/custom/kiro/path'
        monkeypatch.setenv('KIRO_DATA_DIR', custom_path)
        config = Config()
        assert config.kiro_data_dir == Path(custom_path)

    def test_chat_source_filter_default(self):
        """Test default chat source filter (claude)."""
        config = Config()
        from src.models import ChatSource
        assert config.chat_source_filter == ChatSource.CLAUDE_DESKTOP

    def test_chat_source_filter_claude(self, monkeypatch):
        """Test chat source filter set to claude."""
        monkeypatch.setenv('CHAT_SOURCE', 'claude')
        config = Config()
        from src.models import ChatSource
        assert config.chat_source_filter == ChatSource.CLAUDE_DESKTOP

    def test_chat_source_filter_kiro(self, monkeypatch):
        """Test chat source filter set to kiro."""
        monkeypatch.setenv('CHAT_SOURCE', 'kiro')
        config = Config()
        from src.models import ChatSource
        assert config.chat_source_filter == ChatSource.KIRO_IDE

    def test_chat_source_filter_all(self, monkeypatch):
        """Test chat source filter set to all (returns None)."""
        monkeypatch.setenv('CHAT_SOURCE', 'all')
        config = Config()
        assert config.chat_source_filter is None

    def test_chat_source_filter_invalid(self, monkeypatch):
        """Test invalid chat source filter falls back to claude."""
        monkeypatch.setenv('CHAT_SOURCE', 'invalid')
        config = Config()
        from src.models import ChatSource
        assert config.chat_source_filter == ChatSource.CLAUDE_DESKTOP

    def test_chat_source_filter_case_insensitive(self, monkeypatch):
        """Test chat source filter is case-insensitive."""
        monkeypatch.setenv('CHAT_SOURCE', 'KIRO')
        config = Config()
        from src.models import ChatSource
        assert config.chat_source_filter == ChatSource.KIRO_IDE

    def test_validate_kiro_directory_exists(self, tmp_path, monkeypatch):
        """Test validation succeeds when Kiro directory exists."""
        kiro_dir = tmp_path / 'kiro'
        kiro_dir.mkdir()
        monkeypatch.setenv('KIRO_DATA_DIR', str(kiro_dir))
        config = Config()
        assert config.validate_kiro_directory() is True

    def test_validate_kiro_directory_not_exists(self, tmp_path, monkeypatch):
        """Test validation fails when Kiro directory doesn't exist."""
        kiro_dir = tmp_path / 'nonexistent'
        monkeypatch.setenv('KIRO_DATA_DIR', str(kiro_dir))
        config = Config()
        assert config.validate_kiro_directory() is False

    def test_validate_kiro_directory_is_file(self, tmp_path, monkeypatch):
        """Test validation fails when Kiro path is a file, not directory."""
        kiro_file = tmp_path / 'kiro_file'
        kiro_file.touch()
        monkeypatch.setenv('KIRO_DATA_DIR', str(kiro_file))
        config = Config()
        assert config.validate_kiro_directory() is False

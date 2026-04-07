"""Unit tests for source auto-detection and selection flow.

Tests the detect_and_select_source() function and _detect_available_sources() helper
introduced when removing the default --source=claude behavior.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.models import ChatSource
from src.cli import detect_and_select_source, _detect_available_sources


class TestDetectAvailableSources:
    """Test _detect_available_sources() discovery logic."""

    def test_no_sources_available(self):
        """Returns empty list when no source directories exist."""
        with patch('src.cli.config') as mock_config:
            mock_config.claude_projects_dir = Path('/nonexistent/claude')
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            result = _detect_available_sources()
            assert result == []

    def test_only_claude_available(self, tmp_path):
        """Detects Claude Desktop when it has projects with JSONL files."""
        # Create a fake Claude project with a JSONL file
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / "chat.jsonl").write_text("{}")

        with patch('src.cli.config') as mock_config:
            mock_config.claude_projects_dir = tmp_path
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            result = _detect_available_sources()
            assert len(result) == 1
            assert result[0][0] == ChatSource.CLAUDE_DESKTOP
            assert result[0][1] == 1

    def test_only_kiro_available(self):
        """Detects Kiro IDE when it has workspaces."""
        mock_workspace = MagicMock()
        mock_workspace.workspace_name = "test-workspace"

        with patch('src.cli.config') as mock_config, \
             patch('src.cli.discover_kiro_workspaces', create=True) as mock_discover:
            mock_config.claude_projects_dir = Path('/nonexistent/claude')
            mock_config.validate_kiro_directory.return_value = True
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_codex_directory.return_value = False

            # Patch the import inside the function
            with patch.dict('sys.modules', {}):
                with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace], create=True):
                    # Need to patch at the point of import inside _detect_available_sources
                    import src.kiro_projects
                    with patch.object(src.kiro_projects, 'discover_kiro_workspaces', return_value=[mock_workspace]):
                        result = _detect_available_sources()
                        assert len(result) == 1
                        assert result[0][0] == ChatSource.KIRO_IDE
                        assert result[0][1] == 1

    def test_claude_dir_exists_but_no_projects(self, tmp_path):
        """Claude dir exists but has no project subdirectories with JSONL files."""
        # Empty directory — no projects
        with patch('src.cli.config') as mock_config:
            mock_config.claude_projects_dir = tmp_path
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            result = _detect_available_sources()
            assert result == []

    def test_multiple_claude_projects(self, tmp_path):
        """Counts multiple Claude projects correctly."""
        for name in ["project-a", "project-b", "project-c"]:
            d = tmp_path / name
            d.mkdir()
            (d / "chat.jsonl").write_text("{}")

        with patch('src.cli.config') as mock_config:
            mock_config.claude_projects_dir = tmp_path
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            result = _detect_available_sources()
            assert len(result) == 1
            assert result[0][0] == ChatSource.CLAUDE_DESKTOP
            assert result[0][1] == 3

    def test_exception_during_scan_is_logged_not_raised(self, tmp_path):
        """Exceptions during source scanning are logged, not propagated."""
        with patch('src.cli.config') as mock_config:
            # Make claude_projects_dir.exists() return True but iterdir() raise
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.iterdir.side_effect = PermissionError("access denied")
            mock_config.claude_projects_dir = mock_dir
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            # Should not raise
            result = _detect_available_sources()
            assert result == []


class TestDetectAndSelectSource:
    """Test detect_and_select_source() interactive menu."""

    def test_no_sources_returns_false(self):
        """Returns False when no sources are found."""
        with patch('src.cli._detect_available_sources', return_value=[]):
            result = detect_and_select_source()
            assert result is False

    def test_single_source_auto_selects(self):
        """Auto-selects when only one source is available."""
        with patch('src.cli._detect_available_sources', return_value=[(ChatSource.KIRO_IDE, 3)]):
            result = detect_and_select_source()
            assert result == ChatSource.KIRO_IDE

    def test_multiple_sources_user_picks_first(self):
        """User selects first source from menu."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='1'):
            result = detect_and_select_source()
            assert result == ChatSource.CLAUDE_DESKTOP

    def test_multiple_sources_user_picks_second(self):
        """User selects second source from menu."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='2'):
            result = detect_and_select_source()
            assert result == ChatSource.KIRO_IDE

    def test_multiple_sources_user_picks_all(self):
        """User selects 'All sources' option."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='3'):
            result = detect_and_select_source()
            assert result is None

    def test_user_quits(self):
        """Returns False when user types 'q'."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='q'):
            result = detect_and_select_source()
            assert result is False

    def test_keyboard_interrupt_returns_false(self):
        """Returns False on KeyboardInterrupt."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5)]
        # Single source auto-selects, so use multiple
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', side_effect=KeyboardInterrupt):
            result = detect_and_select_source()
            assert result is False

    def test_invalid_then_valid_choice(self):
        """Retries on invalid input, then accepts valid choice."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', side_effect=['99', '1']):
            result = detect_and_select_source()
            assert result == ChatSource.CLAUDE_DESKTOP


class TestCLISourceArgNone:
    """Test that --source=None (omitted) triggers auto-detect in main()."""

    @staticmethod
    def _import_main():
        """Import claude-chat-manager.py (hyphenated filename)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("claude_chat_manager", "claude-chat-manager.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_source_no_project_triggers_detection(self):
        """Running with no args triggers detect_and_select_source."""
        with patch('sys.argv', ['claude-chat-manager.py']), \
             patch('src.cli.detect_and_select_source', return_value=False) as mock_detect:
            cm = self._import_main()
            with pytest.raises(SystemExit):
                cm.main()
            mock_detect.assert_called_once()

    def test_explicit_source_skips_detection(self):
        """Running with --source claude skips detect_and_select_source."""
        with patch('sys.argv', ['claude-chat-manager.py', '--source', 'claude', '-l']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_projects_list'):
            cm = self._import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()

    def test_no_source_with_project_searches_all(self):
        """Running with project name but no --source searches all sources."""
        with patch('sys.argv', ['claude-chat-manager.py', 'my-project']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.projects.find_project_by_name', return_value=None), \
             patch('src.cli.display_projects_list'):
            cm = self._import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            # Should NOT call detect — it should search all sources directly
            mock_detect.assert_not_called()

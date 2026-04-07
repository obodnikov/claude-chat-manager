"""Unit tests for source auto-detection and selection flow.

Tests the detect_and_select_source() function and _detect_available_sources() helper
introduced when removing the default --source=claude behavior.
"""

import importlib.util
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.models import ChatSource, SourceSelection
from src.cli import detect_and_select_source, _detect_available_sources


def _import_main():
    """Import claude-chat-manager.py (hyphenated filename)."""
    spec = importlib.util.spec_from_file_location("claude_chat_manager", "claude-chat-manager.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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

        with patch('src.cli.config') as mock_config:
            mock_config.claude_projects_dir = Path('/nonexistent/claude')
            mock_config.validate_kiro_directory.return_value = True
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_codex_directory.return_value = False

            import src.kiro_projects
            with patch.object(src.kiro_projects, 'discover_kiro_workspaces', return_value=[mock_workspace]):
                result = _detect_available_sources()
                assert len(result) == 1
                assert result[0][0] == ChatSource.KIRO_IDE
                assert result[0][1] == 1

    def test_claude_dir_exists_but_no_projects(self, tmp_path):
        """Claude dir exists but has no project subdirectories with JSONL files."""
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

    def test_permission_error_is_logged_not_raised(self, tmp_path):
        """OSError during source scanning is logged, not propagated."""
        with patch('src.cli.config') as mock_config:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.iterdir.side_effect = PermissionError("access denied")
            mock_config.claude_projects_dir = mock_dir
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            result = _detect_available_sources()
            assert result == []

    def test_unexpected_type_error_propagates(self, tmp_path):
        """TypeError (programming error) is NOT caught — it propagates."""
        with patch('src.cli.config') as mock_config:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.iterdir.side_effect = TypeError("bad code")
            mock_config.claude_projects_dir = mock_dir
            mock_config.validate_kiro_directory.return_value = False
            mock_config.validate_codex_directory.return_value = False

            with pytest.raises(TypeError):
                _detect_available_sources()


class TestDetectAndSelectSource:
    """Test detect_and_select_source() returns SourceSelection."""

    def test_no_sources_returns_quit(self):
        """Returns SourceSelection(quit=True) when no sources found."""
        with patch('src.cli._detect_available_sources', return_value=[]):
            result = detect_and_select_source()
            assert isinstance(result, SourceSelection)
            assert result.quit is True

    def test_single_source_auto_selects(self):
        """Auto-selects when only one source is available."""
        with patch('src.cli._detect_available_sources', return_value=[(ChatSource.KIRO_IDE, 3)]):
            result = detect_and_select_source()
            assert isinstance(result, SourceSelection)
            assert result.source == ChatSource.KIRO_IDE
            assert result.quit is False

    def test_multiple_sources_user_picks_first(self):
        """User selects first source from menu."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='1'):
            result = detect_and_select_source()
            assert result.source == ChatSource.CLAUDE_DESKTOP
            assert result.quit is False

    def test_multiple_sources_user_picks_second(self):
        """User selects second source from menu."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='2'):
            result = detect_and_select_source()
            assert result.source == ChatSource.KIRO_IDE

    def test_multiple_sources_user_picks_all(self):
        """User selects 'All sources' — source is None, quit is False."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='3'):
            result = detect_and_select_source()
            assert result.source is None
            assert result.quit is False

    def test_user_quits(self):
        """Returns quit=True when user types 'q'."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', return_value='q'):
            result = detect_and_select_source()
            assert result.quit is True

    def test_keyboard_interrupt_returns_quit(self):
        """Returns quit=True on KeyboardInterrupt."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', side_effect=KeyboardInterrupt):
            result = detect_and_select_source()
            assert result.quit is True

    def test_eof_returns_quit(self):
        """Returns quit=True on EOFError (piped stdin / non-interactive)."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', side_effect=EOFError):
            result = detect_and_select_source()
            assert result.quit is True

    def test_invalid_then_valid_choice(self):
        """Retries on invalid input, then accepts valid choice."""
        sources = [(ChatSource.CLAUDE_DESKTOP, 5), (ChatSource.KIRO_IDE, 3)]
        with patch('src.cli._detect_available_sources', return_value=sources), \
             patch('builtins.input', side_effect=['99', '1']):
            result = detect_and_select_source()
            assert result.source == ChatSource.CLAUDE_DESKTOP


class TestCLISourceArgNone:
    """Test --source omitted triggers correct precedence in main()."""

    def test_no_source_no_project_triggers_detection(self):
        """Running with no args triggers detect_and_select_source."""
        with patch('sys.argv', ['claude-chat-manager.py']), \
             patch('src.cli.detect_and_select_source', return_value=SourceSelection(quit=True)) as mock_detect:
            cm = _import_main()
            with pytest.raises(SystemExit):
                cm.main()
            mock_detect.assert_called_once()

    def test_explicit_source_skips_detection(self):
        """Running with --source claude skips detect_and_select_source."""
        with patch('sys.argv', ['claude-chat-manager.py', '--source', 'claude', '-l']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_projects_list'):
            cm = _import_main()
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
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()


class TestChatSourceEnvPrecedence:
    """Test CHAT_SOURCE env is honored when --source is not provided."""

    def test_env_kiro_used_for_list_command(self, monkeypatch):
        """CHAT_SOURCE=kiro is used when running -l without --source."""
        monkeypatch.setenv('CHAT_SOURCE', 'kiro')
        with patch('sys.argv', ['claude-chat-manager.py', '-l']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_projects_list') as mock_list:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            # Should NOT show interactive menu
            mock_detect.assert_not_called()
            # Should pass Kiro filter
            mock_list.assert_called_once_with(ChatSource.KIRO_IDE)

    def test_env_all_used_for_search_command(self, monkeypatch):
        """CHAT_SOURCE=all is used when running -s without --source."""
        monkeypatch.setenv('CHAT_SOURCE', 'all')
        with patch('sys.argv', ['claude-chat-manager.py', '-s', 'test']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_search_results') as mock_search:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            # CHAT_SOURCE=all → config returns None → source_filter=None
            mock_search.assert_called_once_with('test', None)

    def test_cli_source_overrides_env(self, monkeypatch):
        """--source claude overrides CHAT_SOURCE=kiro."""
        monkeypatch.setenv('CHAT_SOURCE', 'kiro')
        with patch('sys.argv', ['claude-chat-manager.py', '--source', 'claude', '-l']), \
             patch('src.cli.display_projects_list') as mock_list:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_list.assert_called_once_with(ChatSource.CLAUDE_DESKTOP)

    def test_env_codex_used_for_interactive_mode(self, monkeypatch):
        """CHAT_SOURCE=codex skips detection menu in interactive mode."""
        monkeypatch.setenv('CHAT_SOURCE', 'codex')
        with patch('sys.argv', ['claude-chat-manager.py']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.interactive_browser') as mock_browser:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_browser.assert_called_once_with(ChatSource.CODEX)


class TestNonInteractiveCommandsSkipMenu:
    """Non-interactive commands (-l, -s, -r, -c) should not prompt when no env is set."""

    def test_list_without_source_defaults_to_all(self):
        """Running -l without --source or CHAT_SOURCE uses all sources (no menu)."""
        with patch('sys.argv', ['claude-chat-manager.py', '-l']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_projects_list') as mock_list:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_list.assert_called_once_with(None)

    def test_search_without_source_defaults_to_all(self):
        """Running -s without --source or CHAT_SOURCE uses all sources (no menu)."""
        with patch('sys.argv', ['claude-chat-manager.py', '-s', 'docker']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_search_results') as mock_search:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_search.assert_called_once_with('docker', None)

    def test_recent_without_source_defaults_to_all(self):
        """Running -r without --source or CHAT_SOURCE uses all sources (no menu)."""
        with patch('sys.argv', ['claude-chat-manager.py', '-r', '5']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_recent_projects') as mock_recent:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_recent.assert_called_once_with(5, None)

    def test_content_search_without_source_defaults_to_all(self):
        """Running -c without --source or CHAT_SOURCE uses all sources (no menu)."""
        with patch('sys.argv', ['claude-chat-manager.py', '-c', 'auth']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_content_search') as mock_content:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_content.assert_called_once_with('auth', None)


class TestMainLogsLlmWarnings:
    """Test that main() actually logs warnings from validate_llm_config()."""

    def test_llm_warnings_are_logged(self, monkeypatch):
        """main() calls logger.warning for each validate_llm_config() warning."""
        monkeypatch.setenv('WIKI_GENERATE_TITLES', 'true')
        monkeypatch.setenv('WIKI_USE_LLM_TITLES', 'true')
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)

        mock_logger = MagicMock()
        real_get_logger = logging.getLogger

        def patched_get_logger(name=None):
            # Intercept the logger created inside main()
            if name == 'claude_chat_manager':
                return mock_logger
            return real_get_logger(name)

        with patch('sys.argv', ['claude-chat-manager.py', '--source', 'claude', '-l']), \
             patch('src.cli.display_projects_list'), \
             patch('logging.getLogger', side_effect=patched_get_logger):
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            warning_calls = [
                call for call in mock_logger.warning.call_args_list
                if 'LLM_TITLES' in str(call) or 'OPENROUTER_API_KEY' in str(call)
            ]
            assert len(warning_calls) >= 1, (
                f"Expected LLM config warning to be logged, got: {mock_logger.warning.call_args_list}"
            )


class TestChatSourceAllEnvSkipsMenu:
    """Regression: CHAT_SOURCE=all must skip the detection menu."""

    def test_env_all_skips_menu_in_interactive_mode(self, monkeypatch):
        """CHAT_SOURCE=all in interactive mode uses all sources without prompting."""
        monkeypatch.setenv('CHAT_SOURCE', 'all')
        with patch('sys.argv', ['claude-chat-manager.py']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.interactive_browser') as mock_browser:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            # source_filter should be None (all sources)
            mock_browser.assert_called_once_with(None)

    def test_env_all_skips_menu_for_list(self, monkeypatch):
        """CHAT_SOURCE=all with -l uses all sources without prompting."""
        monkeypatch.setenv('CHAT_SOURCE', 'all')
        with patch('sys.argv', ['claude-chat-manager.py', '-l']), \
             patch('src.cli.detect_and_select_source') as mock_detect, \
             patch('src.cli.display_projects_list') as mock_list:
            cm = _import_main()
            try:
                cm.main()
            except SystemExit:
                pass
            mock_detect.assert_not_called()
            mock_list.assert_called_once_with(None)

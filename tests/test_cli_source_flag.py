"""Unit tests for CLI source flag functionality.

Tests the --source flag integration with project listing and filtering.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.models import ChatSource, ProjectInfo
from src.projects import list_all_projects, search_projects_by_name, get_recent_projects
from src.exceptions import ProjectNotFoundError


class TestSourceFiltering:
    """Test source filtering in project listing functions."""

    def test_list_all_projects_default_claude_only(self):
        """Test default behavior lists Claude Desktop projects only.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            # Setup mock config
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            # Create mock Claude directory with projects
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir') as mock_iterdir, \
                 patch('pathlib.Path.glob', return_value=[Path('test.jsonl')]), \
                 patch('src.projects.count_messages_in_file', return_value=10):
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'test-project'
                mock_project_dir.is_dir.return_value = True
                mock_project_dir.glob.return_value = [Path('test.jsonl')]
                mock_iterdir.return_value = [mock_project_dir]
                
                # Call with default (Claude only)
                projects = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                
                # Should return Claude projects
                assert len(projects) > 0
                assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in projects)

    def test_list_all_projects_kiro_only(self):
        """Test --source kiro lists only Kiro IDE projects.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            # Setup mock config
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Mock Kiro workspace discovery
            mock_workspace = Mock()
            mock_workspace.workspace_name = 'kiro-workspace'
            mock_workspace.workspace_path = '/path/to/workspace'
            mock_workspace.session_count = 5
            mock_workspace.last_modified = '2025-01-15 10:00'
            mock_workspace.sessions = [Mock(session_id='session1')]
            
            with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]), \
                 patch('pathlib.Path.exists', return_value=False):
                
                # Call with Kiro filter
                projects = list_all_projects(ChatSource.KIRO_IDE)
                
                # Should return only Kiro projects
                assert len(projects) > 0
                assert all(p.source == ChatSource.KIRO_IDE for p in projects)

    def test_list_all_projects_all_sources(self):
        """Test --source all lists both Claude and Kiro projects.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            # Setup mock config
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Mock Claude projects
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir') as mock_iterdir, \
                 patch('pathlib.Path.glob', return_value=[Path('test.jsonl')]), \
                 patch('src.projects.count_messages_in_file', return_value=10):
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'claude-project'
                mock_project_dir.is_dir.return_value = True
                mock_project_dir.glob.return_value = [Path('test.jsonl')]
                mock_iterdir.return_value = [mock_project_dir]
                
                # Mock Kiro workspace discovery
                mock_workspace = Mock()
                mock_workspace.workspace_name = 'kiro-workspace'
                mock_workspace.workspace_path = '/path/to/workspace'
                mock_workspace.session_count = 5
                mock_workspace.last_modified = '2025-01-15 10:00'
                mock_workspace.sessions = [Mock(session_id='session1')]
                
                with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]):
                    # Call with no filter (all sources)
                    projects = list_all_projects(None)
                    
                    # Should return both Claude and Kiro projects
                    assert len(projects) >= 2
                    claude_projects = [p for p in projects if p.source == ChatSource.CLAUDE_DESKTOP]
                    kiro_projects = [p for p in projects if p.source == ChatSource.KIRO_IDE]
                    assert len(claude_projects) > 0
                    assert len(kiro_projects) > 0

    def test_search_projects_respects_source_filter(self):
        """Test search respects source filter.
        
        Validates: Requirements 3.3, 3.5
        """
        # Create mock projects from different sources
        claude_project = ProjectInfo(
            name='claude-test-project',
            path=Path('/mock/claude/project'),
            file_count=5,
            total_messages=100,
            last_modified='2025-01-15',
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        kiro_project = ProjectInfo(
            name='kiro-test-project',
            path=Path('/mock/kiro/project'),
            file_count=3,
            total_messages=50,
            last_modified='2025-01-15',
            source=ChatSource.KIRO_IDE
        )
        
        with patch('src.projects.list_all_projects') as mock_list:
            # Test Claude filter
            mock_list.return_value = [claude_project]
            results = search_projects_by_name('test', ChatSource.CLAUDE_DESKTOP)
            assert len(results) == 1
            assert results[0].source == ChatSource.CLAUDE_DESKTOP
            
            # Test Kiro filter
            mock_list.return_value = [kiro_project]
            results = search_projects_by_name('test', ChatSource.KIRO_IDE)
            assert len(results) == 1
            assert results[0].source == ChatSource.KIRO_IDE
            
            # Test all sources
            mock_list.return_value = [claude_project, kiro_project]
            results = search_projects_by_name('test', None)
            assert len(results) == 2

    def test_get_recent_projects_respects_source_filter(self):
        """Test recent projects respects source filter.
        
        Validates: Requirements 3.3, 3.5
        """
        # Create mock projects with timestamps
        claude_project = ProjectInfo(
            name='claude-recent',
            path=Path('/mock/claude/recent'),
            file_count=5,
            total_messages=100,
            last_modified='2025-01-15 10:00',
            sort_timestamp=1736935200.0,
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        kiro_project = ProjectInfo(
            name='kiro-recent',
            path=Path('/mock/kiro/recent'),
            file_count=3,
            total_messages=50,
            last_modified='2025-01-15 11:00',
            sort_timestamp=1736938800.0,
            source=ChatSource.KIRO_IDE
        )
        
        with patch('src.projects.list_all_projects') as mock_list:
            # Test Claude filter
            mock_list.return_value = [claude_project]
            results = get_recent_projects(10, ChatSource.CLAUDE_DESKTOP)
            assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in results)
            
            # Test Kiro filter
            mock_list.return_value = [kiro_project]
            results = get_recent_projects(10, ChatSource.KIRO_IDE)
            assert all(p.source == ChatSource.KIRO_IDE for p in results)
            
            # Test all sources
            mock_list.return_value = [claude_project, kiro_project]
            results = get_recent_projects(10, None)
            assert len(results) == 2


class TestSourceIndicators:
    """Test source indicators in project display."""

    def test_project_has_source_field(self):
        """Test that ProjectInfo includes source field.
        
        Validates: Requirements 3.2
        """
        project = ProjectInfo(
            name='test-project',
            path=Path('/mock/project'),
            file_count=5,
            total_messages=100,
            last_modified='2025-01-15',
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        assert hasattr(project, 'source')
        assert project.source == ChatSource.CLAUDE_DESKTOP

    def test_claude_project_has_correct_source(self):
        """Test Claude projects are marked with CLAUDE_DESKTOP source.
        
        Validates: Requirements 3.2
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir') as mock_iterdir, \
                 patch('pathlib.Path.glob', return_value=[Path('test.jsonl')]), \
                 patch('src.projects.count_messages_in_file', return_value=10):
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'test-project'
                mock_project_dir.is_dir.return_value = True
                mock_project_dir.glob.return_value = [Path('test.jsonl')]
                mock_iterdir.return_value = [mock_project_dir]
                
                projects = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                
                for project in projects:
                    assert project.source == ChatSource.CLAUDE_DESKTOP

    def test_kiro_project_has_correct_source(self):
        """Test Kiro projects are marked with KIRO_IDE source.
        
        Validates: Requirements 3.2
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            mock_workspace = Mock()
            mock_workspace.workspace_name = 'kiro-workspace'
            mock_workspace.workspace_path = '/path/to/workspace'
            mock_workspace.session_count = 5
            mock_workspace.last_modified = '2025-01-15 10:00'
            mock_workspace.sessions = [Mock(session_id='session1')]
            
            with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]), \
                 patch('pathlib.Path.exists', return_value=False):
                
                projects = list_all_projects(ChatSource.KIRO_IDE)
                
                for project in projects:
                    assert project.source == ChatSource.KIRO_IDE


class TestEdgeCases:
    """Test edge cases and error handling for source filtering."""

    def test_list_projects_with_no_claude_directory(self):
        """Test behavior when Claude directory doesn't exist.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/nonexistent/claude')
            mock_config.kiro_data_dir = Path('/nonexistent/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            with patch('pathlib.Path.exists', return_value=False):
                with pytest.raises(ProjectNotFoundError):
                    list_all_projects(ChatSource.CLAUDE_DESKTOP)

    def test_list_projects_with_no_kiro_directory(self):
        """Test behavior when Kiro directory doesn't exist.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/nonexistent/claude')
            mock_config.kiro_data_dir = Path('/nonexistent/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            with patch('pathlib.Path.exists', return_value=False):
                with pytest.raises(ProjectNotFoundError):
                    list_all_projects(ChatSource.KIRO_IDE)

    def test_list_projects_empty_results(self):
        """Test behavior when no projects are found.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir', return_value=[]):
                
                with pytest.raises(ProjectNotFoundError):
                    list_all_projects(ChatSource.CLAUDE_DESKTOP)

    def test_search_with_no_matches(self):
        """Test search when no projects match the term.
        
        Validates: Requirements 3.3, 3.5
        """
        claude_project = ProjectInfo(
            name='claude-project',
            path=Path('/mock/claude/project'),
            file_count=5,
            total_messages=100,
            last_modified='2025-01-15',
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        with patch('src.projects.list_all_projects', return_value=[claude_project]):
            results = search_projects_by_name('nonexistent', ChatSource.CLAUDE_DESKTOP)
            assert len(results) == 0

    def test_recent_projects_with_no_timestamps(self):
        """Test recent projects when projects have no timestamps.
        
        Validates: Requirements 3.3, 3.5
        """
        project_no_timestamp = ProjectInfo(
            name='no-timestamp',
            path=Path('/mock/project'),
            file_count=5,
            total_messages=100,
            last_modified='unknown',
            sort_timestamp=None,
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        with patch('src.projects.list_all_projects', return_value=[project_no_timestamp]):
            results = get_recent_projects(10, ChatSource.CLAUDE_DESKTOP)
            assert len(results) == 0  # Projects without timestamps are filtered out

    def test_mixed_source_filtering_consistency(self):
        """Test that filtering is consistent across different functions.
        
        Validates: Requirements 3.3, 3.5
        """
        claude_project = ProjectInfo(
            name='claude-test',
            path=Path('/mock/claude/test'),
            file_count=5,
            total_messages=100,
            last_modified='2025-01-15',
            sort_timestamp=1736935200.0,
            source=ChatSource.CLAUDE_DESKTOP
        )
        
        kiro_project = ProjectInfo(
            name='kiro-test',
            path=Path('/mock/kiro/test'),
            file_count=3,
            total_messages=50,
            last_modified='2025-01-15',
            sort_timestamp=1736935200.0,
            source=ChatSource.KIRO_IDE
        )
        
        all_projects = [claude_project, kiro_project]
        
        with patch('src.projects.list_all_projects') as mock_list:
            # Test consistency: Claude filter
            mock_list.return_value = [claude_project]
            search_results = search_projects_by_name('test', ChatSource.CLAUDE_DESKTOP)
            recent_results = get_recent_projects(10, ChatSource.CLAUDE_DESKTOP)
            
            assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in search_results)
            assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in recent_results)
            
            # Test consistency: Kiro filter
            mock_list.return_value = [kiro_project]
            search_results = search_projects_by_name('test', ChatSource.KIRO_IDE)
            recent_results = get_recent_projects(10, ChatSource.KIRO_IDE)
            
            assert all(p.source == ChatSource.KIRO_IDE for p in search_results)
            assert all(p.source == ChatSource.KIRO_IDE for p in recent_results)


class TestFindProjectByName:
    """Test find_project_by_name with source filtering."""

    def test_find_claude_project_by_name(self):
        """Test finding a Claude project by name.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir') as mock_iterdir, \
                 patch('pathlib.Path.glob', return_value=[]):
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'test-project'
                mock_project_dir.is_dir.return_value = True
                mock_project_dir.glob.return_value = []
                mock_iterdir.return_value = [mock_project_dir]
                
                from src.projects import find_project_by_name
                result = find_project_by_name('test-project', ChatSource.CLAUDE_DESKTOP)
                
                assert result is not None
                assert result.source == ChatSource.CLAUDE_DESKTOP
                assert result.path == mock_project_dir

    def test_find_kiro_project_by_name(self):
        """Test finding a Kiro project by name.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            mock_workspace = Mock()
            mock_workspace.workspace_name = 'kiro-workspace'
            mock_workspace.workspace_path = '/path/to/workspace'
            mock_workspace.session_count = 5
            mock_workspace.last_modified = '2025-01-15 10:00'
            mock_workspace.sessions = [Mock(session_id='session1')]
            mock_workspace.session_dir = Path('/mock/kiro/workspace-sessions/encoded')
            
            with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]):
                from src.projects import find_project_by_name
                result = find_project_by_name('kiro-workspace', ChatSource.KIRO_IDE)
                
                assert result is not None
                assert result.source == ChatSource.KIRO_IDE
                # path points to session_dir (where chat files live)
                assert result.path == mock_workspace.session_dir
                assert result.workspace_path == '/path/to/workspace'

    def test_find_project_not_found(self):
        """Test behavior when project is not found.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = False
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir', return_value=[]):
                
                from src.projects import find_project_by_name
                result = find_project_by_name('nonexistent', ChatSource.CLAUDE_DESKTOP)
                
                assert result is None

    def test_find_project_default_source_searches_all(self):
        """Test that default source filter (None) searches all sources.
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Setup Claude project
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir') as mock_iterdir, \
                 patch('pathlib.Path.glob', return_value=[]):
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'claude-project'
                mock_project_dir.is_dir.return_value = True
                mock_project_dir.glob.return_value = []
                mock_iterdir.return_value = [mock_project_dir]
                
                from src.projects import find_project_by_name
                # Call without source_filter - should search all sources (Claude first)
                result = find_project_by_name('claude-project')
                
                # Should find Claude project
                assert result is not None
                assert result.source == ChatSource.CLAUDE_DESKTOP
                assert result.path == mock_project_dir
    
    def test_find_project_searches_kiro_when_not_in_claude(self):
        """Test that when project not in Claude, it searches Kiro (when source is None).
        
        Validates: Requirements 3.1, 3.3
        """
        with patch('src.projects.config') as mock_config:
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Setup empty Claude directory
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir', return_value=[]):
                
                # Setup Kiro workspace
                mock_workspace = Mock()
                mock_workspace.workspace_name = 'kiro-only-project'
                mock_workspace.workspace_path = '/path/to/kiro/project'
                mock_workspace.session_count = 5
                mock_workspace.last_modified = '2025-01-15 10:00'
                mock_workspace.sessions = [Mock(session_id='session1')]
                mock_workspace.session_dir = Path('/mock/kiro/workspace-sessions/encoded')
                
                with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]):
                    from src.projects import find_project_by_name
                    # Call without source_filter - should search all sources
                    result = find_project_by_name('kiro-only-project')
                    
                    # Should find Kiro project
                    assert result is not None
                    assert result.source == ChatSource.KIRO_IDE
                    # path points to session_dir (where chat files live)
                    assert result.path == mock_workspace.session_dir
                    assert result.workspace_path == '/path/to/kiro/project'


# ============================================================================
# Step 7 — Cline VS Code --source flag tests
# ============================================================================

class TestClineVscodeSourceFlag:
    """Tests for --source cline-vscode and --source cline (alias) in the CLI.

    Mapping tests use the *production* parse_source_filter() function from
    src/cli_utils.py — the same function called by claude-chat-manager.py —
    so a regression in the real mapping will cause these tests to fail.

    All symbols used (Path, MagicMock, patch, ChatSource, pytest) are imported
    at module scope so this class can be moved independently without NameErrors.
    """

    # ── argparse acceptance ──────────────────────────────────────────────────

    def _build_parser(self):
        """Return a minimal argparse parser matching the --source argument in main()."""
        import argparse
        from src.cli_utils import SOURCE_CHOICES
        p = argparse.ArgumentParser()
        p.add_argument('--source', choices=list(SOURCE_CHOICES), default=None)
        return p

    def test_source_cline_vscode_accepted(self):
        """--source cline-vscode is a valid argparse choice."""
        args = self._build_parser().parse_args(['--source', 'cline-vscode'])
        assert args.source == 'cline-vscode'

    def test_source_cline_alias_accepted(self):
        """--source cline (alias) is a valid argparse choice."""
        args = self._build_parser().parse_args(['--source', 'cline'])
        assert args.source == 'cline'

    def test_source_cline_vscode_not_rejected(self):
        """--source cline-vscode does not raise SystemExit (invalid choice)."""
        try:
            self._build_parser().parse_args(['--source', 'cline-vscode'])
        except SystemExit:
            pytest.fail('--source cline-vscode raised SystemExit (invalid choice)')

    def test_source_cline_alias_not_rejected(self):
        """--source cline does not raise SystemExit (invalid choice)."""
        try:
            self._build_parser().parse_args(['--source', 'cline'])
        except SystemExit:
            pytest.fail('--source cline raised SystemExit (invalid choice)')

    # ── enum mapping — uses production parse_source_filter() ─────────────────

    def test_cline_vscode_maps_to_cline_vscode_enum(self):
        """parse_source_filter('cline-vscode') → ChatSource.CLINE_VSCODE."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('cline-vscode') == ChatSource.CLINE_VSCODE

    def test_cline_alias_maps_to_cline_vscode_enum(self):
        """parse_source_filter('cline') → ChatSource.CLINE_VSCODE."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('cline') == ChatSource.CLINE_VSCODE

    # ── regression: existing source values unchanged ─────────────────────────

    def test_claude_still_maps_to_claude_desktop(self):
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('claude') == ChatSource.CLAUDE_DESKTOP

    def test_kiro_still_maps_to_kiro_ide(self):
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('kiro') == ChatSource.KIRO_IDE

    def test_codex_still_maps_to_codex(self):
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('codex') == ChatSource.CODEX

    def test_all_still_maps_to_none(self):
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('all') is None

    def test_none_maps_to_none(self):
        """parse_source_filter(None) returns None (all sources / auto-detect)."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter(None) is None

    # ── CRITICAL regression guard: export_project_chats accepts source kwarg ─

    def test_export_project_chats_accepts_source_kwarg(self):
        """export_project_chats() must accept source= without raising TypeError.

        Uses signature inspection only — avoids coupling to filesystem layout,
        format behaviour, or exporter internals. An explicit 'source' param OR
        **kwargs means the CLI call source=project_info.source will not crash.
        """
        import inspect
        from src.exporters import export_project_chats

        sig = inspect.signature(export_project_chats)
        has_explicit_source = 'source' in sig.parameters
        has_var_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        assert has_explicit_source or has_var_kwargs, (
            "export_project_chats() has neither an explicit 'source' parameter "
            "nor **kwargs — calling it with source=... will raise TypeError."
        )

    # ── end-to-end: list_all_projects respects CLINE_VSCODE filter ───────────

    def test_list_all_projects_cline_vscode_filter(self):
        """list_all_projects(CLINE_VSCODE) returns only Cline VS Code projects.

        The config mock explicitly disables all other sources (Kiro, Codex, Claude)
        so MagicMock default truthiness cannot accidentally trigger them.
        Claude's directory is a non-existent path AND we patch Path.exists to
        return False for it, so the Claude enumeration branch is skipped reliably.
        """
        import json
        from tempfile import TemporaryDirectory
        from src.projects import list_all_projects

        with TemporaryDirectory() as tmpdir:
            cline_dir = Path(tmpdir)
            # Minimal globalStorage structure
            state_dir = cline_dir / "state"
            state_dir.mkdir()
            tasks_dir = cline_dir / "tasks"
            tasks_dir.mkdir()
            task_dir = tasks_dir / "1781697826685"
            task_dir.mkdir()
            (task_dir / "ui_messages.json").write_text(
                json.dumps([{"ts": 1_700_000_000_000, "type": "say",
                             "say": "task", "text": "Hello"}]),
                encoding="utf-8",
            )
            (state_dir / "taskHistory.json").write_text(
                json.dumps([{
                    "id": "1781697826685",
                    "ts": 1_700_000_000_000,
                    "task": "Hello",
                    "cwdOnTaskInitialization": "/home/user/proj",
                    "modelId": "claude-opus-4.6",
                }]),
                encoding="utf-8",
            )

            cfg_mock = MagicMock()
            # ── Cline: valid and pointing at our temp dir ──
            cfg_mock.cline_vscode_data_dir = cline_dir
            cfg_mock.validate_cline_vscode_directory.return_value = True
            # ── All other sources: ALL gating methods explicitly disabled ────
            # MagicMock defaults to truthy — pin each to False so no branch
            # can accidentally execute due to MagicMock default truthiness.
            cfg_mock.validate_kiro_directory.return_value = False
            cfg_mock.validate_codex_directory.return_value = False
            cfg_mock.validate_claude_directory.return_value = False
            # Claude projects_dir points at an existing but empty subdirectory
            # so the iterdir() loop produces nothing — no Path.exists patch needed.
            no_claude = cline_dir / "_empty_claude_dir"
            no_claude.mkdir()
            cfg_mock.claude_projects_dir = no_claude

            with patch('src.projects.config', cfg_mock):
                projects = list_all_projects(ChatSource.CLINE_VSCODE)

        assert len(projects) == 1
        assert projects[0].source == ChatSource.CLINE_VSCODE
        assert projects[0].name == "proj"

    # ── unknown value rejected loudly ────────────────────────────────────────

    def test_unknown_source_raises_value_error(self):
        """parse_source_filter raises ValueError for unrecognised non-None values."""
        from src.cli_utils import parse_source_filter
        with pytest.raises(ValueError, match="Unknown source value"):
            parse_source_filter('typo-source')

    # ── CHAT_SOURCE env var supports cline / cline-vscode ────────────────────

    def test_chat_source_env_cline_vscode(self, monkeypatch):
        """CHAT_SOURCE=cline-vscode is handled by config.chat_source_filter."""
        from src.config import Config
        monkeypatch.setenv('CHAT_SOURCE', 'cline-vscode')
        cfg = Config()
        assert cfg.chat_source_filter == ChatSource.CLINE_VSCODE

    def test_chat_source_env_cline_alias(self, monkeypatch):
        """CHAT_SOURCE=cline (alias) is handled by config.chat_source_filter."""
        from src.config import Config
        monkeypatch.setenv('CHAT_SOURCE', 'cline')
        cfg = Config()
        assert cfg.chat_source_filter == ChatSource.CLINE_VSCODE

    def test_chat_source_env_overrides_auto_detect(self, monkeypatch):
        """When CHAT_SOURCE=cline-vscode is set, is_chat_source_set returns True.

        This validates the documented precedence: CHAT_SOURCE env overrides
        auto-detect in claude-chat-manager.py's 'if not source_explicit' branch.
        """
        from src.config import Config
        monkeypatch.setenv('CHAT_SOURCE', 'cline-vscode')
        cfg = Config()
        assert cfg.is_chat_source_set is True
        assert cfg.chat_source_filter == ChatSource.CLINE_VSCODE

    def test_chat_source_env_not_set_returns_none(self, monkeypatch):
        """When CHAT_SOURCE is not set, chat_source_filter returns None (auto-detect)."""
        from src.config import Config
        monkeypatch.delenv('CHAT_SOURCE', raising=False)
        cfg = Config()
        assert cfg.is_chat_source_set is False
        assert cfg.chat_source_filter is None

    # ── parse_source_filter normalisation (MEDIUM: whitespace / empty) ───────

    def test_empty_string_treated_as_none(self):
        """parse_source_filter('') returns None (unset / all sources)."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('') is None

    def test_whitespace_only_treated_as_none(self):
        """parse_source_filter('  ') returns None (whitespace stripped → empty)."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('  ') is None

    def test_mixed_case_accepted(self):
        """parse_source_filter is case-insensitive for known values."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('CLINE-VSCODE') == ChatSource.CLINE_VSCODE
        assert parse_source_filter('Cline') == ChatSource.CLINE_VSCODE


class TestSourceLabelWidth:
    """Verify _source_label returns consistent fixed-width strings for all sources."""

    def test_all_labels_same_width(self):
        from src.cli import _source_label
        from src.models import ChatSource
        expected_width = 8  # "[Claude]" is 8 chars
        for source in ChatSource:
            if source == ChatSource.UNKNOWN:
                continue
            label = _source_label(source)
            assert len(label) == expected_width, (
                f"_source_label({source}) returned {label!r} (len={len(label)}), "
                f"expected width {expected_width}"
            )

    def test_pi_label_correct(self):
        from src.cli import _source_label
        from src.models import ChatSource
        assert _source_label(ChatSource.PI) == "[Pi]    "


class TestPiSourceFlag:
    """Tests for --source pi in the CLI and config."""

    def test_parse_source_filter_pi(self):
        """parse_source_filter('pi') returns ChatSource.PI."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('pi') == ChatSource.PI

    def test_parse_source_filter_pi_uppercase(self):
        """parse_source_filter is case-insensitive for 'pi'."""
        from src.cli_utils import parse_source_filter
        assert parse_source_filter('PI') == ChatSource.PI

    def test_pi_in_source_choices(self):
        """'pi' must be present in SOURCE_CHOICES and VALID_SOURCE_VALUES."""
        from src.cli_utils import SOURCE_CHOICES, VALID_SOURCE_VALUES
        assert 'pi' in SOURCE_CHOICES
        assert 'pi' in VALID_SOURCE_VALUES

    def test_argparse_accepts_pi(self):
        """--source pi is accepted as a valid argparse choice."""
        import argparse
        from src.cli_utils import SOURCE_CHOICES
        p = argparse.ArgumentParser()
        p.add_argument('--source', choices=list(SOURCE_CHOICES), default=None)
        args = p.parse_args(['--source', 'pi'])
        assert args.source == 'pi'

    def test_chat_source_env_pi(self, monkeypatch):
        """CHAT_SOURCE=pi is handled by config.chat_source_filter."""
        from src.config import Config
        monkeypatch.setenv('CHAT_SOURCE', 'pi')
        cfg = Config()
        assert cfg.chat_source_filter == ChatSource.PI


class TestPiExporterDetection:
    """Integration tests for Pi source detection and loading via exporters."""

    def _write_pi_session(self, path: Path, messages: list) -> None:
        """Write a minimal pi session JSONL file."""
        import json
        header = {
            "type": "session", "version": 3,
            "id": "test-uuid-exporter",
            "timestamp": "2026-06-28T10:00:00.000Z",
            "cwd": "/home/user/project",
        }
        with open(path, "w") as fh:
            fh.write(json.dumps(header) + "\n")
            for msg in messages:
                fh.write(json.dumps(msg) + "\n")

    def test_detect_chat_source_returns_pi(self, tmp_path):
        """_detect_chat_source identifies a pi session JSONL as ChatSource.PI."""
        from src.exporters import _detect_chat_source
        f = tmp_path / "session.jsonl"
        self._write_pi_session(f, [])
        assert _detect_chat_source(f) == ChatSource.PI

    def test_detect_chat_source_pi_without_cwd(self, tmp_path):
        """Pi detection works even when cwd is absent from the header."""
        import json
        from src.exporters import _detect_chat_source
        f = tmp_path / "no_cwd.jsonl"
        header = {"type": "session", "version": 3, "id": "uuid-no-cwd",
                  "timestamp": "2026-06-28T10:00:00.000Z"}
        f.write_text(json.dumps(header) + "\n")
        assert _detect_chat_source(f) == ChatSource.PI

    def test_detect_chat_source_pi_with_only_timestamp(self, tmp_path):
        """Pi detection works with only timestamp (no id/version/cwd)."""
        import json
        from src.exporters import _detect_chat_source
        f = tmp_path / "minimal.jsonl"
        header = {"type": "session", "timestamp": "2026-06-28T10:00:00.000Z"}
        f.write_text(json.dumps(header) + "\n")
        assert _detect_chat_source(f) == ChatSource.PI

    def test_load_chat_data_pi_session(self, tmp_path):
        """_load_chat_data loads a pi session and returns ChatSource.PI with messages."""
        from src.exporters import _load_chat_data
        f = tmp_path / "session.jsonl"
        self._write_pi_session(f, [
            {"type": "message", "id": "m1", "parentId": "root",
             "timestamp": "2026-06-28T10:00:01.000Z",
             "message": {"role": "user", "content": "Hello pi!"}},
            {"type": "message", "id": "m2", "parentId": "m1",
             "timestamp": "2026-06-28T10:00:02.000Z",
             "message": {"role": "assistant",
                          "content": [{"type": "text", "text": "Hi!"}]}},
        ])
        chat_data, source, errors = _load_chat_data(f)
        assert source == ChatSource.PI
        assert errors == []
        assert len(chat_data) == 2
        roles = [m["message"]["role"] for m in chat_data]
        assert roles == ["user", "assistant"]

    def test_codex_not_detected_as_pi(self, tmp_path):
        """A Codex rollout file (type=session_meta) is NOT detected as pi."""
        import json
        from src.exporters import _detect_chat_source
        f = tmp_path / "rollout.jsonl"
        f.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "x", "cwd": "/"}}) + "\n"
        )
        assert _detect_chat_source(f) == ChatSource.CODEX


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


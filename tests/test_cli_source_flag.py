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
                 patch('pathlib.Path.iterdir') as mock_iterdir:
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'test-project'
                mock_project_dir.is_dir.return_value = True
                mock_iterdir.return_value = [mock_project_dir]
                
                from src.projects import find_project_by_name
                result = find_project_by_name('test-project', ChatSource.CLAUDE_DESKTOP)
                
                assert result == mock_project_dir

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
            
            with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]):
                from src.projects import find_project_by_name
                result = find_project_by_name('kiro-workspace', ChatSource.KIRO_IDE)
                
                assert result == Path('/path/to/workspace')

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
                 patch('pathlib.Path.iterdir') as mock_iterdir:
                
                mock_project_dir = Mock(spec=Path)
                mock_project_dir.name = 'claude-project'
                mock_project_dir.is_dir.return_value = True
                mock_iterdir.return_value = [mock_project_dir]
                
                from src.projects import find_project_by_name
                # Call without source_filter - should search all sources (Claude first)
                result = find_project_by_name('claude-project')
                
                # Should find Claude project
                assert result == mock_project_dir
    
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
                
                with patch('src.kiro_projects.discover_kiro_workspaces', return_value=[mock_workspace]):
                    from src.projects import find_project_by_name
                    # Call without source_filter - should search all sources
                    result = find_project_by_name('kiro-only-project')
                    
                    # Should find Kiro project
                    assert result == Path('/path/to/kiro/project')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

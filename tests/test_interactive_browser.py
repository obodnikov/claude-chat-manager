"""Unit tests for interactive browser functionality.

Tests the interactive browser source filtering and search integration.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.models import ChatSource, ProjectInfo
from src.cli import interactive_browser, display_content_search
from src.search import search_chat_content


class TestInteractiveBrowserSourceFilter:
    """Test interactive browser source filtering."""

    def test_browser_shows_source_indicators(self):
        """Test that browser shows source indicators for projects.
        
        Validates: Requirements 6.1, 6.2
        """
        with patch('src.cli.list_all_projects') as mock_list, \
             patch('src.cli.input', side_effect=['q']), \
             patch('builtins.print') as mock_print:
            
            # Mock mixed source projects
            mock_projects = [
                ProjectInfo(
                    name='Claude Project',
                    path=Path('/mock/claude'),
                    file_count=5,
                    total_messages=100,
                    last_modified='2024-01-01',
                    source=ChatSource.CLAUDE_DESKTOP
                ),
                ProjectInfo(
                    name='Kiro Project',
                    path=Path('/mock/kiro'),
                    file_count=3,
                    total_messages=50,
                    last_modified='2024-01-02',
                    source=ChatSource.KIRO_IDE
                )
            ]
            mock_list.return_value = mock_projects
            
            # Test with all sources
            interactive_browser(None)
            
            # Check that source indicators were printed
            calls = [str(call) for call in mock_print.call_args_list]
            output = '\n'.join(calls)
            assert '[Claude]' in output or 'Claude' in output
            assert '[Kiro]' in output or 'Kiro' in output
    
    def test_browser_source_switching_option_available(self):
        """Test that browser offers source switching option.
        
        Validates: Requirements 6.2
        """
        with patch('src.cli.list_all_projects') as mock_list, \
             patch('src.cli.input', side_effect=['q']), \
             patch('builtins.print') as mock_print:
            
            # Mock at least one project so browser doesn't exit early
            mock_projects = [
                ProjectInfo(
                    name='Test Project',
                    path=Path('/mock/test'),
                    file_count=1,
                    total_messages=10,
                    last_modified='2024-01-01',
                    source=ChatSource.CLAUDE_DESKTOP
                )
            ]
            mock_list.return_value = mock_projects
            
            # Run browser
            interactive_browser(None)
            
            # Check that 's) Switch source filter' option was printed
            calls = [str(call) for call in mock_print.call_args_list]
            output = '\n'.join(calls)
            assert 'Switch source' in output or 's)' in output


class TestContentSearchKiroIntegration:
    """Test content search with Kiro integration."""

    def test_search_respects_source_filter(self):
        """Test that content search respects source filter.
        
        Validates: Requirements 6.4
        """
        with patch('src.search.config') as mock_config, \
             patch('src.kiro_projects.discover_kiro_workspaces') as mock_discover:
            
            # Setup mock config
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Mock Claude directory doesn't exist
            with patch('pathlib.Path.exists', return_value=False):
                
                # Search with Claude only filter
                results = search_chat_content('test', ChatSource.CLAUDE_DESKTOP)
                
                # Should NOT have called Kiro discovery
                mock_discover.assert_not_called()
    
    def test_search_calls_kiro_when_filter_allows(self):
        """Test that content search calls Kiro discovery when filter allows.
        
        Validates: Requirements 6.4
        """
        with patch('src.search.config') as mock_config, \
             patch('src.kiro_projects.discover_kiro_workspaces') as mock_discover:
            
            # Setup mock config
            mock_config.claude_projects_dir = Path('/mock/claude')
            mock_config.kiro_data_dir = Path('/mock/kiro')
            mock_config.validate_kiro_directory.return_value = True
            
            # Mock empty Kiro workspaces
            mock_discover.return_value = []
            
            # Mock Claude directory doesn't exist
            with patch('pathlib.Path.exists', return_value=False):
                
                # Search with all sources (None)
                results = search_chat_content('test', None)
                
                # Should have called Kiro discovery
                mock_discover.assert_called_once()

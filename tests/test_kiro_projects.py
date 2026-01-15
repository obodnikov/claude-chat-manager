"""Unit tests for Kiro projects discovery module."""

import base64
import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.kiro_projects import (
    KiroSession,
    KiroWorkspace,
    decode_workspace_path,
    list_kiro_sessions,
    discover_kiro_workspaces
)
from src.exceptions import ChatFileNotFoundError, InvalidChatFileError


class TestDecodeWorkspacePath:
    """Tests for decode_workspace_path function."""
    
    def test_decode_valid_path(self):
        """Test decoding a valid base64-encoded path."""
        original_path = "C:\\Users\\test\\workspace"
        encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
        # Remove padding for Kiro format
        encoded = encoded.rstrip('=')
        
        decoded = decode_workspace_path(encoded)
        assert decoded == original_path
    
    def test_decode_unix_path(self):
        """Test decoding a Unix-style path."""
        original_path = "/home/user/projects/myapp"
        encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
        encoded = encoded.rstrip('=')
        
        decoded = decode_workspace_path(encoded)
        assert decoded == original_path
    
    def test_decode_with_special_chars(self):
        """Test decoding paths with special characters."""
        original_path = "C:\\Users\\test\\my-project_v2"
        encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
        encoded = encoded.rstrip('=')
        
        decoded = decode_workspace_path(encoded)
        assert decoded == original_path
    
    def test_decode_invalid_base64(self):
        """Test that invalid base64 raises ValueError."""
        with pytest.raises(ValueError, match="Failed to decode"):
            decode_workspace_path("not-valid-base64!!!")


class TestListKiroSessions:
    """Tests for list_kiro_sessions function."""
    
    def test_list_sessions_valid(self):
        """Test listing sessions from valid sessions.json."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            # Create sessions.json
            sessions_data = [
                {
                    "sessionId": "session-1",
                    "title": "First Session",
                    "dateCreated": 1234567890000,
                    "workspaceDirectory": "C:\\workspace"
                },
                {
                    "sessionId": "session-2",
                    "title": "Second Session",
                    "dateCreated": 1234567891000,
                    "workspaceDirectory": "C:\\workspace"
                }
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            sessions = list_kiro_sessions(workspace_dir)
            
            assert len(sessions) == 2
            assert sessions[0].session_id == "session-1"
            assert sessions[0].title == "First Session"
            assert sessions[0].date_created == "1234567890000"
            assert sessions[0].workspace_directory == "C:\\workspace"
            assert sessions[0].chat_file_path == workspace_dir / "session-1.chat"
            
            assert sessions[1].session_id == "session-2"
            assert sessions[1].title == "Second Session"
    
    def test_list_sessions_missing_file(self):
        """Test that missing sessions.json raises ChatFileNotFoundError."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            with pytest.raises(ChatFileNotFoundError, match="sessions.json not found"):
                list_kiro_sessions(workspace_dir)
    
    def test_list_sessions_invalid_json(self):
        """Test that invalid JSON raises InvalidChatFileError."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                f.write("{ invalid json }")
            
            with pytest.raises(InvalidChatFileError, match="Invalid JSON"):
                list_kiro_sessions(workspace_dir)
    
    def test_list_sessions_not_array(self):
        """Test that non-array JSON raises InvalidChatFileError."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump({"not": "an array"}, f)
            
            with pytest.raises(InvalidChatFileError, match="must contain a JSON array"):
                list_kiro_sessions(workspace_dir)
    
    def test_list_sessions_empty_array(self):
        """Test listing sessions from empty array."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
            
            sessions = list_kiro_sessions(workspace_dir)
            assert len(sessions) == 0
    
    def test_list_sessions_missing_fields(self):
        """Test handling sessions with missing optional fields."""
        with TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_data = [
                {
                    "sessionId": "session-1"
                    # Missing title, dateCreated, workspaceDirectory
                }
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            sessions = list_kiro_sessions(workspace_dir)
            
            assert len(sessions) == 1
            assert sessions[0].session_id == "session-1"
            assert sessions[0].title == "Untitled"
            assert sessions[0].date_created == ""
            assert sessions[0].workspace_directory == ""


class TestDiscoverKiroWorkspaces:
    """Tests for discover_kiro_workspaces function."""
    
    def test_discover_workspaces_valid(self):
        """Test discovering workspaces from valid directory structure."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            # Create a workspace directory with encoded name
            original_path = "C:\\Users\\test\\workspace"
            encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
            encoded = encoded.rstrip('=')
            
            workspace_dir = workspace_sessions_dir / encoded
            workspace_dir.mkdir()
            
            # Create sessions.json
            sessions_data = [
                {
                    "sessionId": "session-1",
                    "title": "Test Session",
                    "dateCreated": 1234567890000,
                    "workspaceDirectory": original_path
                }
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            
            assert len(workspaces) == 1
            assert workspaces[0].workspace_path == original_path
            assert workspaces[0].workspace_name == "workspace"
            assert workspaces[0].session_count == 1
            assert len(workspaces[0].sessions) == 1
            assert workspaces[0].sessions[0].session_id == "session-1"
    
    def test_discover_workspaces_no_workspace_sessions_dir(self):
        """Test that missing workspace-sessions directory returns empty list."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            assert len(workspaces) == 0
    
    def test_discover_workspaces_empty_directory(self):
        """Test discovering from empty workspace-sessions directory."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            assert len(workspaces) == 0
    
    def test_discover_workspaces_invalid_base64(self):
        """Test handling workspace with invalid base64 name."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            # Create workspace with invalid base64 name
            workspace_dir = workspace_sessions_dir / 'invalid-base64-name'
            workspace_dir.mkdir()
            
            # Create sessions.json
            sessions_data = [
                {
                    "sessionId": "session-1",
                    "title": "Test Session",
                    "dateCreated": 1234567890000,
                    "workspaceDirectory": "C:\\workspace"
                }
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            
            # Should still discover workspace with fallback name
            assert len(workspaces) == 1
            assert workspaces[0].workspace_name == 'invalid-base64-name'
    
    def test_discover_workspaces_missing_sessions_json(self):
        """Test that workspaces without sessions.json are skipped."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            # Create workspace directory without sessions.json
            workspace_dir = workspace_sessions_dir / 'workspace1'
            workspace_dir.mkdir()
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            assert len(workspaces) == 0
    
    def test_discover_workspaces_multiple(self):
        """Test discovering multiple workspaces."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            # Create two workspaces
            for i in range(2):
                original_path = f"C:\\workspace{i}"
                encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
                encoded = encoded.rstrip('=')
                
                workspace_dir = workspace_sessions_dir / encoded
                workspace_dir.mkdir()
                
                sessions_data = [
                    {
                        "sessionId": f"session-{i}",
                        "title": f"Session {i}",
                        "dateCreated": 1234567890000 + i,
                        "workspaceDirectory": original_path
                    }
                ]
                
                sessions_file = workspace_dir / 'sessions.json'
                with open(sessions_file, 'w', encoding='utf-8') as f:
                    json.dump(sessions_data, f)
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            assert len(workspaces) == 2
    
    def test_discover_workspaces_last_modified(self):
        """Test that last_modified is calculated from session timestamps."""
        with TemporaryDirectory() as tmpdir:
            kiro_data_dir = Path(tmpdir)
            workspace_sessions_dir = kiro_data_dir / 'workspace-sessions'
            workspace_sessions_dir.mkdir()
            
            original_path = "C:\\workspace"
            encoded = base64.urlsafe_b64encode(original_path.encode('utf-8')).decode('utf-8')
            encoded = encoded.rstrip('=')
            
            workspace_dir = workspace_sessions_dir / encoded
            workspace_dir.mkdir()
            
            # Create sessions with different timestamps
            sessions_data = [
                {
                    "sessionId": "session-1",
                    "title": "Old Session",
                    "dateCreated": 1234567890000,
                    "workspaceDirectory": original_path
                },
                {
                    "sessionId": "session-2",
                    "title": "New Session",
                    "dateCreated": 1634567890000,  # More recent
                    "workspaceDirectory": original_path
                }
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            workspaces = discover_kiro_workspaces(kiro_data_dir)
            
            assert len(workspaces) == 1
            # Should use the most recent timestamp
            assert workspaces[0].last_modified != 'Unknown'
            assert '2021' in workspaces[0].last_modified  # 1634567890000 is in 2021

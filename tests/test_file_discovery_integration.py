"""Integration tests for file discovery across Claude and Kiro sources.

These tests verify that the correct file types are discovered for each source.
"""

import pytest
import tempfile
import json
from pathlib import Path

from src.models import ChatSource
from src.projects import get_project_chat_files


class TestFileDiscoveryIntegration:
    """Integration tests for file discovery functionality."""
    
    def test_claude_discovers_jsonl_files(self):
        """Test that Claude source discovers .jsonl files only.
        
        Validates: Requirements 3.1, 3.3
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            
            # Create test files
            (test_dir / "chat1.jsonl").write_text('{"role": "human", "content": "test"}\n')
            (test_dir / "chat2.jsonl").write_text('{"role": "human", "content": "test"}\n')
            (test_dir / "session1.chat").write_text(json.dumps({"chat": []}))
            (test_dir / "session2.json").write_text(json.dumps({"chat": []}))
            
            # Test Claude Desktop source
            claude_files = get_project_chat_files(test_dir, ChatSource.CLAUDE_DESKTOP)
            
            assert len(claude_files) == 2, f"Expected 2 JSONL files, found {len(claude_files)}"
            assert all(f.suffix == '.jsonl' for f in claude_files), "All files should be .jsonl"
            assert set(f.name for f in claude_files) == {'chat1.jsonl', 'chat2.jsonl'}
    
    def test_kiro_discovers_chat_files(self):
        """Test that Kiro source discovers .chat files only.
        
        Validates: Requirements 2.1, 2.4
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            
            # Create test files
            (test_dir / "session1.chat").write_text(json.dumps({"chat": [{"role": "human", "content": "test"}]}))
            (test_dir / "session2.chat").write_text(json.dumps({"chat": [{"role": "human", "content": "test"}]}))
            (test_dir / "chat1.jsonl").write_text('{"role": "human", "content": "test"}\n')
            (test_dir / "sessions.json").write_text(json.dumps([]))  # Metadata file
            (test_dir / "other.json").write_text(json.dumps({}))  # Other JSON file
            
            # Test Kiro IDE source
            kiro_files = get_project_chat_files(test_dir, ChatSource.KIRO_IDE)
            
            assert len(kiro_files) == 2, f"Expected 2 .chat files, found {len(kiro_files)}: {[f.name for f in kiro_files]}"
            assert all(f.suffix == '.chat' for f in kiro_files), "All files should be .chat"
            assert set(f.name for f in kiro_files) == {'session1.chat', 'session2.chat'}
    
    def test_file_discovery_sorting(self):
        """Test that files are sorted by modification time (newest first).
        
        Validates: Requirements 2.3
        """
        import time
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            
            # Create files with different modification times
            old_file = test_dir / "old.chat"
            old_file.write_text(json.dumps({"chat": []}))
            
            time.sleep(0.01)  # Ensure different timestamps
            
            new_file = test_dir / "new.chat"
            new_file.write_text(json.dumps({"chat": []}))
            
            # Get files
            kiro_files = get_project_chat_files(test_dir, ChatSource.KIRO_IDE)
            
            assert len(kiro_files) == 2
            # Newest file should be first
            assert kiro_files[0].name == "new.chat"
            assert kiro_files[1].name == "old.chat"
    
    def test_empty_directory(self):
        """Test behavior with empty directory.
        
        Validates: Requirements 2.1
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            
            claude_files = get_project_chat_files(test_dir, ChatSource.CLAUDE_DESKTOP)
            kiro_files = get_project_chat_files(test_dir, ChatSource.KIRO_IDE)
            
            assert len(claude_files) == 0
            assert len(kiro_files) == 0
    
    def test_nonexistent_directory(self):
        """Test behavior with nonexistent directory.
        
        Validates: Requirements 2.1
        """
        nonexistent = Path("/nonexistent/path/that/does/not/exist")
        
        claude_files = get_project_chat_files(nonexistent, ChatSource.CLAUDE_DESKTOP)
        kiro_files = get_project_chat_files(nonexistent, ChatSource.KIRO_IDE)
        
        assert len(claude_files) == 0
        assert len(kiro_files) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

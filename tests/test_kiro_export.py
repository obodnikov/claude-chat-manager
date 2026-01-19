"""Tests for Kiro IDE export functionality.

Tests export_project_chats with ChatSource.KIRO_IDE, including:
- Successful parsing and export of Kiro chat files
- Conversion of messages to ChatMessage objects
- Error handling for malformed files
- Filtering of trivial chats
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from src.exporters import export_project_chats
from src.models import ChatSource, ChatMessage


class TestExportProjectChatsKiro:
    """Tests for export_project_chats with Kiro IDE source."""

    def test_export_kiro_chats_basic(self):
        """Test basic export of Kiro chat files to markdown."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create a valid Kiro chat file
            chat_data = {
                "executionId": "exec-123",
                "chat": [
                    {"role": "human", "content": "Hello"},
                    {"role": "bot", "content": "Hi there!"}
                ],
                "context": []
            }
            chat_file = project_dir / "session-1.json"
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f)
            
            # Export
            exported = export_project_chats(
                project_dir, 
                export_dir, 
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            assert len(exported) == 1
            assert exported[0].exists()
            assert exported[0].suffix == '.md'
            
            # Verify content
            content = exported[0].read_text(encoding='utf-8')
            assert 'Hello' in content or 'Hi there' in content

    def test_export_kiro_excludes_sessions_json(self):
        """Test that sessions.json is excluded from export."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create sessions.json (metadata file, should be excluded)
            sessions_data = [{"sessionId": "123", "title": "Test"}]
            sessions_file = project_dir / "sessions.json"
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            # Create a valid chat file
            chat_data = {
                "executionId": "exec-123",
                "chat": [{"role": "human", "content": "Test"}],
                "context": []
            }
            chat_file = project_dir / "chat-1.json"
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f)
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            # Should only export the chat file, not sessions.json
            assert len(exported) == 1
            assert 'sessions' not in exported[0].name.lower()

    def test_export_kiro_handles_malformed_json(self):
        """Test that malformed JSON files are skipped gracefully."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create a malformed JSON file
            malformed_file = project_dir / "malformed.json"
            with open(malformed_file, 'w', encoding='utf-8') as f:
                f.write("{invalid json")
            
            # Create a valid chat file
            chat_data = {
                "executionId": "exec-123",
                "chat": [{"role": "human", "content": "Valid"}],
                "context": []
            }
            valid_file = project_dir / "valid.json"
            with open(valid_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f)
            
            # Should not raise, should skip malformed and export valid
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            # Only the valid file should be exported
            assert len(exported) == 1
            assert 'valid' in exported[0].name.lower()

    def test_export_kiro_multiple_files(self):
        """Test export of multiple Kiro chat files."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create multiple chat files
            for i in range(3):
                chat_data = {
                    "executionId": f"exec-{i}",
                    "chat": [
                        {"role": "human", "content": f"Question {i}"},
                        {"role": "bot", "content": f"Answer {i}"}
                    ],
                    "context": []
                }
                chat_file = project_dir / f"session-{i}.json"
                with open(chat_file, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f)
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            assert len(exported) == 3

    def test_export_kiro_empty_project(self):
        """Test export of project with no chat files."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            assert len(exported) == 0

    def test_export_kiro_structured_content(self):
        """Test export of Kiro chat with structured content blocks."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create chat with structured content
            chat_data = {
                "executionId": "exec-123",
                "chat": [
                    {
                        "role": "human",
                        "content": [
                            {"type": "text", "text": "Help me with code"}
                        ]
                    },
                    {
                        "role": "bot",
                        "content": [
                            {"type": "text", "text": "Here's the solution"},
                            {"type": "tool_use", "name": "write_file", "input": {"path": "test.py"}}
                        ]
                    }
                ],
                "context": []
            }
            chat_file = project_dir / "structured.json"
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f)
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.KIRO_IDE
            )
            
            assert len(exported) == 1
            assert exported[0].exists()

    def test_export_kiro_book_format(self):
        """Test export of Kiro chats to book format."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create a non-trivial chat (min 3 messages, min 75 words)
            chat_data = {
                "executionId": "exec-123",
                "chat": [
                    {"role": "human", "content": "Can you explain what Python is and how it differs from other programming languages like Java or C++?"},
                    {"role": "bot", "content": "Python is a high-level, interpreted programming language known for its simplicity and readability. Unlike Java or C++, Python uses dynamic typing and doesn't require explicit variable declarations. It emphasizes code readability with its clean syntax and significant whitespace."},
                    {"role": "human", "content": "That's helpful. What are some common use cases for Python in modern software development?"},
                    {"role": "bot", "content": "Python is widely used in web development with frameworks like Django and Flask, data science and machine learning with libraries like NumPy, Pandas, and TensorFlow, automation and scripting, and backend API development."}
                ],
                "context": []
            }
            chat_file = project_dir / "session.json"
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f)
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'book',
                source=ChatSource.KIRO_IDE
            )
            
            assert len(exported) == 1
            assert exported[0].exists()


class TestExportProjectChatsClaude:
    """Tests to ensure Claude Desktop export still works."""

    def test_export_claude_chats_unchanged(self):
        """Test that Claude Desktop export still works correctly."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create a Claude Desktop JSONL file
            jsonl_content = [
                {"type": "human", "text": "Hello Claude"},
                {"type": "assistant", "text": "Hello! How can I help?"}
            ]
            chat_file = project_dir / "chat.jsonl"
            with open(chat_file, 'w', encoding='utf-8') as f:
                for entry in jsonl_content:
                    f.write(json.dumps(entry) + '\n')
            
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown',
                source=ChatSource.CLAUDE_DESKTOP
            )
            
            assert len(exported) == 1
            assert exported[0].exists()

    def test_export_default_source_is_claude(self):
        """Test that default source is Claude Desktop for backward compatibility."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            export_dir = Path(tmpdir) / "export"
            
            # Create both .json and .jsonl files
            json_data = {"chat": [{"role": "human", "content": "Kiro"}]}
            json_file = project_dir / "kiro.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f)
            
            jsonl_content = [{"type": "human", "text": "Claude"}]
            jsonl_file = project_dir / "claude.jsonl"
            with open(jsonl_file, 'w', encoding='utf-8') as f:
                for entry in jsonl_content:
                    f.write(json.dumps(entry) + '\n')
            
            # Without source parameter, should default to Claude Desktop (JSONL)
            exported = export_project_chats(
                project_dir,
                export_dir,
                'markdown'
            )
            
            # Should only export the JSONL file
            assert len(exported) == 1
            assert 'claude' in exported[0].name.lower()


class TestKiroDataDirValidation:
    """Tests for kiro_data_dir path validation in _load_chat_data."""

    def test_valid_kiro_data_dir_structure(self):
        """Test that valid kiro_data_dir structure is detected correctly."""
        with TemporaryDirectory() as tmpdir:
            # Create proper kiro.kiroagent structure
            kiro_data_dir = Path(tmpdir) / "kiro.kiroagent"
            workspace_sessions = kiro_data_dir / "workspace-sessions"
            encoded_workspace = workspace_sessions / "dGVzdC13b3Jrc3BhY2U"  # base64 encoded
            encoded_workspace.mkdir(parents=True)
            
            # Create a session file
            session_data = {
                "chat": [
                    {"role": "human", "content": "Hello"},
                    {"role": "bot", "content": "Hi there"}
                ]
            }
            session_file = encoded_workspace / "session.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f)
            
            # Create hash-named execution log directory
            hash_dir = kiro_data_dir / "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
            subdir = hash_dir / "74abcdef"
            subdir.mkdir(parents=True)
            (subdir / "exec-001").write_text('{"executionId": "exec-001"}')
            
            from src.exporters import _load_chat_data
            
            # Load with workspace_dir, should infer kiro_data_dir
            chat_data, source, errors = _load_chat_data(
                session_file,
                workspace_dir=encoded_workspace
            )
            
            assert source == ChatSource.KIRO_IDE
            assert len(chat_data) == 2

    def test_invalid_kiro_data_dir_reports_error(self):
        """Test that invalid kiro_data_dir structure reports error."""
        with TemporaryDirectory() as tmpdir:
            # Create workspace structure without proper kiro.kiroagent parent
            workspace_dir = Path(tmpdir) / "some" / "random" / "path"
            workspace_dir.mkdir(parents=True)
            
            session_data = {
                "chat": [
                    {"role": "human", "content": "Hello"},
                    {"role": "bot", "content": "Hi"}
                ]
            }
            session_file = workspace_dir / "session.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f)
            
            from src.exporters import _load_chat_data
            
            # Load with workspace_dir pointing to invalid structure
            chat_data, source, errors = _load_chat_data(
                session_file,
                workspace_dir=workspace_dir,
                use_execution_logs=True
            )
            
            # Should still work but report error about missing execution logs
            assert source == ChatSource.KIRO_IDE
            # Should have error about inferred path
            assert any("does not" in e.lower() or "not found" in e.lower() for e in errors)

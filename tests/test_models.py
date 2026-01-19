"""Tests for models module."""

import pytest
from pathlib import Path
from src.models import ChatSource, ChatMessage, ProjectInfo


class TestChatSource:
    """Tests for ChatSource enum."""

    def test_chat_source_claude_desktop_value(self):
        """Test ChatSource.CLAUDE_DESKTOP has correct value."""
        assert ChatSource.CLAUDE_DESKTOP.value == "claude"

    def test_chat_source_kiro_ide_value(self):
        """Test ChatSource.KIRO_IDE has correct value."""
        assert ChatSource.KIRO_IDE.value == "kiro"

    def test_chat_source_unknown_value(self):
        """Test ChatSource.UNKNOWN has correct value."""
        assert ChatSource.UNKNOWN.value == "unknown"

    def test_chat_source_enum_members(self):
        """Test ChatSource enum has all expected members."""
        sources = [source.value for source in ChatSource]
        assert "claude" in sources
        assert "kiro" in sources
        assert "unknown" in sources
        assert len(sources) == 3


class TestChatMessage:
    """Tests for ChatMessage dataclass."""

    def test_chat_message_basic_creation(self):
        """Test creating a basic ChatMessage."""
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is None
        assert msg.tool_result is None
        assert msg.source == ChatSource.UNKNOWN
        assert msg.execution_id is None
        assert msg.context_items is None

    def test_chat_message_with_source_field(self):
        """Test ChatMessage with source field."""
        msg = ChatMessage(
            role="assistant",
            content="Response",
            source=ChatSource.CLAUDE_DESKTOP
        )
        assert msg.role == "assistant"
        assert msg.content == "Response"
        assert msg.source == ChatSource.CLAUDE_DESKTOP

    def test_chat_message_with_kiro_fields(self):
        """Test ChatMessage with Kiro-specific fields."""
        context = [{"type": "file", "path": "/test.py"}]
        msg = ChatMessage(
            role="user",
            content="Test message",
            source=ChatSource.KIRO_IDE,
            execution_id="exec-123",
            context_items=context
        )
        assert msg.source == ChatSource.KIRO_IDE
        assert msg.execution_id == "exec-123"
        assert msg.context_items == context
        assert len(msg.context_items) == 1

    def test_chat_message_with_all_fields(self):
        """Test ChatMessage with all fields populated."""
        msg = ChatMessage(
            role="assistant",
            content="Full message",
            timestamp="2024-01-15T10:00:00Z",
            tool_result={"status": "success"},
            source=ChatSource.KIRO_IDE,
            execution_id="exec-456",
            context_items=[{"type": "context"}]
        )
        assert msg.role == "assistant"
        assert msg.content == "Full message"
        assert msg.timestamp == "2024-01-15T10:00:00Z"
        assert msg.tool_result == {"status": "success"}
        assert msg.source == ChatSource.KIRO_IDE
        assert msg.execution_id == "exec-456"
        assert msg.context_items == [{"type": "context"}]

    def test_chat_message_default_source_is_unknown(self):
        """Test ChatMessage defaults to UNKNOWN source."""
        msg = ChatMessage(role="user", content="Test")
        assert msg.source == ChatSource.UNKNOWN


class TestProjectInfo:
    """Tests for ProjectInfo dataclass."""

    def test_project_info_basic_creation(self):
        """Test creating a basic ProjectInfo."""
        project = ProjectInfo(
            name="Test Project",
            path=Path("/test/path"),
            file_count=5,
            total_messages=100,
            last_modified="2024-01-15"
        )
        assert project.name == "Test Project"
        assert project.path == Path("/test/path")
        assert project.file_count == 5
        assert project.total_messages == 100
        assert project.last_modified == "2024-01-15"
        assert project.sort_timestamp is None
        assert project.source == ChatSource.UNKNOWN
        assert project.workspace_path is None
        assert project.session_ids is None

    def test_project_info_with_source_field(self):
        """Test ProjectInfo with source field."""
        project = ProjectInfo(
            name="Claude Project",
            path=Path("/claude/project"),
            file_count=3,
            total_messages=50,
            last_modified="2024-01-15",
            source=ChatSource.CLAUDE_DESKTOP
        )
        assert project.source == ChatSource.CLAUDE_DESKTOP

    def test_project_info_with_kiro_fields(self):
        """Test ProjectInfo with Kiro-specific fields."""
        session_ids = ["session-1", "session-2", "session-3"]
        project = ProjectInfo(
            name="Kiro Workspace",
            path=Path("/kiro/workspace"),
            file_count=3,
            total_messages=75,
            last_modified="2024-01-15",
            source=ChatSource.KIRO_IDE,
            workspace_path="/home/user/project",
            session_ids=session_ids
        )
        assert project.source == ChatSource.KIRO_IDE
        assert project.workspace_path == "/home/user/project"
        assert project.session_ids == session_ids
        assert len(project.session_ids) == 3

    def test_project_info_with_all_fields(self):
        """Test ProjectInfo with all fields populated."""
        project = ProjectInfo(
            name="Full Project",
            path=Path("/full/path"),
            file_count=10,
            total_messages=200,
            last_modified="2024-01-15",
            sort_timestamp=1705315200.0,
            source=ChatSource.KIRO_IDE,
            workspace_path="/workspace/path",
            session_ids=["s1", "s2"]
        )
        assert project.name == "Full Project"
        assert project.path == Path("/full/path")
        assert project.file_count == 10
        assert project.total_messages == 200
        assert project.last_modified == "2024-01-15"
        assert project.sort_timestamp == 1705315200.0
        assert project.source == ChatSource.KIRO_IDE
        assert project.workspace_path == "/workspace/path"
        assert project.session_ids == ["s1", "s2"]

    def test_project_info_default_source_is_unknown(self):
        """Test ProjectInfo defaults to UNKNOWN source."""
        project = ProjectInfo(
            name="Test",
            path=Path("/test"),
            file_count=1,
            total_messages=10,
            last_modified="2024-01-15"
        )
        assert project.source == ChatSource.UNKNOWN

    def test_project_info_str_representation(self):
        """Test ProjectInfo string representation."""
        project = ProjectInfo(
            name="Test Project",
            path=Path("/test"),
            file_count=5,
            total_messages=100,
            last_modified="2024-01-15"
        )
        result = str(project)
        assert "Test Project" in result
        assert "5 chats" in result
        assert "100 msgs" in result
        assert "2024-01-15" in result

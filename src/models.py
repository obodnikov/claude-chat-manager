"""Data models for Claude Chat Manager.

This module defines data classes and models for representing
projects, chats, and messages.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


class ChatSource(Enum):
    """Identifies the source of a chat or project.
    
    Attributes:
        CLAUDE_DESKTOP: Chat from Claude Desktop application
        KIRO_IDE: Chat from Kiro IDE
        UNKNOWN: Unknown or unspecified source
    """
    CLAUDE_DESKTOP = "claude"
    KIRO_IDE = "kiro"
    UNKNOWN = "unknown"


@dataclass
class ProjectInfo:
    """Information about a Claude project.

    Attributes:
        name: Cleaned, human-readable project name.
        path: Path to the project directory.
        file_count: Number of JSONL chat files.
        total_messages: Total number of messages across all chats.
        last_modified: Last modification timestamp as string.
        sort_timestamp: Unix timestamp for sorting (optional).
        source: Source of the project (Claude Desktop, Kiro IDE, etc.).
        workspace_path: Kiro-specific workspace path (optional).
        session_ids: Kiro-specific session IDs (optional).
    """

    name: str
    path: Path
    file_count: int
    total_messages: int
    last_modified: str
    sort_timestamp: Optional[float] = None
    source: ChatSource = ChatSource.UNKNOWN
    workspace_path: Optional[str] = None
    session_ids: Optional[List[str]] = None

    def __str__(self) -> str:
        """Return string representation of project info.

        Returns:
            Formatted project information string.
        """
        return f"{self.name} ({self.file_count} chats, {self.total_messages} msgs, {self.last_modified})"


@dataclass
class ChatMessage:
    """Represents a single chat message.

    Attributes:
        role: Message role (user, assistant, system).
        content: Message content (can be string or structured data).
        timestamp: Message timestamp.
        tool_result: Tool execution result (optional).
        source: Source of the chat message (Claude Desktop, Kiro IDE, etc.).
        execution_id: Kiro-specific execution ID (optional).
        context_items: Kiro-specific context items (optional).
    """

    role: str
    content: Any
    timestamp: Optional[str] = None
    tool_result: Optional[Any] = None
    source: ChatSource = ChatSource.UNKNOWN
    execution_id: Optional[str] = None
    context_items: Optional[List[dict]] = None

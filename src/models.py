"""Data models for Claude Chat Manager.

This module defines data classes and models for representing
projects, chats, and messages.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


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
    """

    name: str
    path: Path
    file_count: int
    total_messages: int
    last_modified: str
    sort_timestamp: Optional[float] = None

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
    """

    role: str
    content: any
    timestamp: Optional[str] = None
    tool_result: Optional[any] = None

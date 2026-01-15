"""Kiro IDE chat file parsing utilities.

This module handles parsing of Kiro's JSON .chat files and
extracting message data.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import ChatFileNotFoundError, InvalidChatFileError
from .models import ChatMessage, ChatSource

logger = logging.getLogger(__name__)


@dataclass
class KiroChatSession:
    """Represents a parsed Kiro chat session.
    
    Attributes:
        session_id: Unique identifier for the session
        title: Session title (if available)
        messages: List of raw message dictionaries
        context: List of context items
        execution_id: Execution ID for the session
        created_at: Session creation timestamp
    """
    session_id: str
    title: str
    messages: List[Dict[str, Any]]
    context: List[Dict[str, Any]]
    execution_id: Optional[str]
    created_at: Optional[str]


def parse_kiro_chat_file(file_path: Path) -> KiroChatSession:
    """Parse a Kiro .chat file and return structured session data.
    
    Args:
        file_path: Path to the .chat file
        
    Returns:
        KiroChatSession with parsed data
        
    Raises:
        ChatFileNotFoundError: If file doesn't exist
        InvalidChatFileError: If JSON is malformed
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Chat file not found: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            chat_data = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidChatFileError(f"Invalid JSON in {file_path}: {e}")
    except Exception as e:
        raise InvalidChatFileError(f"Failed to read chat file {file_path}: {e}")
    
    # Extract session data
    session_id = file_path.stem  # Use filename as session ID
    execution_id = chat_data.get('executionId')
    context = chat_data.get('context', [])
    messages = chat_data.get('chat', [])
    
    # Try to extract title from first user message
    title = "Untitled Session"
    for msg in messages:
        if msg.get('role') == 'human':
            content = msg.get('content', '')
            if isinstance(content, str):
                title = content[:50]  # Truncate to 50 chars
            elif isinstance(content, list) and len(content) > 0:
                # Extract from first text block
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        title = block.get('text', '')[:50]
                        break
            break
    
    return KiroChatSession(
        session_id=session_id,
        title=title,
        messages=messages,
        context=context,
        execution_id=execution_id,
        created_at=None  # Will be populated from sessions.json later
    )



def normalize_kiro_content(content: Any) -> str:
    """Normalize Kiro's structured content to plain text.
    
    Handles both string content and array of content blocks.
    
    Args:
        content: Message content (string or list of blocks)
        
    Returns:
        Normalized string content
    """
    # If content is already a string, return as-is
    if isinstance(content, str):
        return content
    
    # If content is a list of blocks, process each block
    if isinstance(content, list):
        text_parts = []
        
        for block in content:
            if not isinstance(block, dict):
                continue
            
            block_type = block.get('type', '')
            
            if block_type == 'text':
                # Extract text from text blocks
                text = block.get('text', '')
                if text:
                    text_parts.append(text)
            
            elif block_type == 'tool_use':
                # Format tool use blocks
                tool_name = block.get('name', 'unknown')
                text_parts.append(f"[Tool: {tool_name}]")
            
            elif block_type == 'image_url':
                # Indicate image presence
                text_parts.append("[Image]")
            
            elif block_type == 'image':
                # Alternative image format
                text_parts.append("[Image]")
        
        return '\n'.join(text_parts) if text_parts else ''
    
    # Fallback for unexpected types
    return str(content) if content else ''


def extract_kiro_messages(chat_data: Dict[str, Any]) -> List[ChatMessage]:
    """Extract ChatMessage objects from Kiro chat data.
    
    Args:
        chat_data: Parsed JSON from .chat file
        
    Returns:
        List of ChatMessage objects
    """
    messages = []
    chat_messages = chat_data.get('chat', [])
    execution_id = chat_data.get('executionId')
    context = chat_data.get('context', [])
    
    for msg in chat_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        # Normalize content - handle both string and array formats
        normalized_content = normalize_kiro_content(content)
        
        # Create ChatMessage object with Kiro-specific fields
        chat_msg = ChatMessage(
            role=role,
            content=normalized_content,
            timestamp=None,  # Kiro doesn't store per-message timestamps
            tool_result=None,  # Will be extracted from content blocks if needed
            source=ChatSource.KIRO_IDE,
            execution_id=execution_id,
            context_items=context if context else None
        )
        messages.append(chat_msg)
    
    return messages

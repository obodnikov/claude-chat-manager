"""Kiro IDE chat file parsing utilities.

This module handles parsing of Kiro's JSON .chat files and
extracting message data, including enrichment from execution logs.

Kiro stores chat data in two locations:
1. `.chat` files - contain brief bot acknowledgments like "On it."
2. Execution log files - contain full bot responses in `messagesFromExecutionId`

This module provides functions to:
- Parse .chat files
- Find and parse execution log files
- Enrich bot messages with full responses from execution logs
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    context = chat_data.get('context', chat_data.get('contextItems', []))
    
    # Kiro uses 'history' array, each entry has 'message' with role/content
    # Fall back to 'chat' for compatibility with test fixtures
    history = chat_data.get('history', chat_data.get('chat', []))
    
    # Convert history entries to message format
    messages = []
    for entry in history:
        if isinstance(entry, dict):
            # Real Kiro format: entry has 'message' key
            if 'message' in entry:
                messages.append(entry['message'])
            # Test fixture format: entry is the message directly
            elif 'role' in entry:
                messages.append(entry)
    
    # Try to extract title from session data or first user message
    title = chat_data.get('title', "Untitled Session")
    if title == "Untitled Session":
        for msg in messages:
            role = msg.get('role', '')
            if role in ('user', 'human'):
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


def find_execution_log_dirs(workspace_dir: Path) -> List[Path]:
    """Find all execution log directories within a workspace.
    
    Execution logs are stored in hash-named subdirectories within the workspace.
    These directories contain files without extensions that hold the full
    conversation data including complete bot responses.
    
    Args:
        workspace_dir: Path to the workspace directory (contains .chat files)
        
    Returns:
        List of paths to execution log directories
    """
    execution_dirs = []
    
    if not workspace_dir.exists():
        return execution_dirs
    
    for item in workspace_dir.iterdir():
        if item.is_dir():
            # Check if this looks like an execution log directory
            # (contains files without extensions that are JSON)
            has_execution_logs = False
            for subitem in item.iterdir():
                if subitem.is_file() and not subitem.suffix:
                    # File without extension - likely an execution log
                    has_execution_logs = True
                    break
            
            if has_execution_logs:
                execution_dirs.append(item)
    
    return execution_dirs


def build_execution_log_index(workspace_dir: Path) -> Dict[str, Path]:
    """Build an index mapping execution IDs to their log file paths.
    
    Scans all execution log directories in the workspace and creates
    a mapping from executionId to the file path containing that execution's data.
    
    Args:
        workspace_dir: Path to the workspace directory
        
    Returns:
        Dictionary mapping executionId strings to file paths
    """
    index = {}
    execution_dirs = find_execution_log_dirs(workspace_dir)
    
    for exec_dir in execution_dirs:
        for log_file in exec_dir.iterdir():
            if log_file.is_file() and not log_file.suffix:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    exec_id = data.get('executionId')
                    if exec_id:
                        index[exec_id] = log_file
                except (json.JSONDecodeError, IOError, KeyError):
                    # Skip files that can't be parsed
                    continue
    
    return index


def parse_execution_log(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse an execution log file.
    
    Args:
        file_path: Path to the execution log file (no extension)
        
    Returns:
        Parsed JSON data or None if parsing fails
    """
    if not file_path.exists():
        logger.warning(f"Execution log file not found: {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in execution log {file_path}: {e}")
        return None
    except IOError as e:
        logger.error(f"Failed to read execution log {file_path}: {e}")
        return None


def extract_bot_responses_from_execution_log(execution_log: Dict[str, Any]) -> List[str]:
    """Extract full bot text responses from an execution log.
    
    Execution logs contain a `messagesFromExecutionId` array with entries
    that have `role: "bot"` and `entries` array containing the actual content.
    
    Args:
        execution_log: Parsed execution log JSON
        
    Returns:
        List of bot response texts in order
    """
    responses = []
    
    messages = execution_log.get('messagesFromExecutionId', [])
    
    for msg in messages:
        if msg.get('role') != 'bot':
            continue
        
        entries = msg.get('entries', [])
        text_parts = []
        
        for entry in entries:
            entry_type = entry.get('type', '')
            
            if entry_type == 'text':
                text = entry.get('text', '')
                if text:
                    text_parts.append(text)
            elif entry_type == 'toolUse':
                # Include tool use indicator
                tool_name = entry.get('name', 'unknown')
                text_parts.append(f"[Tool: {tool_name}]")
        
        if text_parts:
            responses.append('\n'.join(text_parts))
    
    return responses


def find_execution_log_for_chat(
    workspace_dir: Path,
    execution_id: str,
    execution_log_index: Optional[Dict[str, Path]] = None
) -> Optional[Path]:
    """Find the execution log file for a given execution ID.
    
    Args:
        workspace_dir: Path to the workspace directory
        execution_id: The executionId from the .chat file
        execution_log_index: Optional pre-built index for faster lookups
        
    Returns:
        Path to the execution log file, or None if not found
    """
    if not execution_id:
        return None
    
    # Use index if provided
    if execution_log_index and execution_id in execution_log_index:
        return execution_log_index[execution_id]
    
    # Otherwise, search through execution log directories
    execution_dirs = find_execution_log_dirs(workspace_dir)
    
    for exec_dir in execution_dirs:
        for log_file in exec_dir.iterdir():
            if log_file.is_file() and not log_file.suffix:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if data.get('executionId') == execution_id:
                        return log_file
                except (json.JSONDecodeError, IOError):
                    continue
    
    return None


def enrich_chat_with_execution_log(
    chat_data: Dict[str, Any],
    workspace_dir: Path,
    execution_log_index: Optional[Dict[str, Path]] = None,
    strict: bool = False
) -> Tuple[Dict[str, Any], List[str]]:
    """Enrich chat data with full bot responses from execution logs.
    
    The .chat files only contain brief acknowledgments like "On it." for bot
    responses. This function finds the corresponding execution log and replaces
    those brief responses with the full text.
    
    Matching Strategy:
        Both the .chat file and execution log represent the same conversation
        tied by executionId. Messages are matched sequentially (1st bot message
        in chat → 1st bot response in log, etc.) because both files store the
        same conversation in chronological order.
    
    Args:
        chat_data: Parsed .chat file data
        workspace_dir: Path to the workspace directory containing execution logs
        execution_log_index: Optional pre-built index for faster lookups
        strict: If True, skip enrichment entirely when message counts don't match.
                If False (default), enrich what's possible and log warnings.
        
    Returns:
        Tuple of (enriched_chat_data, errors) where errors is a list of
        error messages for any issues encountered. If strict=True and counts
        don't match, returns original data with error message.
    """
    errors = []
    execution_id = chat_data.get('executionId')
    
    if not execution_id:
        errors.append("No executionId found in chat file")
        return chat_data, errors
    
    # Find the execution log
    log_path = find_execution_log_for_chat(workspace_dir, execution_id, execution_log_index)
    
    if not log_path:
        errors.append(f"Execution log not found for executionId: {execution_id}")
        return chat_data, errors
    
    # Parse the execution log
    execution_log = parse_execution_log(log_path)
    
    if not execution_log:
        errors.append(f"Failed to parse execution log: {log_path}")
        return chat_data, errors
    
    # Verify executionId matches (sanity check)
    log_exec_id = execution_log.get('executionId')
    if log_exec_id and log_exec_id != execution_id:
        errors.append(
            f"ExecutionId mismatch: chat has '{execution_id}', "
            f"log has '{log_exec_id}'. Skipping enrichment."
        )
        return chat_data, errors
    
    # Extract bot responses
    bot_responses = extract_bot_responses_from_execution_log(execution_log)
    
    if not bot_responses:
        errors.append(f"No bot responses found in execution log: {log_path}")
        return chat_data, errors
    
    # Create enriched chat data
    enriched_data = chat_data.copy()
    chat_messages = enriched_data.get('chat', [])
    
    # Count bot messages in chat for validation
    chat_bot_count = sum(1 for msg in chat_messages if msg.get('role', '') in ('bot', 'assistant'))
    exec_bot_count = len(bot_responses)
    
    # Validate message counts match
    if chat_bot_count != exec_bot_count:
        mismatch_msg = (
            f"Bot message count mismatch: chat has {chat_bot_count}, "
            f"execution log has {exec_bot_count}."
        )
        
        if strict:
            errors.append(f"{mismatch_msg} Strict mode: skipping enrichment to prevent data corruption.")
            return chat_data, errors
        
        errors.append(f"{mismatch_msg} Partial enrichment will be attempted.")
        
        if exec_bot_count < chat_bot_count:
            errors.append(
                f"Only {exec_bot_count} of {chat_bot_count} bot messages will be enriched. "
                f"Remaining messages will keep original (brief) content."
            )
    
    # Replace bot message content with full responses (sequential matching)
    # Sequential matching is correct because both files represent the same
    # conversation in chronological order, tied by the same executionId.
    bot_index = 0
    enriched_messages = []
    enriched_count = 0
    skipped_count = 0
    
    for msg in chat_messages:
        role = msg.get('role', '')
        
        if role in ('bot', 'assistant'):
            if bot_index < len(bot_responses):
                original_content = normalize_kiro_content(msg.get('content', ''))
                full_response = bot_responses[bot_index]
                
                # Content validation: check if this looks like a valid enrichment
                # Brief responses are typically short acknowledgments that should
                # either be contained in the full response or be very short
                is_valid_enrichment = _validate_enrichment(original_content, full_response)
                
                if is_valid_enrichment:
                    # Replace with full response
                    enriched_msg = msg.copy()
                    enriched_msg['content'] = full_response
                    enriched_messages.append(enriched_msg)
                    enriched_count += 1
                else:
                    # Validation failed - keep original to prevent corruption
                    errors.append(
                        f"Enrichment validation failed for bot message {bot_index + 1}: "
                        f"original '{original_content[:50]}...' doesn't match full response pattern. "
                        f"Keeping original content."
                    )
                    enriched_messages.append(msg)
                    skipped_count += 1
            else:
                # No more responses available, keep original
                enriched_messages.append(msg)
            bot_index += 1
        else:
            enriched_messages.append(msg)
    
    enriched_data['chat'] = enriched_messages
    
    # Log success info
    if enriched_count > 0:
        logger.debug(f"Successfully enriched {enriched_count} bot messages")
    if skipped_count > 0:
        logger.warning(f"Skipped {skipped_count} bot messages due to validation failures")
    
    return enriched_data, errors


def _validate_enrichment(original: str, full_response: str) -> bool:
    """Validate that enrichment is likely correct.
    
    Checks if the original brief response could reasonably be replaced
    by the full response. This helps prevent data corruption from
    mismatched messages.
    
    Args:
        original: Original brief content from .chat file
        full_response: Full response from execution log
        
    Returns:
        True if enrichment appears valid, False otherwise
    """
    # Empty or whitespace-only original is always valid to replace
    if not original or not original.strip():
        return True
    
    original_lower = original.lower().strip()
    full_lower = full_response.lower()
    
    # Common brief acknowledgments that are always valid to replace
    brief_acknowledgments = [
        "on it", "on it.", "i'll", "let me", "sure", "okay", "ok",
        "i can", "i will", "understood", "got it", "working on",
        "looking", "checking", "analyzing", "reading", "examining"
    ]
    
    for ack in brief_acknowledgments:
        if original_lower.startswith(ack):
            return True
    
    # If original is very short (< 100 chars), it's likely a brief acknowledgment
    if len(original) < 100:
        return True
    
    # If original content appears in the full response, it's valid
    # (the full response might include the brief acknowledgment)
    if original_lower in full_lower:
        return True
    
    # If original starts with the same words as full response, it's valid
    original_words = original_lower.split()[:5]
    full_words = full_lower.split()[:5]
    if original_words and full_words:
        matching_words = sum(1 for o, f in zip(original_words, full_words) if o == f)
        if matching_words >= 2:
            return True
    
    # If we get here, the content doesn't match expected patterns
    # This could indicate a mismatch - be conservative
    return False


def extract_kiro_messages_enriched(
    chat_data: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    execution_log_index: Optional[Dict[str, Path]] = None
) -> Tuple[List[ChatMessage], List[str]]:
    """Extract ChatMessage objects with enriched bot responses.
    
    This is the main function to use when exporting Kiro chats. It attempts
    to enrich bot messages with full responses from execution logs.
    
    Args:
        chat_data: Parsed JSON from .chat file
        workspace_dir: Path to workspace directory for execution log lookup
        execution_log_index: Optional pre-built index for faster lookups
        
    Returns:
        Tuple of (messages, errors) where messages is a list of ChatMessage
        objects and errors is a list of error messages encountered
    """
    errors = []
    
    # Try to enrich if workspace_dir is provided
    if workspace_dir:
        chat_data, enrich_errors = enrich_chat_with_execution_log(
            chat_data, workspace_dir, execution_log_index
        )
        errors.extend(enrich_errors)
    
    # Extract messages from (possibly enriched) chat data
    messages = []
    chat_messages = chat_data.get('chat', [])
    execution_id = chat_data.get('executionId')
    context = chat_data.get('context', [])
    
    for msg in chat_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        # Normalize content - handle both string and array formats
        normalized_content = normalize_kiro_content(content)
        
        # Skip messages with empty content after normalization
        # (these are likely failed enrichments)
        if not normalized_content.strip():
            continue
        
        # Create ChatMessage object with Kiro-specific fields
        chat_msg = ChatMessage(
            role=role,
            content=normalized_content,
            timestamp=None,  # Kiro doesn't store per-message timestamps
            tool_result=None,
            source=ChatSource.KIRO_IDE,
            execution_id=execution_id,
            context_items=context if context else None
        )
        messages.append(chat_msg)
    
    return messages, errors

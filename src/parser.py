"""JSONL file parsing utilities.

This module handles parsing of Claude's JSONL chat files and
extracting message data.
"""

import json
from pathlib import Path
from typing import List, Dict, Any
import logging

from .exceptions import ChatFileNotFoundError, InvalidJSONLError
from .models import ChatMessage

logger = logging.getLogger(__name__)


def parse_jsonl_file(file_path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL file and return list of message data.

    Args:
        file_path: Path to the JSONL file.

    Returns:
        List of parsed message dictionaries.

    Raises:
        ChatFileNotFoundError: If the file doesn't exist.
        InvalidJSONLError: If the JSONL data is malformed.
    """
    if not file_path.exists():
        raise ChatFileNotFoundError(f"Chat file not found: {file_path}")

    chat_messages = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())
                    if data and data.get('type') != 'summary':  # Skip summary entries
                        chat_messages.append(data)
                except json.JSONDecodeError as e:
                    logger.warning(f'Skipping invalid JSON on line {line_num}: {e}')
                except Exception as e:
                    logger.warning(f'Error processing line {line_num}: {e}')
    except Exception as e:
        raise InvalidJSONLError(f"Failed to read JSONL file {file_path}: {e}")

    if not chat_messages:
        logger.info(f'No valid messages found in {file_path}')

    return chat_messages


def extract_chat_messages(chat_data: List[Dict[str, Any]]) -> List[ChatMessage]:
    """Extract ChatMessage objects from parsed JSONL data.

    Args:
        chat_data: List of parsed message dictionaries.

    Returns:
        List of ChatMessage objects.
    """
    messages = []

    for entry in chat_data:
        # Extract the nested message structure
        message = entry.get('message', {})

        # Skip if no message content
        if not message:
            continue

        # Get basic message info
        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        timestamp = entry.get('timestamp')
        tool_result = entry.get('toolUseResult')

        # Create ChatMessage object
        chat_msg = ChatMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_result=tool_result
        )
        messages.append(chat_msg)

    return messages


def count_messages_in_file(file_path: Path) -> int:
    """Count number of messages in a JSONL file.

    Args:
        file_path: Path to the JSONL file.

    Returns:
        Number of messages in the file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except Exception as e:
        logger.error(f"Error counting messages in {file_path}: {e}")
        return 0

def count_codex_messages_in_file(file_path: Path) -> int:
    """Count user and assistant messages in a Codex rollout JSONL file.

    Only counts response_item entries with type 'message' and
    role 'user' or 'assistant', matching the export filtering logic.

    Args:
        file_path: Path to the Codex rollout JSONL file.

    Returns:
        Number of conversation messages (user + assistant only).
    """
    count = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if (data.get('type') == 'response_item'
                            and isinstance(data.get('payload'), dict)
                            and data['payload'].get('type') == 'message'
                            and data['payload'].get('role') in ('user', 'assistant')):
                        count += 1
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        logger.error(f"Error counting Codex messages in {file_path}: {e}")
        return 0
    return count


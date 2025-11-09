"""Message formatting utilities for different output formats.

This module handles formatting of chat messages for various output formats
including pretty terminal output, markdown, and book format.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import logging

from .colors import Colors

logger = logging.getLogger(__name__)


def format_timestamp(ts: Optional[Union[str, int, float]]) -> str:
    """Format timestamp to readable format.

    Args:
        ts: Timestamp in various formats (ISO string, unix seconds/milliseconds).

    Returns:
        Formatted timestamp string.

    Example:
        >>> format_timestamp("2025-09-20T12:28:46.794Z")
        '2025-09-20 12:28:46'
        >>> format_timestamp(1695217726000)
        '2023-09-20 12:28:46'
    """
    try:
        if ts is None:
            return 'No timestamp'

        if isinstance(ts, str):
            # Parse ISO format (like 2025-09-20T12:28:46.794Z)
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                logger.debug(f"Failed to parse timestamp string: {ts}, error: {e}")
                return ts

        if isinstance(ts, (int, float)):
            # Handle both seconds and milliseconds timestamps
            if ts > 1000000000000:  # Milliseconds
                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            else:  # Seconds
                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

        return str(ts)
    except Exception as e:
        logger.error(f"Error formatting timestamp {ts}: {e}")
        return 'Invalid timestamp'


def format_tool_use(tool_input: Dict[str, Any]) -> List[str]:
    """Format tool use parameters for display.

    Args:
        tool_input: Dictionary of tool input parameters.

    Returns:
        List of formatted parameter strings.
    """
    text_parts = []

    if 'file_path' in tool_input:
        text_parts.append(f'   File: {tool_input["file_path"]}')
    elif 'todos' in tool_input:
        todos = tool_input.get('todos', [])
        if todos:
            text_parts.append(f'   Todos: {len(todos)} items')
            for todo in todos[:2]:  # Show first 2 todos
                todo_content = todo.get('content', 'Unknown todo')
                status = todo.get('status', 'unknown')
                text_parts.append(f'     • {todo_content} ({status})')
    elif 'old_string' in tool_input and 'new_string' in tool_input:
        old_preview = tool_input['old_string'][:50] + '...' if len(tool_input['old_string']) > 50 else tool_input['old_string']
        text_parts.append(f'   Replacing: {old_preview}')
    elif 'edits' in tool_input:
        edits = tool_input.get('edits', [])
        text_parts.append(f'   Edits: {len(edits)} changes')
    else:
        params = []
        for k, v in list(tool_input.items())[:3]:
            if isinstance(v, str) and len(v) > 50:
                params.append(f'{k}={v[:50]}...')
            elif isinstance(v, (list, dict)):
                params.append(f'{k}=<{type(v).__name__}>')
            else:
                params.append(f'{k}={v}')
        if params:
            text_parts.append(f'   Parameters: {", ".join(params)}')

    return text_parts


def format_content(content: Any, role: str) -> str:
    """Format message content for display.

    Args:
        content: Message content (can be string, list, or dict).
        role: Message role (user, assistant, system).

    Returns:
        Formatted content string.
    """
    if content is None:
        return f'[Empty {role} message]'

    if not content:
        return f'[No content in {role} message]'

    # Handle string content
    if isinstance(content, str):
        return content.strip() if content.strip() else f'[Empty {role} message]'

    # Handle list content (Claude's structured format)
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text = item.get('text', '').strip()
                    if text:
                        text_parts.append(text)
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'unknown')
                    tool_input = item.get('input', {})
                    text_parts.append(f'🔧 [Tool Use: {tool_name}]')
                    if tool_input:
                        text_parts.extend(format_tool_use(tool_input))
                elif item.get('type') == 'tool_result':
                    result = item.get('content', '')
                    if isinstance(result, str):
                        preview = result[:200] + '...' if len(result) > 200 else result
                        text_parts.append(f'⚙️ [Tool Result: {preview}]')
                    else:
                        text_parts.append('⚙️ [Tool Result]')
                elif item.get('type') == 'image':
                    text_parts.append('🖼️ [Image attachment]')
            elif isinstance(item, str):
                if item.strip():
                    text_parts.append(item.strip())
            else:
                text_parts.append(str(item))

        result = '\n'.join(text_parts) if text_parts else f'[Empty {role} message]'
        return result

    # Handle dict content
    if isinstance(content, dict):
        if 'text' in content:
            return content['text'].strip() if content['text'] else f'[Empty {role} message]'
        elif 'content' in content:
            return format_content(content['content'], role)
        else:
            return f'[Complex {role} data: {str(content)[:100]}...]'

    return str(content) if content else f'[Empty {role} message]'


def format_tool_result(tool_result: Any, role: str) -> str:
    """Format tool result information for display.

    Args:
        tool_result: Tool result data.
        role: Message role.

    Returns:
        Formatted tool result string.
    """
    if not tool_result:
        return ''

    if isinstance(tool_result, str):
        return f'\n⚙️ [Tool Output]: {tool_result[:200]}...' if len(tool_result) > 200 else f'\n⚙️ [Tool Output]: {tool_result}'

    if isinstance(tool_result, dict):
        result_type = tool_result.get('type', 'unknown')

        if result_type == 'text' and 'file' in tool_result:
            file_info = tool_result['file']
            file_path = file_info.get('filePath', 'unknown')
            lines = file_info.get('numLines', 0)
            return f'\n📄 [File Read]: {file_path} ({lines} lines)'

        elif 'newTodos' in tool_result:
            new_todos = tool_result.get('newTodos', [])
            old_todos = tool_result.get('oldTodos', [])
            return f'\n✅ [Todo Update]: {len(old_todos)} → {len(new_todos)} todos'

        elif 'filePath' in tool_result and 'newString' in tool_result:
            file_path = tool_result.get('filePath', 'unknown')
            return f'\n✏️ [File Edit]: {file_path}'

        else:
            return f'\n⚙️ [Tool Result]: {result_type}'

    return f'\n⚙️ [Tool Result]: {str(tool_result)[:100]}...'


def sanitize_for_filename(name: str) -> str:
    """Sanitize name for use in filename/directory.

    Converts spaces to hyphens, removes special characters, and normalizes format.
    Useful for creating clean directory names from hostnames or project names.

    Args:
        name: Original name (may contain spaces, special chars, dots).

    Returns:
        Sanitized name with hyphens instead of spaces, safe for filenames.

    Example:
        >>> sanitize_for_filename('MacBook Air.local')
        'MacBook-Air'
        >>> sanitize_for_filename('My Project Name')
        'My-Project-Name'
    """
    import re

    # Remove .local suffix if present (common in hostnames)
    if name.endswith('.local'):
        name = name[:-6]

    # Replace spaces and underscores with hyphens
    sanitized = name.replace(' ', '-').replace('_', '-')

    # Remove dots and other special characters except hyphens
    sanitized = re.sub(r'[^\w-]', '', sanitized)

    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)

    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')

    return sanitized


def clean_project_name(name: str) -> str:
    """Clean project name by removing leading dash and making it readable.

    Args:
        name: Original project directory name.

    Returns:
        Cleaned and readable project name.

    Example:
        >>> clean_project_name('-my-project-name')
        'My Project Name'
    """
    # Remove leading dash if present
    if name.startswith('-'):
        name = name[1:]

    # Replace dashes with spaces for better readability
    readable_name = name.replace('-', ' ').title()

    return readable_name

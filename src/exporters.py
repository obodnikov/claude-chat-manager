"""Export functionality for various output formats.

This module handles exporting chats to different formats including
pretty terminal output, markdown, book format, and wiki format.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import os

from .parser import parse_jsonl_file, extract_chat_messages
from .formatters import format_content, format_tool_result, format_timestamp, clean_project_name
from .colors import Colors, get_role_color
from .exceptions import ExportError

logger = logging.getLogger(__name__)


def export_chat_pretty(chat_data: List[Dict[str, Any]]) -> str:
    """Export chat in pretty terminal format with colors.

    Args:
        chat_data: Parsed JSONL chat data.

    Returns:
        Formatted string ready for terminal display.
    """
    output_lines = []
    msg_count = 0

    for entry in chat_data:
        message = entry.get('message', {})
        if not message:
            continue

        msg_count += 1

        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        timestamp = format_timestamp(entry.get('timestamp'))
        tool_result = entry.get('toolUseResult')

        formatted_content = format_content(content, role)

        if tool_result:
            tool_output = format_tool_result(tool_result, role)
            if tool_output:
                formatted_content += tool_output

        # Skip empty messages
        if not formatted_content or formatted_content.strip() in ['[Empty unknown message]', '[No content in unknown message]']:
            continue

        color, icon = get_role_color(role)

        output_lines.append(f'{color}{icon} Message {msg_count} - {role.title()}{Colors.NC}')
        output_lines.append(f'🕒 {timestamp}')
        output_lines.append(f'💬 {formatted_content}')
        output_lines.append('─' * 80)

    return '\n'.join(output_lines)


def export_chat_markdown(chat_data: List[Dict[str, Any]]) -> str:
    """Export chat in standard markdown format.

    Args:
        chat_data: Parsed JSONL chat data.

    Returns:
        Markdown formatted string.
    """
    output_lines = []
    output_lines.append('# Claude Chat Export\n')
    output_lines.append(f'**Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**\n')

    msg_count = 0

    for entry in chat_data:
        message = entry.get('message', {})
        if not message:
            continue

        msg_count += 1

        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        timestamp = format_timestamp(entry.get('timestamp'))
        tool_result = entry.get('toolUseResult')

        formatted_content = format_content(content, role)

        if tool_result:
            tool_output = format_tool_result(tool_result, role)
            if tool_output:
                formatted_content += tool_output

        if not formatted_content or formatted_content.strip() in ['[Empty unknown message]', '[No content in unknown message]']:
            continue

        output_lines.append(f'## Message {msg_count} - {role.title()}\n')
        output_lines.append(f'**Time:** {timestamp}\n\n')
        output_lines.append(f'{formatted_content}\n\n')
        output_lines.append('---\n\n')

    return ''.join(output_lines)


def export_chat_book(chat_data: List[Dict[str, Any]]) -> str:
    """Export chat in clean book format without timestamps.

    Args:
        chat_data: Parsed JSONL chat data.

    Returns:
        Book formatted string.
    """
    output_lines = []
    output_lines.append('# Claude Chat Export\n')
    output_lines.append(f'**Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**\n')

    for entry in chat_data:
        message = entry.get('message', {})
        if not message:
            continue

        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')
        tool_result = entry.get('toolUseResult')

        formatted_content = format_content(content, role)

        if tool_result:
            tool_output = format_tool_result(tool_result, role)
            if tool_output:
                formatted_content += tool_output

        if not formatted_content or formatted_content.strip() in ['[Empty unknown message]', '[No content in unknown message]']:
            continue

        if role == 'user':
            # User question in callout style
            output_lines.append(f'> {formatted_content}\n\n')
        elif role == 'assistant':
            # Assistant response without headers
            output_lines.append(f'{formatted_content}\n\n')

    return ''.join(output_lines)


def export_chat_to_file(
    file_path: Path,
    output_path: Path,
    format_type: str = 'markdown'
) -> None:
    """Export a chat file to specified format and save to file.

    Args:
        file_path: Path to the JSONL chat file.
        output_path: Path where to save the export.
        format_type: Export format (pretty, markdown, book, raw).

    Raises:
        ExportError: If export operation fails.
    """
    try:
        chat_data = parse_jsonl_file(file_path)

        if format_type == 'markdown':
            content = export_chat_markdown(chat_data)
        elif format_type == 'book':
            content = export_chat_book(chat_data)
        elif format_type == 'pretty':
            content = export_chat_pretty(chat_data)
        elif format_type == 'raw':
            import json
            content = '\n'.join(json.dumps(entry, indent=2) for entry in chat_data)
        else:
            raise ExportError(f"Unknown format type: {format_type}")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Exported chat to {output_path} in {format_type} format")

    except Exception as e:
        raise ExportError(f"Failed to export chat: {e}")


def export_project_chats(
    project_path: Path,
    export_dir: Path,
    format_type: str = 'markdown'
) -> List[Path]:
    """Export all chats in a project to a directory.

    Args:
        project_path: Path to the project directory.
        export_dir: Directory where to save exports.
        format_type: Export format (markdown, book).

    Returns:
        List of exported file paths.

    Raises:
        ExportError: If export operation fails.
    """
    try:
        # Create export directory
        os.makedirs(export_dir, exist_ok=True)

        chat_files = list(project_path.glob('*.jsonl'))
        exported_files = []

        for chat_file in chat_files:
            chat_name = chat_file.stem
            export_file = export_dir / f"{chat_name}.md"

            export_chat_to_file(chat_file, export_file, format_type)
            exported_files.append(export_file)

        logger.info(f"Exported {len(exported_files)} chats to {export_dir}")
        return exported_files

    except Exception as e:
        raise ExportError(f"Failed to export project chats: {e}")


def export_project_wiki(
    project_path: Path,
    output_file: Path,
    use_llm: bool = True,
    api_key: Optional[str] = None
) -> None:
    """Export entire project as single wiki file with AI-generated titles.

    Args:
        project_path: Path to the project directory.
        output_file: Path where to save the wiki.
        use_llm: Whether to use LLM for title generation.
        api_key: OpenRouter API key (required if use_llm=True).

    Raises:
        ExportError: If export operation fails.
    """
    try:
        from .wiki_generator import WikiGenerator
        from .llm_client import OpenRouterClient

        # Get all chat files
        chat_files = list(project_path.glob('*.jsonl'))
        if not chat_files:
            raise ExportError(f"No chat files found in {project_path}")

        chat_files.sort()

        # Initialize LLM client if requested
        llm_client = None
        if use_llm and api_key:
            try:
                llm_client = OpenRouterClient(api_key=api_key)
                logger.info("Using LLM for title generation")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM client: {e}")
                logger.info("Falling back to non-LLM title generation")

        # Generate wiki
        project_name = clean_project_name(project_path.name)
        wiki_gen = WikiGenerator(llm_client=llm_client)
        wiki_content = wiki_gen.generate_wiki(
            chat_files=chat_files,
            project_name=project_name,
            use_llm_titles=use_llm and llm_client is not None
        )

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(wiki_content)

        logger.info(f"Wiki exported to {output_file}")

    except Exception as e:
        raise ExportError(f"Failed to export project wiki: {e}")

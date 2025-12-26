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
from .colors import Colors, get_role_color, print_colored
from .exceptions import ExportError
from .filters import ChatFilter
from .sanitizer import Sanitizer
from .config import config

logger = logging.getLogger(__name__)


def _display_wiki_summary(stats: 'WikiGenerationStats', mode: str) -> None:
    """Display summary of wiki generation statistics.

    Args:
        stats: Wiki generation statistics.
        mode: Generation mode ('new', 'update', 'rebuild').
    """
    from .wiki_generator import WikiGenerationStats

    print()  # Blank line before summary
    print_colored("📊 Wiki Generation Summary:", Colors.CYAN)
    print_colored("=" * 50, Colors.CYAN)

    if mode == 'new':
        print(f"   Total chats in wiki: {stats.total_chats}")
        if stats.filtered_chats > 0:
            print(f"   Filtered out (trivial): {stats.filtered_chats} chats")
        print(f"   Titles generated: {stats.titles_generated}")
    elif mode == 'update':
        print(f"   Previously in wiki: {stats.existing_chats} chats")
        print(f"   Added to wiki: {stats.new_chats} new chats")
        if stats.filtered_chats > 0:
            print(f"   Filtered out (trivial): {stats.filtered_chats} chats")
        print(f"   Total chats now: {stats.total_chats}")
        print()
        print(f"   Titles reused (cached): {stats.titles_from_cache}")
        print(f"   Titles newly generated: {stats.titles_generated}")
        print()
        strategy_label = "Append-only (fast)" if stats.strategy_used == 'append' else "Full rebuild (thorough)"
        print(f"   Strategy used: {strategy_label}")
    elif mode == 'rebuild':
        print(f"   Total chats in wiki: {stats.total_chats}")
        if stats.filtered_chats > 0:
            print(f"   Filtered out (trivial): {stats.filtered_chats} chats")
        print(f"   All titles regenerated: {stats.titles_generated}")

    print_colored("=" * 50, Colors.CYAN)


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


def export_chat_book(chat_data: List[Dict[str, Any]], sanitize: Optional[bool] = None) -> str:
    """Export chat in clean book format without timestamps.

    Applies enhanced filtering based on configuration:
    - Filters out system tags from user messages
    - Removes tool use/result noise
    - Shows file references (optional)
    - Enhanced user message highlighting
    - Sanitizes sensitive data (optional)

    Args:
        chat_data: Parsed JSONL chat data.
        sanitize: Enable sanitization (overrides config if provided).

    Returns:
        Book formatted string.
    """
    output_lines = []
    output_lines.append('# Claude Chat Export\n')
    output_lines.append(f'**Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**\n\n')

    # Initialize sanitizer if enabled
    sanitizer = None
    sanitize_enabled = sanitize if sanitize is not None else config.sanitize_enabled

    if sanitize_enabled:
        sanitizer = Sanitizer(
            enabled=True,
            level=config.sanitize_level,
            style=config.sanitize_style,
            sanitize_paths=config.sanitize_paths,
            custom_patterns=config.sanitize_custom_patterns,
            allowlist=config.sanitize_allowlist
        )
        logger.debug(f"Sanitization enabled for book export (level: {config.sanitize_level}, style: {config.sanitize_style})")

    # Initialize chat filter with book-specific config
    chat_filter = ChatFilter(
        skip_trivial=False,  # Don't filter entire chats here, done earlier
        filter_system_tags=config.book_filter_system_tags
    )

    for entry in chat_data:
        message = entry.get('message', {})
        if not message:
            continue

        role = message.get('role', entry.get('type', 'unknown'))
        content = message.get('content', '')

        # Skip system messages
        if role not in ('user', 'assistant'):
            continue

        # Extract clean content (filter tool noise if configured)
        if config.book_filter_tool_noise:
            text, files = chat_filter.extract_clean_content(content, include_tool_use=False)
        else:
            # Use standard formatting if tool noise filtering is disabled
            text = format_content(content, role)
            files = []

        # For user messages, clean system tags
        if role == 'user':
            if config.book_filter_system_tags:
                text = chat_filter.clean_user_message(text)
                # Skip if message was purely system notification
                if not text:
                    continue

            # Apply sanitization to user text
            if sanitizer:
                text, _ = sanitizer.sanitize_text(text, track_changes=False)

            # Enhanced user message formatting with visual separator
            output_lines.append('---\n\n')
            output_lines.append('👤 **USER:**\n')
            output_lines.append(f'> {text}\n\n')

        elif role == 'assistant':
            if not text or not text.strip():
                continue

            # Apply sanitization to assistant text
            if sanitizer:
                text, _ = sanitizer.sanitize_text(text, track_changes=False)

            # Assistant response without headers
            output_lines.append(f'{text}\n')

            # Add file references if enabled and files were modified
            if config.book_show_file_refs and files:
                files_list = ', '.join(f'`{f}`' for f in sorted(set(files)))
                output_lines.append(f'\n*Files: {files_list}*\n')

            output_lines.append('\n')

    return ''.join(output_lines)


def export_chat_to_file(
    file_path: Path,
    output_path: Path,
    format_type: str = 'markdown',
    sanitize: Optional[bool] = None
) -> None:
    """Export a chat file to specified format and save to file.

    Args:
        file_path: Path to the JSONL chat file.
        output_path: Path where to save the export.
        format_type: Export format (pretty, markdown, book, raw).
        sanitize: Override .env sanitization setting (True/False/None).

    Raises:
        ExportError: If export operation fails.
    """
    try:
        chat_data = parse_jsonl_file(file_path)

        if format_type == 'markdown':
            content = export_chat_markdown(chat_data)
        elif format_type == 'book':
            content = export_chat_book(chat_data, sanitize=sanitize)
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
    format_type: str = 'markdown',
    api_key: Optional[str] = None,
    sanitize: Optional[bool] = None
) -> List[Path]:
    """Export all chats in a project to a directory.

    For book format, applies enhanced features:
    - Filters out trivial/empty chats (configurable)
    - Generates descriptive filenames (configurable)
    - Applies content cleaning and filtering
    - Optional sensitive data sanitization

    Args:
        project_path: Path to the project directory.
        export_dir: Directory where to save exports.
        format_type: Export format (markdown, book).
        api_key: OpenRouter API key for LLM title generation (optional).
        sanitize: Override .env sanitization setting (True/False/None).

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
        filtered_count = 0

        # Initialize filter for book format if needed
        chat_filter = None
        if format_type == 'book' and config.book_skip_trivial:
            chat_filter = ChatFilter(
                skip_trivial=config.book_skip_trivial,
                min_messages=config.book_min_messages,
                min_words=config.book_min_words,
                skip_keywords=config.book_skip_keywords,
                filter_system_tags=config.book_filter_system_tags
            )

        # Initialize LLM client for title generation if needed
        llm_client = None
        if format_type == 'book' and config.book_generate_titles and config.book_use_llm_titles:
            # Use provided API key or fall back to config
            effective_api_key = api_key or config.openrouter_api_key
            if effective_api_key:
                try:
                    from .llm_client import OpenRouterClient
                    llm_client = OpenRouterClient(api_key=effective_api_key)
                    logger.info("Using LLM for title generation in book export")
                except Exception as e:
                    logger.warning(f"Failed to initialize LLM client: {e}")
                    logger.info("Falling back to first user question for titles")
            else:
                logger.info("No API key available, using first user question for titles")

        for chat_file in chat_files:
            # Parse chat data for filtering and title generation
            chat_data = parse_jsonl_file(chat_file)

            # Filter trivial chats for book format
            if chat_filter and chat_filter.is_pointless_chat(chat_data):
                logger.info(f"Filtering out trivial chat: {chat_file.name}")
                filtered_count += 1
                continue

            # Generate filename
            if format_type == 'book' and config.book_generate_titles:
                filename = _generate_book_filename(
                    chat_data,
                    chat_file,
                    llm_client,
                    chat_filter
                )
            else:
                filename = chat_file.stem

            export_file = export_dir / f"{filename}.md"

            export_chat_to_file(chat_file, export_file, format_type, sanitize=sanitize)
            exported_files.append(export_file)

        logger.info(f"Exported {len(exported_files)} chats to {export_dir}")
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} trivial chats")

        return exported_files

    except Exception as e:
        raise ExportError(f"Failed to export project chats: {e}")


def _extract_chat_date_simple(chat_data: List[Dict[str, Any]]) -> Optional[str]:
    """Extract date from first message in chat for filename.

    Args:
        chat_data: Parsed chat data.

    Returns:
        Date string in YYYY-MM-DD format or None if not available.
    """
    if not chat_data:
        return None

    first_entry = chat_data[0]
    timestamp = first_entry.get('timestamp')

    if not timestamp:
        return None

    try:
        from datetime import datetime

        if isinstance(timestamp, str):
            # Parse ISO format (like 2025-09-20T12:28:46.794Z)
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif isinstance(timestamp, (int, float)):
            # Handle both seconds and milliseconds timestamps
            if timestamp > 10000000000:  # Milliseconds
                dt = datetime.fromtimestamp(timestamp / 1000)
            else:  # Seconds
                dt = datetime.fromtimestamp(timestamp)
        else:
            return None

        return dt.strftime('%Y-%m-%d')

    except Exception as e:
        logger.debug(f"Failed to extract date from timestamp: {e}")
        return None


def _generate_book_filename(
    chat_data: List[Dict[str, Any]],
    chat_file: Path,
    llm_client: Optional[Any],
    chat_filter: Optional[ChatFilter]
) -> str:
    """Generate descriptive filename for book export.

    Generates filename in format: topic-name-2025-11-09
    If date extraction fails, uses: topic-name

    Args:
        chat_data: Parsed chat data.
        chat_file: Original chat file path.
        llm_client: Optional LLM client for title generation.
        chat_filter: Optional chat filter for text extraction.

    Returns:
        Sanitized filename (without extension).
    """
    title = None

    # Try LLM generation if available
    if llm_client:
        try:
            # Extract conversation excerpt for title generation
            excerpt_parts = []
            total_chars = 0
            max_chars = 2000 * 4  # Approximate 2000 tokens

            for entry in chat_data[:20]:  # First 20 messages
                message = entry.get('message', {})
                role = message.get('role', '')
                content = message.get('content', '')

                if role not in ('user', 'assistant'):
                    continue

                # Extract text
                if chat_filter:
                    text = chat_filter.extract_text_only(content)
                else:
                    text = str(content)

                if not text:
                    continue

                prefix = "User: " if role == 'user' else "Assistant: "
                message_text = f"{prefix}{text}\n\n"

                if total_chars + len(message_text) > max_chars:
                    break

                excerpt_parts.append(message_text)
                total_chars += len(message_text)

            excerpt = ''.join(excerpt_parts)

            if excerpt:
                title = llm_client.generate_chat_title(excerpt, max_words=10)
                logger.debug(f"Generated LLM title: {title}")

        except Exception as e:
            logger.warning(f"LLM title generation failed: {e}")

    # Fallback: Use first user question
    if not title:
        for entry in chat_data:
            message = entry.get('message', {})
            role = message.get('role', '')
            content = message.get('content', '')

            if role == 'user':
                # Extract text
                if chat_filter:
                    text = chat_filter.extract_text_only(content)
                else:
                    text = str(content)

                if text:
                    # Use first line or first 60 chars
                    first_line = text.split('\n')[0]
                    title = first_line[:60].strip()
                    if len(first_line) > 60:
                        title += "..."
                    break

    # Last resort: use filename
    if not title:
        title = f"chat-{chat_file.stem[:8]}"

    # Sanitize filename (remove special chars, limit length)
    # Keep alphanumeric, spaces, hyphens, underscores
    import re
    sanitized = re.sub(r'[^\w\s-]', '', title)
    sanitized = re.sub(r'[-\s]+', '-', sanitized)
    sanitized = sanitized.strip('-_')

    # Limit to 100 chars for filesystem compatibility (leaving room for date)
    if len(sanitized) > 89:  # 100 - 11 chars for date (-YYYY-MM-DD)
        sanitized = sanitized[:89].rstrip('-_')

    # Make lowercase for consistency
    sanitized = sanitized.lower()

    # Append date if available and configured
    if config.book_include_date:
        chat_date = _extract_chat_date_simple(chat_data)
        if chat_date:
            sanitized = f"{sanitized}-{chat_date}"

    return sanitized if sanitized else f"chat-{chat_file.stem[:8]}"


def export_single_chat(
    chat_file: Path,
    format_type: str = 'markdown',
    output_dir: Optional[Path] = None,
    api_key: Optional[str] = None
) -> Path:
    """Export a single chat file to markdown or book format.

    Generates descriptive filename for book format using same logic as batch export.
    Saves to current directory by default or specified output directory.

    Args:
        chat_file: Path to the chat JSONL file to export.
        format_type: Export format ('markdown' or 'book').
        output_dir: Optional output directory (defaults to current directory).
        api_key: Optional OpenRouter API key for LLM title generation.

    Returns:
        Path to the exported file.

    Raises:
        ExportError: If export operation fails.
    """
    try:
        # Default to current directory
        if output_dir is None:
            output_dir = Path.cwd()
        else:
            os.makedirs(output_dir, exist_ok=True)

        # Parse chat data for filename generation
        chat_data = parse_jsonl_file(chat_file)

        # Generate filename
        if format_type == 'book' and config.book_generate_titles:
            # Initialize LLM client if needed
            llm_client = None
            if config.book_use_llm_titles:
                effective_api_key = api_key or config.openrouter_api_key
                if effective_api_key:
                    try:
                        from .llm_client import OpenRouterClient
                        llm_client = OpenRouterClient(api_key=effective_api_key)
                        logger.debug("Using LLM for single chat title generation")
                    except Exception as e:
                        logger.warning(f"Failed to initialize LLM client: {e}")

            # Initialize chat filter for text extraction
            chat_filter = ChatFilter(
                skip_trivial=False,
                filter_system_tags=config.book_filter_system_tags
            )

            filename = _generate_book_filename(
                chat_data,
                chat_file,
                llm_client,
                chat_filter
            )
        else:
            filename = chat_file.stem

        output_file = output_dir / f"{filename}.md"

        # Export the file
        export_chat_to_file(chat_file, output_file, format_type)

        logger.info(f"Exported single chat to {output_file}")
        return output_file

    except Exception as e:
        raise ExportError(f"Failed to export single chat: {e}")


def export_project_wiki(
    project_path: Path,
    output_file: Path,
    use_llm: bool = True,
    api_key: Optional[str] = None,
    update_mode: str = 'new',
    sanitize: Optional[bool] = None
) -> None:
    """Export entire project as single wiki file with AI-generated titles.

    Args:
        project_path: Path to the project directory.
        output_file: Path where to save the wiki.
        use_llm: Whether to use LLM for title generation.
        api_key: OpenRouter API key (required if use_llm=True).
        update_mode: Mode: 'new', 'update', or 'rebuild'.
        sanitize: Override .env sanitization setting (True/False/None).

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
        wiki_gen = WikiGenerator(llm_client=llm_client, sanitize=sanitize)

        # Pass existing wiki file for update/rebuild modes
        existing_wiki = output_file if update_mode in ['update', 'rebuild'] else None

        # Print status message before generation
        if update_mode == 'update' and existing_wiki and existing_wiki.exists():
            # Calculate stats for feedback
            from .wiki_parser import WikiParser
            try:
                parser = WikiParser(existing_wiki)
                existing_sections = parser.parse()
                existing_count = len(existing_sections)
                existing_chat_ids = set(existing_sections.keys())
                current_chat_ids = {f.stem[:8] for f in chat_files}
                new_count = len(current_chat_ids - existing_chat_ids)
                print_colored(
                    f"📝 Found {existing_count} existing chats, adding {new_count} new chats",
                    Colors.CYAN
                )
            except Exception:
                pass
        elif update_mode == 'rebuild':
            print_colored(f"🔄 Rebuilding wiki with {len(chat_files)} chats", Colors.CYAN)

        wiki_content, stats = wiki_gen.generate_wiki(
            chat_files=chat_files,
            project_name=project_name,
            use_llm_titles=use_llm and llm_client is not None,
            existing_wiki=existing_wiki,
            update_mode=update_mode
        )

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(wiki_content)

        logger.info(f"Wiki exported to {output_file}")

        # Display summary statistics
        _display_wiki_summary(stats, update_mode)

    except Exception as e:
        raise ExportError(f"Failed to export project wiki: {e}")

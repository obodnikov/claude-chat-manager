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
from .kiro_parser import (
    parse_kiro_chat_file, 
    extract_kiro_messages, 
    extract_kiro_messages_enriched, 
    build_execution_log_index,
    build_full_session_from_executions
)
from .models import ChatSource, ChatMessage

logger = logging.getLogger(__name__)


def _detect_chat_source(file_path: Path) -> ChatSource:
    """Detect whether a chat file is from Claude Desktop or Kiro IDE.
    
    Uses both file extension and content structure to determine source.
    
    Args:
        file_path: Path to the chat file
        
    Returns:
        ChatSource enum value
        
    Raises:
        ExportError: If file format cannot be determined
    """
    import json
    
    # First check: file extension
    if file_path.suffix == '.jsonl':
        return ChatSource.CLAUDE_DESKTOP
    
    if file_path.suffix in ('.chat', '.json'):
        # Second check: inspect file content structure
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Try to read first line/object
                first_line = f.readline().strip()
                if not first_line:
                    raise ExportError(f"Empty file: {file_path}")
                
                data = json.loads(first_line)
                
                # Kiro files have 'chat' array and 'executionId' at top level
                if isinstance(data, dict) and 'chat' in data:
                    return ChatSource.KIRO_IDE
                
                # Claude JSONL has 'message' or 'type' at top level
                if isinstance(data, dict) and ('message' in data or 'type' in data):
                    return ChatSource.CLAUDE_DESKTOP
                
        except json.JSONDecodeError:
            # If JSON parsing fails, fall back to extension
            pass
        except Exception as e:
            logger.warning(f"Error detecting source for {file_path}: {e}")
        
        # Default for .chat/.json files
        return ChatSource.KIRO_IDE
    
    # Default fallback
    return ChatSource.CLAUDE_DESKTOP


def _convert_kiro_to_dict(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Convert Kiro ChatMessage objects to dict format for compatibility.
    
    Args:
        messages: List of ChatMessage objects from Kiro parser
        
    Returns:
        List of message dictionaries compatible with export functions
    """
    chat_data = []
    for msg in messages:
        entry = {
            'message': {
                'role': msg.role,
                'content': msg.content
            },
            'timestamp': msg.timestamp,
            'source': ChatSource.KIRO_IDE
        }
        if msg.execution_id:
            entry['execution_id'] = msg.execution_id
        if msg.context_items:
            entry['context_items'] = msg.context_items
        chat_data.append(entry)
    return chat_data


def _log_enrichment_errors(errors: List[str], context: str) -> None:
    """Log enrichment errors consistently across all export functions.
    
    Args:
        errors: List of error messages from enrichment
        context: Context string (e.g., filename) for log messages
    """
    for error in errors:
        logger.warning(f"Enrichment issue for {context}: {error}")


def _load_chat_data(
    file_path: Path,
    workspace_dir: Optional[Path] = None,
    execution_log_index: Optional[Dict[str, Path]] = None,
    use_execution_logs: bool = False,
    kiro_data_dir: Optional[Path] = None
) -> tuple[List[Dict[str, Any]], ChatSource, List[str]]:
    """Load chat data from either Claude JSONL or Kiro JSON file.
    
    For Kiro files, attempts to enrich bot messages with full responses
    from execution logs if workspace_dir is provided.
    
    Args:
        file_path: Path to the chat file
        workspace_dir: Optional workspace directory for Kiro execution log lookup
        execution_log_index: Optional pre-built index for faster lookups
        use_execution_logs: If True, use build_full_session_from_executions for Kiro
                           (recommended for wiki/book exports to get full conversations)
        kiro_data_dir: Path to kiro.kiroagent directory (required when use_execution_logs=True)
        
    Returns:
        Tuple of (chat_data, source, errors) where:
        - chat_data is a list of message dicts
        - source is the ChatSource enum
        - errors is a list of error messages (empty for Claude Desktop)
        
    Raises:
        ExportError: If file cannot be loaded
        
    Note:
        Callers should use _log_enrichment_errors() to log any returned errors
        for consistent error reporting across the codebase.
    """
    errors = []
    
    try:
        # Detect source using both extension and content
        source = _detect_chat_source(file_path)
        
        if source == ChatSource.KIRO_IDE:
            # Parse Kiro chat file to get session data
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Determine kiro_data_dir if not provided
            if kiro_data_dir is None and workspace_dir is not None:
                # workspace_dir is typically workspace-sessions/<encoded-path>
                # kiro_data_dir is the parent kiro.kiroagent directory
                inferred_dir = workspace_dir.parent.parent
                
                # Validate the inferred directory exists and looks like kiro.kiroagent
                if inferred_dir.exists() and inferred_dir.name == 'kiro.kiroagent':
                    kiro_data_dir = inferred_dir
                elif inferred_dir.exists():
                    # Check if it contains hash-named directories (execution logs)
                    from .kiro_parser import find_execution_log_dirs
                    if find_execution_log_dirs(inferred_dir):
                        kiro_data_dir = inferred_dir
                    else:
                        errors.append(
                            f"Inferred kiro_data_dir '{inferred_dir}' does not contain execution logs. "
                            f"Full conversation extraction may not work."
                        )
                else:
                    errors.append(
                        f"Inferred kiro_data_dir '{inferred_dir}' does not exist. "
                        f"Full conversation extraction may not work."
                    )
            
            # Use execution logs directly for wiki/book exports (full conversations)
            if use_execution_logs and kiro_data_dir is not None:
                messages, exec_errors = build_full_session_from_executions(
                    session_data,
                    kiro_data_dir,
                    execution_log_index=execution_log_index,
                    include_tool_details=False
                )
                errors.extend(exec_errors)
                
                if messages:
                    chat_data = _convert_kiro_to_dict(messages)
                    return chat_data, ChatSource.KIRO_IDE, errors
                else:
                    # Fall back to enriched extraction if no messages from execution logs
                    errors.append("No messages from execution logs, falling back to session history")
            
            # Fall back to enriched extraction (for simple exports or when execution logs unavailable)
            session = parse_kiro_chat_file(file_path)
            
            # Determine workspace directory if not provided
            if workspace_dir is None:
                workspace_dir = file_path.parent
                
            # Validate workspace directory contains execution logs
            from .kiro_parser import find_execution_log_dirs
            exec_log_dirs = find_execution_log_dirs(workspace_dir)
            if not exec_log_dirs and session.execution_id:
                errors.append(
                    f"No execution log directories found in {workspace_dir}. "
                    f"Bot responses may not be enriched."
                )
            
            # Use enriched extraction to get full bot responses
            messages, enrich_errors = extract_kiro_messages_enriched(
                {
                    'chat': session.messages,
                    'executionId': session.execution_id,
                    'context': session.context
                },
                workspace_dir=workspace_dir,
                execution_log_index=execution_log_index
            )
            errors.extend(enrich_errors)
            
            # Log errors but continue with available data
            for error in enrich_errors:
                logger.warning(f"Kiro enrichment issue for {file_path.name}: {error}")
            
            chat_data = _convert_kiro_to_dict(messages)
            return chat_data, ChatSource.KIRO_IDE, errors
        else:
            # Parse Claude Desktop JSONL file
            chat_data = parse_jsonl_file(file_path)
            return chat_data, ChatSource.CLAUDE_DESKTOP, errors
            
    except (FileNotFoundError, PermissionError) as e:
        raise ExportError(f"Cannot access file {file_path}: {e}")
    except json.JSONDecodeError as e:
        raise ExportError(f"Invalid JSON in {file_path}: {e}")
    except Exception as e:
        raise ExportError(f"Failed to load chat data from {file_path}: {e}")


def _generate_filename_from_content(chat_data: List[Dict[str, Any]], fallback: str, source: ChatSource) -> str:
    """Generate filename from chat content (session title or first message).
    
    Args:
        chat_data: Parsed chat data
        fallback: Fallback filename if content extraction fails
        source: Source of the chat
        
    Returns:
        Sanitized filename (without extension)
    """
    import re
    import unicodedata
    
    title = None
    
    # Extract first user message
    for entry in chat_data:
        message = entry.get('message', {})
        role = message.get('role', '')
        
        if role in ('user', 'human'):
            content = message.get('content', '')
            if isinstance(content, str) and content.strip():
                # Use first line or first 60 chars
                first_line = content.split('\n')[0]
                title = first_line[:60].strip()
                if len(first_line) > 60:
                    title += "..."
                break
    
    # Use fallback if no title found
    if not title:
        title = fallback
    
    # Normalize Unicode to ASCII (remove accents, convert to closest ASCII)
    title = unicodedata.normalize('NFKD', title)
    title = title.encode('ascii', 'ignore').decode('ascii')
    
    # Sanitize filename (remove special chars, limit length)
    # Keep only ASCII alphanumeric, spaces, hyphens, underscores
    sanitized = re.sub(r'[^a-zA-Z0-9\s\-_]', '', title)
    sanitized = re.sub(r'[-\s]+', '-', sanitized)
    sanitized = sanitized.strip('-_')
    
    # Limit to 100 chars for filesystem compatibility
    if len(sanitized) > 100:
        sanitized = sanitized[:100].rstrip('-_')
    
    # Make lowercase for consistency
    sanitized = sanitized.lower()
    
    # If sanitization resulted in empty string, use sanitized fallback
    if not sanitized:
        # Apply same sanitization to fallback
        fallback_normalized = unicodedata.normalize('NFKD', fallback)
        fallback_normalized = fallback_normalized.encode('ascii', 'ignore').decode('ascii')
        sanitized = re.sub(r'[^a-zA-Z0-9\s\-_]', '', fallback_normalized)
        sanitized = re.sub(r'[-\s]+', '-', sanitized)
        sanitized = sanitized.strip('-_').lower()
        
        # If still empty, use a default
        if not sanitized:
            sanitized = 'untitled'
    
    return sanitized


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


def export_chat_pretty(chat_data: List[Dict[str, Any]], verbose: bool = False) -> str:
    """Export chat in pretty terminal format with colors.

    Args:
        chat_data: Parsed chat data.
        verbose: Include additional metadata (execution IDs, context items).

    Returns:
        Formatted string ready for terminal display.
    """
    output_lines = []
    
    # Add verbose metadata header if present
    if verbose and chat_data:
        first_entry = chat_data[0]
        if 'execution_id' in first_entry:
            output_lines.append(f'{Colors.CYAN}Execution ID: {first_entry["execution_id"]}{Colors.NC}')
        if 'context_items' in first_entry and first_entry['context_items']:
            output_lines.append(f'{Colors.CYAN}Context Items: {len(first_entry["context_items"])} items{Colors.NC}')
        if output_lines:
            output_lines.append('─' * 80)
    
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
        
        # Add verbose metadata for this message
        if verbose:
            if 'execution_id' in entry:
                output_lines.append(f'{Colors.CYAN}🔑 Execution ID: {entry["execution_id"]}{Colors.NC}')
            if 'context_items' in entry and entry['context_items']:
                output_lines.append(f'{Colors.CYAN}📎 Context Items: {len(entry["context_items"])} items{Colors.NC}')
        
        output_lines.append(f'💬 {formatted_content}')
        output_lines.append('─' * 80)

    return '\n'.join(output_lines)


def export_chat_markdown(chat_data: List[Dict[str, Any]], verbose: bool = False) -> str:
    """Export chat in standard markdown format.

    Args:
        chat_data: Parsed chat data.
        verbose: Include additional metadata (execution IDs, context items).

    Returns:
        Markdown formatted string.
    """
    output_lines = []
    output_lines.append('# Claude Chat Export\n')
    output_lines.append(f'**Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**\n')
    
    # Add verbose metadata header if present
    if verbose and chat_data:
        first_entry = chat_data[0]
        if 'execution_id' in first_entry:
            output_lines.append(f'**Execution ID:** `{first_entry["execution_id"]}`\n')
        if 'context_items' in first_entry and first_entry['context_items']:
            output_lines.append(f'**Context Items:** {len(first_entry["context_items"])} items\n')
        output_lines.append('\n')

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
        
        # Add verbose metadata for this message
        if verbose:
            if 'execution_id' in entry:
                output_lines.append(f'**Execution ID:** `{entry["execution_id"]}`\n\n')
            if 'context_items' in entry and entry['context_items']:
                output_lines.append(f'**Context Items:** {len(entry["context_items"])} items\n\n')
        
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

        # Skip system messages - handle both Claude and Kiro role names
        if role not in ('user', 'assistant', 'human', 'bot'):
            continue
        
        # Normalize role names for consistent handling
        is_user = role in ('user', 'human')
        is_assistant = role in ('assistant', 'bot')

        # Extract clean content (filter tool noise if configured)
        if config.book_filter_tool_noise:
            text, files = chat_filter.extract_clean_content(content, include_tool_use=False)
        else:
            # Use standard formatting if tool noise filtering is disabled
            text = format_content(content, role)
            files = []

        # For user messages, clean system tags
        if is_user:
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

        elif is_assistant:
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
    sanitize: Optional[bool] = None,
    verbose: bool = False,
    workspace_dir: Optional[Path] = None
) -> None:
    """Export a chat file to specified format and save to file.
    
    Supports both Claude Desktop JSONL and Kiro IDE JSON/chat files.
    For Kiro files, attempts to enrich bot messages with full responses
    from execution logs.

    Args:
        file_path: Path to the chat file (JSONL or .chat/.json).
        output_path: Path where to save the export.
        format_type: Export format (pretty, markdown, book, raw).
        sanitize: Override .env sanitization setting (True/False/None).
        verbose: Include additional metadata (execution IDs, context items).
        workspace_dir: Optional workspace directory for Kiro execution log lookup.

    Raises:
        ExportError: If export operation fails.
    """
    try:
        chat_data, source, errors = _load_chat_data(file_path, workspace_dir=workspace_dir)
        
        # Report any enrichment errors using standardized logging
        _log_enrichment_errors(errors, file_path.name)

        if format_type == 'markdown':
            content = export_chat_markdown(chat_data, verbose=verbose)
        elif format_type == 'book':
            content = export_chat_book(chat_data, sanitize=sanitize)
        elif format_type == 'pretty':
            content = export_chat_pretty(chat_data, verbose=verbose)
        elif format_type == 'raw':
            import json
            content = '\n'.join(json.dumps(entry, indent=2) for entry in chat_data)
        else:
            raise ExportError(f"Unknown format type: {format_type}")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Exported {source.value} chat to {output_path} in {format_type} format")

    except Exception as e:
        raise ExportError(f"Failed to export chat: {e}")


def export_project_chats(
    project_path: Path,
    export_dir: Path,
    format_type: str = 'markdown',
    api_key: Optional[str] = None,
    sanitize: Optional[bool] = None,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP
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
        source: Chat source type (Claude Desktop or Kiro IDE).

    Returns:
        List of exported file paths.

    Raises:
        ExportError: If export operation fails.
    """
    try:
        # Create export directory
        os.makedirs(export_dir, exist_ok=True)

        # Get chat files based on source type
        if source == ChatSource.KIRO_IDE:
            chat_files = [f for f in project_path.glob('*.json') if f.name != 'sessions.json']
        else:
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

        # Build execution log index for Kiro files (for faster lookups)
        execution_log_index = None
        kiro_data_dir = None
        use_execution_logs = format_type in ('book', 'wiki') and source == ChatSource.KIRO_IDE
        
        if source == ChatSource.KIRO_IDE:
            # project_path is typically workspace-sessions/<encoded-path>
            # kiro_data_dir is the parent kiro.kiroagent directory
            kiro_data_dir = project_path.parent.parent
            
            # Validate kiro_data_dir
            if kiro_data_dir.exists():
                execution_log_index = build_execution_log_index(kiro_data_dir)
            else:
                logger.warning(f"kiro_data_dir not found: {kiro_data_dir}")

        for chat_file in chat_files:
            # Parse chat data for filtering and title generation
            try:
                # Use _load_chat_data for consistent parsing and conversion
                chat_data, detected_source, errors = _load_chat_data(
                    chat_file,
                    workspace_dir=project_path,
                    execution_log_index=execution_log_index,
                    use_execution_logs=use_execution_logs,
                    kiro_data_dir=kiro_data_dir
                )
                
                # Log enrichment errors using standardized logging
                _log_enrichment_errors(errors, chat_file.name)
                    
            except Exception as e:
                logger.warning(f"Failed to parse chat file {chat_file.name}: {e}, skipping")
                continue

            # Filter trivial chats for book format (only for Claude Desktop format)
            # Kiro dict format may have different structure that filter doesn't handle well
            if chat_filter and source != ChatSource.KIRO_IDE and chat_filter.is_pointless_chat(chat_data):
                logger.info(f"Filtering out trivial chat: {chat_file.name}")
                filtered_count += 1
                continue

            # Generate filename
            if format_type == 'book' and config.book_generate_titles:
                # Title generation works for both Claude Desktop and Kiro IDE formats
                filename = _generate_book_filename(
                    chat_data,
                    chat_file,
                    llm_client,
                    chat_filter
                )
            else:
                filename = chat_file.stem

            export_file = export_dir / f"{filename}.md"

            # Export using the already-parsed data to avoid re-parsing
            try:
                if format_type == 'markdown':
                    content = export_chat_markdown(chat_data)
                elif format_type == 'book':
                    content = export_chat_book(chat_data, sanitize=sanitize)
                else:
                    content = export_chat_markdown(chat_data)
                
                with open(export_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                exported_files.append(export_file)
            except Exception as e:
                logger.warning(f"Failed to export chat file {chat_file.name}: {e}, skipping")
                continue

        logger.info(f"Exported {len(exported_files)} chats to {export_dir}")
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} trivial chats")

        return exported_files

    except Exception as e:
        raise ExportError(f"Failed to export project chats: {e}")


def export_kiro_workspace(
    workspace_dir: Path,
    export_dir: Path,
    format_type: str = 'markdown',
    verbose: bool = False,
    sanitize: Optional[bool] = None,
    kiro_data_dir: Optional[Path] = None
) -> List[Path]:
    """Export all sessions in a Kiro workspace to a directory.
    
    For wiki/book formats, uses execution logs directly to get full conversations
    instead of the abbreviated session history.
    
    Args:
        workspace_dir: Path to the Kiro workspace-sessions subdirectory.
        export_dir: Directory where to save exports.
        format_type: Export format (markdown, book, pretty).
        verbose: Include additional metadata (execution IDs, context items).
        sanitize: Override .env sanitization setting (True/False/None).
        kiro_data_dir: Path to kiro.kiroagent directory (for execution logs).
        
    Returns:
        List of exported file paths.
        
    Raises:
        ExportError: If export operation fails.
    """
    try:
        from .kiro_projects import list_kiro_sessions
        
        # Create export directory
        os.makedirs(export_dir, exist_ok=True)
        
        # Get all sessions in this workspace
        sessions = list_kiro_sessions(workspace_dir)
        exported_files = []
        
        logger.info(f"Exporting {len(sessions)} Kiro sessions from workspace")
        
        # Determine kiro_data_dir if not provided
        # workspace_dir is typically workspace-sessions/<encoded-path>
        # kiro_data_dir is the parent kiro.kiroagent directory
        if kiro_data_dir is None:
            kiro_data_dir = workspace_dir.parent.parent
        
        # Build execution log index for faster lookups (from kiro_data_dir, not workspace_dir)
        execution_log_index = build_execution_log_index(kiro_data_dir)
        
        # Use execution logs for wiki/book formats to get full conversations
        use_execution_logs = format_type in ('book', 'wiki')
        
        for session in sessions:
            chat_file = session.chat_file_path
            
            # Skip if chat file doesn't exist
            if not chat_file.exists():
                logger.warning(f"Chat file not found: {chat_file}")
                continue
            
            try:
                # Load chat data with execution logs for wiki/book formats
                chat_data, source, errors = _load_chat_data(
                    chat_file,
                    workspace_dir=workspace_dir,
                    execution_log_index=execution_log_index,
                    use_execution_logs=use_execution_logs,
                    kiro_data_dir=kiro_data_dir
                )
                
                # Log enrichment errors using standardized logging
                _log_enrichment_errors(errors, chat_file.name)
                
                # Generate filename from session title or content
                filename = _generate_filename_from_content(
                    chat_data,
                    fallback=session.session_id[:8],
                    source=source
                )
                
                export_file = export_dir / f"{filename}.md"
                
                # Export the chat
                if format_type == 'markdown':
                    content = export_chat_markdown(chat_data, verbose=verbose)
                elif format_type == 'book':
                    content = export_chat_book(chat_data, sanitize=sanitize)
                elif format_type == 'pretty':
                    content = export_chat_pretty(chat_data, verbose=verbose)
                else:
                    content = export_chat_markdown(chat_data, verbose=verbose)
                
                with open(export_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                exported_files.append(export_file)
                
            except Exception as e:
                logger.error(f"Failed to export session {session.session_id}: {e}")
                continue
        
        logger.info(f"Exported {len(exported_files)} Kiro sessions to {export_dir}")
        return exported_files
        
    except Exception as e:
        raise ExportError(f"Failed to export Kiro workspace: {e}")


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
        # Fallback to file modification time for Kiro (no per-message timestamps)
        if not chat_date:
            try:
                from datetime import datetime
                mtime = chat_file.stat().st_mtime
                chat_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
            except Exception:
                pass
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
    
    Supports both Claude Desktop JSONL and Kiro IDE JSON/chat files.
    Generates descriptive filename for book format using same logic as batch export.
    Saves to current directory by default or specified output directory.

    Args:
        chat_file: Path to the chat file (JSONL or .chat/.json) to export.
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

        # Load chat data and determine source
        # For single chat export, infer workspace_dir from file location
        workspace_dir = chat_file.parent
        chat_data, source, errors = _load_chat_data(chat_file, workspace_dir=workspace_dir)
        
        # Log enrichment errors using standardized logging
        _log_enrichment_errors(errors, chat_file.name)

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
            # Use session title or first message for filename
            filename = _generate_filename_from_content(
                chat_data,
                fallback=chat_file.stem,
                source=source
            )

        output_file = output_dir / f"{filename}.md"

        # Export the file
        export_chat_to_file(chat_file, output_file, format_type)

        logger.info(f"Exported single {source.value} chat to {output_file}")
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

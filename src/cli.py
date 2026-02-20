"""Command-line interface implementation.

This module handles the interactive browser and command-line operations.
"""

import os
import socket
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

from .config import config
from .colors import Colors, print_colored
from .models import ProjectInfo, ChatSource
from .projects import (
    list_all_projects,
    find_project_by_name,
    search_projects_by_name,
    get_recent_projects,
    get_project_chat_files
)
from .search import search_chat_content
from .parser import parse_jsonl_file, count_messages_in_file, count_codex_messages_in_file
from .exporters import (
    export_chat_pretty,
    export_chat_to_file,
    export_project_chats,
    export_single_chat
)
from .display import display_with_pager
from .formatters import clean_project_name, sanitize_for_filename
from .exceptions import ProjectNotFoundError, ChatFileNotFoundError
from .models import ChatSource

logger = logging.getLogger(__name__)


def _source_label(source: ChatSource) -> str:
    """Return display label for a chat source.

    Args:
        source: ChatSource enum value.

    Returns:
        Formatted source label string with consistent width.
    """
    if source == ChatSource.CLAUDE_DESKTOP:
        return "[Claude]"
    elif source == ChatSource.CODEX:
        return "[Codex] "
    elif source == ChatSource.KIRO_IDE:
        return "[Kiro]  "
    return "[?]     "


def get_export_dirname(project_name: str, export_type: str) -> str:
    """Generate export directory name with machine hostname and project name.

    Creates directory names in format:
        hostname-Project_Name-type-YYYYMMDD_HHMMSS

    Uses underscores for spaces in project name to maintain readability.

    Examples:
        MacBook-Air-Michael-Learn_Telegram_Bot-book-20251109_103654
        MacBook-Air-Michael-Claude_Chat_Manager-markdown-20251109_103654

    Args:
        project_name: Name of the project being exported.
        export_type: Type of export ('book' or 'markdown').

    Returns:
        Directory name string.
    """
    import re

    # Get and sanitize hostname (removes .local, converts spaces to hyphens)
    hostname = socket.gethostname()
    hostname = sanitize_for_filename(hostname)

    # Sanitize project name: replace spaces with underscores
    # Remove leading dash if present (from directory name format like "-Users-mike-src-project")
    project_clean = project_name.lstrip('-')

    # Replace spaces with underscores for project name
    project_sanitized = project_clean.replace(' ', '_')

    # Remove special characters but keep underscores and hyphens
    project_sanitized = re.sub(r'[^\w-]', '', project_sanitized)

    # Collapse multiple consecutive underscores or hyphens
    project_sanitized = re.sub(r'_+', '_', project_sanitized)
    project_sanitized = re.sub(r'-+', '-', project_sanitized)

    # Remove leading/trailing underscores or hyphens
    project_sanitized = project_sanitized.strip('-_')

    # Generate timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Combine components
    return f"{hostname}-{project_sanitized}-{export_type}-{timestamp}"


def display_projects_list(source_filter: Optional[ChatSource] = None) -> None:
    """Display list of all available projects.
    
    Args:
        source_filter: Filter by source (None = all sources).
    """
    try:
        projects = list_all_projects(source_filter)

        # Determine title based on filter
        if source_filter == ChatSource.CLAUDE_DESKTOP:
            title = "📁 Available Claude Desktop Projects"
        elif source_filter == ChatSource.KIRO_IDE:
            title = "📁 Available Kiro IDE Projects"
        elif source_filter == ChatSource.CODEX:
            title = "📁 Available Codex CLI Projects"
        else:
            title = "📁 Available Projects (All Sources)"
        
        print_colored(title, Colors.BLUE)
        print("=" * 60)

        if not projects:
            print_colored("No projects with chat files found", Colors.YELLOW)
            return

        print_colored("Source   Project Name                 Chats  Messages   Last Modified", Colors.CYAN)
        print("-" * 80)

        for info in projects:
            source_label = _source_label(info.source)
            print(f"{source_label} {info.name:<28} {info.file_count:>5}  {info.total_messages:>8}   {info.last_modified}")

    except ProjectNotFoundError as e:
        print_colored(f"❌ {e.message}", Colors.RED)
        logger.error(f"Projects directory not found: {e}")


def display_search_results(search_term: str, source_filter: Optional[ChatSource] = None) -> None:
    """Display search results for project names.

    Args:
        search_term: The term to search for.
        source_filter: Filter by source (None = all sources).
    """
    print_colored(f"🔍 Searching for projects containing: '{search_term}'", Colors.BLUE)
    print("=" * 60)

    found_projects = search_projects_by_name(search_term, source_filter)

    if not found_projects:
        print_colored(f"No projects found matching '{search_term}'", Colors.YELLOW)
        return

    for info in found_projects:
        source_label = _source_label(info.source)
        print_colored(f"✅ {source_label} {info.name}", Colors.GREEN)
        print(f"   {info.file_count} chats, {info.total_messages} messages, modified: {info.last_modified}")


def display_content_search(search_term: str, source_filter: Optional[ChatSource] = None) -> None:
    """Display content search results.

    Args:
        search_term: The term to search for in chat content.
        source_filter: Filter by source (None = all sources).
    """
    print_colored(f"🔍 Searching chat content for: '{search_term}'", Colors.BLUE)
    print("=" * 60)

    results = search_chat_content(search_term, source_filter)

    if not results:
        print_colored(f"No content found matching '{search_term}'", Colors.YELLOW)
        return

    for result in results:
        print_colored(f"📝 Found in: {result.project_name}/{result.chat_name}", Colors.GREEN)
        print(f"   Line {result.line_number} ({result.role}): {result.preview}")
        print()


def display_recent_projects(count: int = 10, source_filter: Optional[ChatSource] = None) -> None:
    """Display most recent projects.

    Args:
        count: Number of recent projects to show.
        source_filter: Filter by source (None = all sources).
    """
    print_colored(f"⏰ {count} Most Recently Modified Projects", Colors.BLUE)
    print("=" * 60)

    projects = get_recent_projects(count, source_filter)

    if not projects:
        print_colored("No projects found", Colors.YELLOW)
        return

    for info in projects:
        source_label = _source_label(info.source)
        print_colored(f"📝 {source_label} {info.name}", Colors.GREEN)
        print(f"   {info.file_count} chats, {info.total_messages} messages, {info.last_modified}")


def view_chat_file(file_path: Path, format_type: str = 'pretty', output_file: Optional[Path] = None) -> None:
    """View a specific chat file.

    Args:
        file_path: Path to the chat file.
        format_type: Output format (pretty, markdown, book, raw).
        output_file: Optional output file path.
    """
    try:
        chat_data = parse_jsonl_file(file_path)

        if not chat_data:
            print_colored('No valid messages found', Colors.YELLOW)
            return

        if format_type == 'pretty':
            content = export_chat_pretty(chat_data)

            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print_colored(f'Chat exported to: {output_file}', Colors.GREEN)
            else:
                title = f"💬 Viewing: {file_path.name}"
                display_with_pager(content, title)
        else:
            export_chat_to_file(file_path, output_file or Path('-'), format_type)

    except (ChatFileNotFoundError, Exception) as e:
        print_colored(f"❌ Error viewing chat: {e}", Colors.RED)
        logger.error(f"Error viewing chat file {file_path}: {e}")


def browse_project_interactive(project_info: ProjectInfo) -> bool:
    """Browse a project interactively.

    Args:
        project_info: ProjectInfo object containing project details and source.

    Returns:
        True to return to main menu, False to quit.
    """
    # Use project_info.name directly (already cleaned/decoded for Kiro/Codex projects)
    # For Claude Desktop, clean_project_name handles the path-based name
    if project_info.source in (ChatSource.KIRO_IDE, ChatSource.CODEX):
        project_name = project_info.name
    else:
        project_name = clean_project_name(project_info.path.name)
    chat_files = get_project_chat_files(
        project_info.path, project_info.source,
        session_ids=project_info.session_ids
    )

    if not chat_files:
        if project_info.source == ChatSource.KIRO_IDE:
            file_type = ".json"
        elif project_info.source == ChatSource.CODEX:
            file_type = "rollout JSONL"
        else:
            file_type = "JSONL"
        print_colored(f"No {file_type} chat files found in project: {project_name}", Colors.YELLOW)
        return True

    def display_menu():
        """Display the project menu."""
        print_colored(f"💬 Project: {project_name}", Colors.BLUE)
        print("=" * 60)
        print_colored(f"Found {len(chat_files)} chat file(s):", Colors.CYAN)
        print()

        # Calculate maximum filename length for proper alignment
        max_filename_len = max((len(f.stem) for f in chat_files), default=36)
        max_filename_len = max(max_filename_len, 36)  # Minimum width for UUIDs

        for i, file_path in enumerate(chat_files, 1):
            filename = file_path.stem
            try:
                size = file_path.stat().st_size
                size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
                modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                if project_info.source == ChatSource.CODEX:
                    msg_count = count_codex_messages_in_file(file_path)
                else:
                    msg_count = count_messages_in_file(file_path)

                print(f"{i:2d}) {filename:<{max_filename_len}}  {size_str:>9}  {msg_count:>6} msgs {modified}")
            except Exception:
                print(f"{i:2d}) {filename:<{max_filename_len}}  {'error':>9}  {'?':>6} msgs {'unknown'}")

        print()
        print_colored("Choose an option:", Colors.YELLOW)
        print(f"  1-{len(chat_files)}) Select chat (view or export)")
        print("  a) View all chats")
        print("  e) Export all to markdown")
        print("  eb) Export all to book format")
        print("  b) Back to main menu")
        print("  q) Quit")
        print()

    display_menu()

    while True:
        try:
            choice = input("Enter choice: ").strip()

            if choice.lower() in ['q', 'quit']:
                return False
            elif choice.lower() == 'b':
                return True
            elif choice.lower() == 'a':
                for file_path in chat_files:
                    print()
                    print_colored("=" * 60, Colors.CYAN)
                    view_chat_file(file_path)
                    print()
                    next_input = input("Press Enter for next chat (or 'q' to stop)...")
                    if next_input.lower() == 'q':
                        break
                return True
            elif choice.lower() == 'e':
                export_dir = Path(get_export_dirname(project_name, 'markdown'))
                print_colored(f"📤 Exporting all chats to markdown in: {export_dir}", Colors.BLUE)

                exported_files = export_project_chats(project_info.path, export_dir, 'markdown', source=project_info.source)

                print_colored(f"✅ All chats exported to: {export_dir}/", Colors.GREEN)
                for file in exported_files:
                    size = file.stat().st_size
                    print(f"   {file.name} ({size/1024:.1f}KB)")
                return True
            elif choice.lower() == 'eb':
                export_dir = Path(get_export_dirname(project_name, 'book'))
                print_colored(f"📚 Exporting all chats to book format in: {export_dir}", Colors.BLUE)

                exported_files = export_project_chats(project_info.path, export_dir, 'book', source=project_info.source)

                print_colored(f"✅ All chats exported to book format: {export_dir}/", Colors.GREEN)
                for file in exported_files:
                    size = file.stat().st_size
                    print(f"   {file.name} ({size/1024:.1f}KB)")
                return True
            elif choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(chat_files):
                    selected_file = chat_files[choice_num - 1]

                    # Show action menu
                    print()
                    print_colored(f"Selected: {selected_file.name}", Colors.CYAN)
                    print()
                    print_colored("What would you like to do?", Colors.YELLOW)
                    print("  1) View in terminal")
                    print("  2) Export to markdown")
                    print("  3) Export to book format")
                    print("  4) Cancel (back to chat list)")
                    print()

                    action_choice = input("Enter choice: ").strip()

                    if action_choice == '1':
                        # View chat
                        view_chat_file(selected_file)
                        print()
                        input("Press Enter to continue...")
                        print()
                        display_menu()
                    elif action_choice == '2':
                        # Export to markdown
                        try:
                            output_file = export_single_chat(selected_file, 'markdown')
                            size = output_file.stat().st_size
                            print_colored(f"✅ Exported to: {output_file} ({size/1024:.1f}KB)", Colors.GREEN)
                        except Exception as e:
                            print_colored(f"❌ Export failed: {e}", Colors.RED)
                        print()
                        input("Press Enter to continue...")
                        print()
                        display_menu()
                    elif action_choice == '3':
                        # Export to book format
                        try:
                            output_file = export_single_chat(selected_file, 'book')
                            size = output_file.stat().st_size
                            print_colored(f"✅ Exported to: {output_file} ({size/1024:.1f}KB)", Colors.GREEN)
                        except Exception as e:
                            print_colored(f"❌ Export failed: {e}", Colors.RED)
                        print()
                        input("Press Enter to continue...")
                        print()
                        display_menu()
                    elif action_choice == '4':
                        # Cancel - redisplay menu
                        print()
                        display_menu()
                    else:
                        print_colored("Invalid choice", Colors.RED)
                        print()
                        display_menu()
                else:
                    print_colored(f"Invalid selection. Please choose 1-{len(chat_files)}", Colors.RED)
            else:
                print_colored("Invalid choice. Please enter a number, 'a', 'e', 'eb', 'b', or 'q'", Colors.RED)

        except (KeyboardInterrupt, EOFError):
            print()
            return False


def interactive_browser(source_filter: Optional[ChatSource] = None) -> None:
    """Run the interactive project browser.
    
    Args:
        source_filter: Filter by source (None = all sources).
    """
    # Main loop to avoid recursion when switching sources or returning from submenus
    while True:
        try:
            projects = list_all_projects(source_filter)
        except ProjectNotFoundError as e:
            print_colored(f"❌ {e.message}", Colors.RED)
            print("Make sure you have Claude Desktop installed and have created projects.")
            return

        if not projects:
            print_colored(f"No projects with chat files found", Colors.YELLOW)
            return

        # Sort by last modified (most recent first)
        projects.sort(key=lambda x: x.last_modified, reverse=True)

        # Determine title based on current filter
        if source_filter == ChatSource.CLAUDE_DESKTOP:
            title = "🤖 Claude Desktop Chat Browser"
        elif source_filter == ChatSource.KIRO_IDE:
            title = "🤖 Kiro IDE Chat Browser"
        elif source_filter == ChatSource.CODEX:
            title = "🤖 Codex CLI Chat Browser"
        else:
            title = "🤖 Chat Browser (All Sources)"
        
        print_colored(title, Colors.BLUE)
        print("=" * 60)
        print()
        print_colored("Available projects:", Colors.CYAN)
        print()

        for i, info in enumerate(projects, 1):
            source_label = _source_label(info.source)
            name_col = f"{i:2d}) {source_label} {info.name}"
            details_col = f"({info.file_count} chats, {info.total_messages} msgs, {info.last_modified})"

            if len(name_col) < 48:
                padding = 48 - len(name_col)
                print(f"{name_col}{' ' * padding}{details_col}")
            else:
                print(f"{name_col}")
                print(f"{'':>50}{details_col}")

        print()
        print_colored("Options:", Colors.YELLOW)
        print(f"  1-{len(projects)}) Browse specific project")
        print("  l) List all projects with details")
        print("  r) Show recent projects")
        print("  c) Search chat content")
        print("  s) Switch source filter")
        print("  q) Quit")
        print()

        # Inner loop for handling menu choices
        menu_active = True
        while menu_active:
            try:
                choice = input("Enter choice: ").strip()

                if choice.lower() in ['q', 'quit']:
                    print_colored("👋 Goodbye!", Colors.BLUE)
                    return
                elif choice.lower() == 's':
                    # Switch source filter
                    print()
                    print_colored("Select source:", Colors.YELLOW)
                    print("  1) Claude Desktop only")
                    print("  2) Kiro IDE only")
                    print("  3) Codex CLI only")
                    print("  4) All sources")
                    print()
                    source_choice = input("Enter choice (1-4): ").strip()
                    
                    if source_choice == '1':
                        source_filter = ChatSource.CLAUDE_DESKTOP
                        print_colored("Switched to Claude Desktop only", Colors.GREEN)
                    elif source_choice == '2':
                        source_filter = ChatSource.KIRO_IDE
                        print_colored("Switched to Kiro IDE only", Colors.GREEN)
                    elif source_choice == '3':
                        source_filter = ChatSource.CODEX
                        print_colored("Switched to Codex CLI only", Colors.GREEN)
                    elif source_choice == '4':
                        source_filter = None
                        print_colored("Switched to all sources", Colors.GREEN)
                    else:
                        print_colored("Invalid choice, keeping current filter", Colors.RED)
                    
                    print()
                    input("Press Enter to continue...")
                    # Break inner loop to refresh project list with new filter
                    menu_active = False
                elif choice.lower() == 'l':
                    print()
                    display_projects_list(source_filter)
                    print()
                    input("Press Enter to continue...")
                    # Break inner loop to redisplay menu
                    menu_active = False
                elif choice.lower() == 'r':
                    print()
                    display_recent_projects(10, source_filter)
                    print()
                    input("Press Enter to continue...")
                    # Break inner loop to redisplay menu
                    menu_active = False
                elif choice.lower() == 'c':
                    search_term = input("Enter search term: ").strip()
                    if search_term:
                        print()
                        display_content_search(search_term, source_filter)
                        print()
                        input("Press Enter to continue...")
                    # Break inner loop to redisplay menu
                    menu_active = False
                elif choice.isdigit():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(projects):
                        print()
                        should_continue = browse_project_interactive(projects[choice_num - 1])
                        if should_continue:
                            print()
                            # Break inner loop to redisplay menu
                            menu_active = False
                        else:
                            # User quit from project browser
                            return
                    else:
                        print_colored(f"Invalid selection. Please choose 1-{len(projects)}", Colors.RED)
                else:
                    print_colored("Invalid choice. Please enter a number, 'l', 'r', 'c', 's', or 'q'", Colors.RED)

            except (KeyboardInterrupt, EOFError):
                print()
                print_colored("👋 Goodbye!", Colors.BLUE)
                return

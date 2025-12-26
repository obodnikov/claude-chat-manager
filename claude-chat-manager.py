#!/usr/bin/env python3
"""Claude Chat Manager - Main entry point.

A powerful Python tool to browse, read, and export Claude Desktop's JSONL
chat files with an intuitive interface and Unix less-like paging.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.cli import (
    interactive_browser,
    display_projects_list,
    display_search_results,
    display_content_search,
    display_recent_projects,
    browse_project_interactive,
    view_chat_file
)
from src.projects import find_project_by_name
from src.colors import print_colored, Colors
from src.exceptions import ProjectNotFoundError, ExportError


def perform_sanitize_preview(args: argparse.Namespace, project_path: Path) -> None:
    """Perform sanitization preview on a project.

    Args:
        args: Parsed command-line arguments.
        project_path: Path to the project directory.

    Raises:
        ExportError: If preview operation fails.
    """
    from src.sanitizer import Sanitizer
    from src.parser import parse_jsonl_file

    print_colored("🔍 Sanitization Preview Mode", Colors.CYAN)
    print_colored("=" * 60, Colors.CYAN)

    # Initialize sanitizer with CLI settings or .env defaults
    sanitizer = Sanitizer(
        level=args.sanitize_level,
        style=args.sanitize_style,
        sanitize_paths=args.sanitize_paths
    )

    # Get all chat files
    chat_files = list(project_path.glob('*.jsonl'))
    if not chat_files:
        print_colored(f"⚠️  No chat files found in project '{args.project}'", Colors.YELLOW)
        sys.exit(0)

    total_matches = 0
    files_with_secrets = 0
    files_scanned = 0
    files_skipped = 0

    print(f"\nScanning {len(chat_files)} chat file(s) in project '{args.project}'...")
    print(f"Configuration:")
    print(f"  Level: {sanitizer.level}")
    print(f"  Style: {sanitizer.style}")
    print(f"  Sanitize paths: {sanitizer.sanitize_paths}")
    print()

    for chat_file in chat_files:
        try:
            chat_data = parse_jsonl_file(chat_file)
            files_scanned += 1

            # Combine all text from chat
            # Check both 'text' and 'content' fields to handle variations
            all_text = []
            for entry in chat_data:
                message = entry.get('message', {})
                if message:
                    # Get text from either 'text' or 'content' field
                    text = message.get('text') or message.get('content', '')
                    if text and isinstance(text, str):
                        all_text.append(text)
                    # Also check tool use content
                    elif isinstance(text, list):
                        for item in text:
                            if isinstance(item, dict) and 'text' in item:
                                all_text.append(item['text'])

            if not all_text:
                continue

            combined_text = '\n'.join(all_text)
            matches = sanitizer.find_sensitive_data(combined_text)

            if matches:
                files_with_secrets += 1
                total_matches += len(matches)
                print_colored(f"📄 {chat_file.name}: {len(matches)} secret(s) found", Colors.YELLOW)

                # Show first few examples
                for i, match in enumerate(matches[:3]):
                    original = match.original_value
                    redacted = match.redacted_value
                    match_type = match.pattern_type

                    # Truncate long values for display
                    if len(original) > 50:
                        original_display = original[:25] + '...' + original[-22:]
                    else:
                        original_display = original

                    print(f"     {i+1}. [{match_type}] {original_display} → {redacted}")

                if len(matches) > 3:
                    print(f"     ... and {len(matches) - 3} more")
                print()

        except Exception as e:
            files_skipped += 1
            logging.warning(f"Failed to process {chat_file.name}: {e}")
            print_colored(f"⚠️  Skipped {chat_file.name}: {str(e)}", Colors.YELLOW)
            continue

    # Summary
    print_colored("=" * 60, Colors.CYAN)
    print_colored("📊 Summary", Colors.CYAN)
    print(f"Files scanned: {files_scanned}")
    if files_skipped > 0:
        print(f"Files skipped (errors): {files_skipped}")
    print(f"Files with secrets: {files_with_secrets}")
    print(f"Total secrets found: {total_matches}")
    print()

    if total_matches > 0:
        print_colored("⚠️  Sensitive data detected!", Colors.YELLOW)
        print("Use --sanitize flag to sanitize exports, or use sanitize-chats.py")
        print("to sanitize existing exported files.")
    else:
        print_colored("✅ No sensitive data detected", Colors.GREEN)


def setup_logging() -> None:
    """Configure logging for the application."""
    log_level = getattr(logging, config.log_level, logging.INFO)

    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'claude-chat-manager.log'

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    # Reduce noise from some loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def main() -> None:
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description='Claude Chat Manager - Browse and export Claude project chat files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Interactive project browser
  %(prog)s -l                        # List all projects
  %(prog)s -r 5                      # Show 5 most recent projects
  %(prog)s -s docker                 # Search for projects with 'docker' in name
  %(prog)s "my-project"              # Browse project interactively
  %(prog)s "my-project" -f book -o my-chats       # Export to directory 'my-chats/'
  %(prog)s "my-project" -f book -o exports/       # Export to 'exports/' directory
  %(prog)s "my-project" -f book -o chat.md        # Export to timestamped 'chat_YYYYMMDD_HHMMSS/' dir
  %(prog)s "my-project" --wiki project-wiki.md    # Generate wiki with AI titles
  %(prog)s "my-project" --wiki wiki.md --update   # Update existing wiki with new chats
  %(prog)s "my-project" --wiki wiki.md --rebuild  # Force full rebuild of existing wiki
  %(prog)s -c "update checker"                    # Search chat content

Sanitization Examples:
  %(prog)s "my-project" -f book -o exports/ --sanitize            # Enable sanitization
  %(prog)s "my-project" --wiki wiki.md --sanitize-preview         # Preview what would be sanitized
  %(prog)s "my-project" -f book -o exports/ --sanitize-level aggressive --sanitize-style labeled
  %(prog)s "my-project" -f book -o exports/ --sanitize --sanitize-report report.txt

Output Behavior:
  -o dirname       # Export to directory 'dirname/'
  -o dirname/      # Export to directory 'dirname/'
  -o file.md       # Export to timestamped 'file_YYYYMMDD_HHMMSS/' directory

Environment Variables:
  CLAUDE_PROJECTS_DIR    # Custom Claude projects directory
  CLAUDE_LOG_LEVEL       # Logging level (DEBUG, INFO, WARNING, ERROR)
  CLAUDE_DEFAULT_FORMAT  # Default export format
  SANITIZE_ENABLED       # Enable sanitization (true/false)
  SANITIZE_LEVEL         # Sanitization level (minimal/balanced/aggressive/custom)
  SANITIZE_STYLE         # Redaction style (simple/stars/labeled/partial/hash)
        """
    )

    parser.add_argument('project', nargs='?', help='Project name to browse')
    parser.add_argument('-l', '--list', action='store_true', help='List all projects')
    parser.add_argument('-s', '--search', metavar='TERM', help='Search for projects containing TERM')
    parser.add_argument('-r', '--recent', metavar='N', type=int, nargs='?', const=10,
                        help='Show N most recently modified projects (default: 10)')
    parser.add_argument('-f', '--format', choices=['pretty', 'markdown', 'raw', 'book', 'wiki'],
                        default='pretty', help='Output format (default: pretty, book=clean markdown without timestamps, wiki=AI-generated single page)')
    parser.add_argument('-o', '--output', metavar='FILE', type=Path, help='Save output to file')
    parser.add_argument('-c', '--content', metavar='TERM', help='Search for content within chats')
    parser.add_argument('--wiki', metavar='FILE', type=Path, help='Generate wiki page from all project chats (shortcut for -f wiki -o FILE)')
    parser.add_argument('--update', action='store_true', help='Update existing wiki file with new chats (use with --wiki)')
    parser.add_argument('--rebuild', action='store_true', help='Force full rebuild of existing wiki file (use with --wiki)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')

    # Sanitization options
    sanitize_group = parser.add_argument_group('Sensitive Data Sanitization')
    sanitize_group.add_argument('--sanitize', action='store_true',
                               help='Enable sanitization of sensitive data (API keys, tokens, passwords, etc.)')
    sanitize_group.add_argument('--no-sanitize', action='store_true',
                               help='Disable sanitization (override .env setting)')
    sanitize_group.add_argument('--sanitize-level',
                               choices=['minimal', 'balanced', 'aggressive', 'custom'],
                               help='Sanitization detection level (default: from .env or balanced)')
    sanitize_group.add_argument('--sanitize-style',
                               choices=['simple', 'stars', 'labeled', 'partial', 'hash'],
                               help='Redaction style (default: from .env or partial)')
    sanitize_group.add_argument('--sanitize-paths', action='store_true',
                               help='Sanitize file paths (e.g., /Users/mike → /Users/[USER])')
    sanitize_group.add_argument('--sanitize-preview', action='store_true',
                               help='Preview what would be sanitized without exporting')
    sanitize_group.add_argument('--sanitize-report', metavar='FILE', type=Path,
                               help='Generate sanitization report to specified file')

    args = parser.parse_args()

    # Validate mutually exclusive sanitization options
    if args.sanitize and args.no_sanitize:
        parser.error("Cannot specify both --sanitize and --no-sanitize")

    # Determine sanitization setting (CLI overrides .env)
    sanitize_enabled = None
    if args.sanitize:
        sanitize_enabled = True
    elif args.no_sanitize:
        sanitize_enabled = False
    # else: None means use .env setting

    # Setup logging
    if args.verbose:
        config._load_config()  # Reload with verbose
        import os
        os.environ['CLAUDE_LOG_LEVEL'] = 'DEBUG'

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Claude Chat Manager starting...")

    # Check if Claude directory exists
    if not config.claude_projects_dir.exists():
        print_colored(f"❌ Claude projects directory not found: {config.claude_projects_dir}", Colors.RED)
        print("Make sure you have Claude Desktop installed and have created projects.")
        print("\nYou can set a custom directory with:")
        print("  export CLAUDE_PROJECTS_DIR=/path/to/your/projects")
        sys.exit(1)

    # Handle command line arguments
    try:
        if args.list:
            display_projects_list()
        elif args.search:
            display_search_results(args.search)
        elif args.content:
            display_content_search(args.content)
        elif args.recent is not None:
            display_recent_projects(args.recent)
        elif args.project:
            # Browse specific project
            project_path = find_project_by_name(args.project)

            if project_path and project_path.exists():
                # Handle sanitization preview mode
                if args.sanitize_preview:
                    perform_sanitize_preview(args, project_path)
                    sys.exit(0)

                # Handle wiki format specially
                wiki_output = args.wiki if args.wiki else (args.output if args.format == 'wiki' else None)

                if wiki_output:
                    # Wiki export mode - single file output
                    from src.exporters import export_project_wiki

                    # Check if file exists and handle accordingly
                    wiki_exists = wiki_output.exists()
                    mode = 'rebuild' if args.rebuild else ('update' if args.update else 'new')

                    if wiki_exists and mode == 'new':
                        # File exists but no --update or --rebuild flag
                        print_colored(f"⚠️  Wiki file already exists: {wiki_output}", Colors.YELLOW)
                        print(f"   Use '--wiki {wiki_output} --update' to add new chats to existing wiki")
                        print(f"   Use '--wiki {wiki_output} --rebuild' to regenerate the entire wiki")
                        print(f"   Or remove the file manually to create a new one\n")
                        response = input("Remove existing file and create new wiki? [y/N]: ").strip().lower()
                        if response not in ['y', 'yes']:
                            print_colored("Operation cancelled.", Colors.YELLOW)
                            sys.exit(0)
                        else:
                            wiki_output.unlink()
                            print_colored(f"Removed existing file. Creating new wiki...\n", Colors.BLUE)

                    logger.info(f"Generating wiki for project: {args.project} (mode: {mode})")

                    # Get API settings from config
                    use_llm = config.wiki_generate_titles
                    api_key = config.openrouter_api_key

                    if use_llm and not api_key:
                        print_colored("⚠️  Warning: OPENROUTER_API_KEY not set. Using fallback titles.", Colors.YELLOW)
                        print("   Set your API key in .env file to enable AI-generated titles.")
                        print("   Get your key at: https://openrouter.ai/keys\n")
                        use_llm = False

                    # Export wiki (pass mode for update/rebuild logic)
                    wiki_output.parent.mkdir(parents=True, exist_ok=True)
                    export_project_wiki(
                        project_path,
                        wiki_output,
                        use_llm,
                        api_key,
                        update_mode=mode,
                        sanitize=sanitize_enabled
                    )

                    size = wiki_output.stat().st_size
                    if mode == 'update':
                        print_colored(f"✅ Wiki updated: {wiki_output} ({size/1024:.1f}KB)", Colors.GREEN)
                    elif mode == 'rebuild':
                        print_colored(f"✅ Wiki rebuilt: {wiki_output} ({size/1024:.1f}KB)", Colors.GREEN)
                    else:
                        print_colored(f"✅ Wiki generated: {wiki_output} ({size/1024:.1f}KB)", Colors.GREEN)

                    if use_llm:
                        print(f"   Using AI-generated titles via {config.openrouter_model}")
                    else:
                        print("   Using first user question as titles")

                elif args.output:
                    # Non-interactive mode: export to file or directory
                    from src.exporters import export_project_chats
                    from src.formatters import clean_project_name

                    logger.info(f"Exporting project: {args.project} to {args.output}")

                    # Determine export directory
                    output_str = str(args.output)

                    # If output ends with / or is existing directory, use it directly
                    if output_str.endswith('/') or (args.output.exists() and args.output.is_dir()):
                        export_dir = args.output if args.output.is_dir() else Path(output_str.rstrip('/'))
                    else:
                        # If output looks like a filename (has extension), use its parent or create timestamped dir
                        if args.output.suffix:
                            # Has extension like .md - create timestamped directory from base name
                            from datetime import datetime
                            output_base = args.output.stem
                            export_dir = Path(f"{output_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        else:
                            # No extension - treat as directory name
                            export_dir = args.output

                    # Create directory and export
                    export_dir.mkdir(parents=True, exist_ok=True)
                    exported_files = export_project_chats(
                        project_path,
                        export_dir,
                        args.format,
                        sanitize=sanitize_enabled
                    )
                    print_colored(f"✅ Exported {len(exported_files)} chats to: {export_dir}/", Colors.GREEN)
                    for file in exported_files:
                        size = file.stat().st_size
                        print(f"   {file.name} ({size/1024:.1f}KB)")
                else:
                    # Interactive mode
                    browse_project_interactive(project_path)
            else:
                print_colored(f"Project not found: {args.project}", Colors.RED)
                print("Available projects:")
                display_projects_list()
                sys.exit(1)
        else:
            # Interactive browser
            interactive_browser()

    except KeyboardInterrupt:
        print()
        print_colored("👋 Goodbye!", Colors.BLUE)
        logger.info("Claude Chat Manager interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        print_colored(f"❌ Error: {e}", Colors.RED)
        sys.exit(1)


if __name__ == '__main__':
    main()

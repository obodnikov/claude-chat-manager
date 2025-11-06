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
from src.exceptions import ProjectNotFoundError


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

Output Behavior:
  -o dirname       # Export to directory 'dirname/'
  -o dirname/      # Export to directory 'dirname/'
  -o file.md       # Export to timestamped 'file_YYYYMMDD_HHMMSS/' directory

Environment Variables:
  CLAUDE_PROJECTS_DIR    # Custom Claude projects directory
  CLAUDE_LOG_LEVEL       # Logging level (DEBUG, INFO, WARNING, ERROR)
  CLAUDE_DEFAULT_FORMAT  # Default export format
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

    args = parser.parse_args()

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
                        update_mode=mode
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
                    exported_files = export_project_chats(project_path, export_dir, args.format)
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

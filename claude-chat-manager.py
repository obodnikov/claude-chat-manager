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

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('claude-chat-manager.log'),
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
  %(prog)s "my-project"              # View specific project chats
  %(prog)s "my-project" -f book      # View as clean book format
  %(prog)s "my-project" -f markdown  # View as markdown
  %(prog)s "my-project" -o chat.md   # Save to markdown file
  %(prog)s -c "update checker"       # Search chat content

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
    parser.add_argument('-f', '--format', choices=['pretty', 'markdown', 'raw', 'book'],
                        default='pretty', help='Output format (default: pretty, book=clean markdown without timestamps)')
    parser.add_argument('-o', '--output', metavar='FILE', type=Path, help='Save output to file')
    parser.add_argument('-c', '--content', metavar='TERM', help='Search for content within chats')
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
                if args.output or args.format != 'pretty':
                    # Non-interactive mode: just view/export
                    logger.info(f"Viewing project: {args.project}")
                    # For now, browse interactively
                    # TODO: Implement direct export mode
                    browse_project_interactive(project_path)
                else:
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
        sys.exit(0)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        print_colored(f"❌ Error: {e}", Colors.RED)
        sys.exit(1)

    logger.info("Claude Chat Manager exiting normally")


if __name__ == '__main__':
    main()

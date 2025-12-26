#!/usr/bin/env python3
"""Post-processing script for sanitizing sensitive data in exported chat files.

This standalone script sanitizes markdown files that have already been exported.
It supports interactive mode for manual review and batch mode for automatic
sanitization. Configuration is loaded from the .env file, same as integrated exports.

Usage:
    # Interactive mode - review each match
    python sanitize-chats.py exported-chats/ --interactive

    # Batch mode - auto-sanitize all matches
    python sanitize-chats.py exported-chats/

    # Preview mode - show what would be changed
    python sanitize-chats.py my-chat.md --preview

    # Custom settings
    python sanitize-chats.py chats/ --level aggressive --style labeled
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

# Add src directory to path for imports
# This is safe for a standalone script as it uses absolute path resolution
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR / 'src'
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from sanitizer import Sanitizer, SanitizationMatch, SanitizationReport
    from config import config
    from colors import Colors, print_colored
except ImportError as e:
    print(f"Error: Could not import required modules from 'src' directory.", file=sys.stderr)
    print(f"Make sure you're running this script from the project root directory.", file=sys.stderr)
    print(f"Import error: {e}", file=sys.stderr)
    sys.exit(1)


class BackupManager:
    """Manages backup file creation and restoration."""

    def __init__(self, create_backups: bool = True):
        """Initialize backup manager.

        Args:
            create_backups: Whether to create backup files.
        """
        self.create_backups = create_backups
        self.backups_created = []

    def create_backup(self, file_path: Path) -> Optional[Path]:
        """Create backup of file before modification.

        Args:
            file_path: Path to file to backup.

        Returns:
            Path to backup file, or None if backups disabled.
        """
        if not self.create_backups:
            return None

        # Create backup with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = file_path.parent / f"{file_path.stem}.{timestamp}.bak"

        try:
            shutil.copy2(file_path, backup_path)
            self.backups_created.append(backup_path)
            return backup_path
        except Exception as e:
            print_colored(f"⚠️  Warning: Could not create backup: {e}", Colors.YELLOW)
            return None

    def cleanup_backups(self) -> None:
        """Remove all created backups (used on error/cancel)."""
        for backup_path in self.backups_created:
            try:
                backup_path.unlink()
            except Exception:
                pass


class FileProcessor:
    """Handles file discovery and processing."""

    def __init__(self, sanitizer: Sanitizer, backup_manager: BackupManager):
        """Initialize file processor.

        Args:
            sanitizer: Configured sanitizer instance.
            backup_manager: Backup manager instance.
        """
        self.sanitizer = sanitizer
        self.backup_manager = backup_manager
        self.files_processed = 0
        self.files_modified = 0
        self.total_matches = 0

    def find_markdown_files(self, paths: List[Path]) -> List[Path]:
        """Find all markdown files from input paths.

        Safely handles symlinks and optimizes directory traversal.

        Args:
            paths: List of file or directory paths.

        Returns:
            List of markdown file paths (symlinks excluded for safety).
        """
        md_files = []

        for path in paths:
            if not path.exists():
                print_colored(f"⚠️  Path not found: {path}", Colors.YELLOW)
                continue

            # Skip symlinks to avoid potential issues
            if path.is_symlink():
                print_colored(f"⚠️  Skipping symlink: {path}", Colors.YELLOW)
                continue

            if path.is_file():
                if path.suffix.lower() == '.md':
                    md_files.append(path)
                else:
                    print_colored(f"⚠️  Skipping non-markdown file: {path}", Colors.YELLOW)
            elif path.is_dir():
                # Use os.walk for better performance on large directories
                # and explicit control over symlink handling
                import os
                for root, dirs, files in os.walk(path, followlinks=False):
                    # Filter out symlinks from directories to traverse
                    dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]

                    # Find markdown files
                    for filename in files:
                        file_path = Path(root) / filename
                        if (file_path.suffix.lower() == '.md' and
                            not file_path.is_symlink()):
                            md_files.append(file_path)

        return sorted(set(md_files))

    def read_file(self, file_path: Path) -> Optional[str]:
        """Read file content safely.

        Args:
            file_path: Path to file to read.

        Returns:
            File content as string, or None on error.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            print_colored(f"⚠️  Skipping binary file: {file_path}", Colors.YELLOW)
            return None
        except Exception as e:
            print_colored(f"❌ Error reading {file_path}: {e}", Colors.RED)
            return None

    def write_file(self, file_path: Path, content: str) -> bool:
        """Write content to file atomically.

        Uses a robust atomic write strategy:
        1. Write to temp file in same directory (ensures same filesystem)
        2. Flush and sync to disk
        3. Atomic rename (POSIX) or replace (Windows)

        Args:
            file_path: Path to file to write.
            content: Content to write.

        Returns:
            True if successful, False otherwise.
        """
        import tempfile
        import os

        # Create temp file in same directory to ensure same filesystem
        temp_fd = None
        temp_path = None

        try:
            # Create temp file in same directory as target
            temp_fd, temp_name = tempfile.mkstemp(
                dir=file_path.parent,
                prefix=f".{file_path.stem}.",
                suffix=f"{file_path.suffix}.tmp"
            )
            temp_path = Path(temp_name)

            # Write content to temp file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk
            temp_fd = None  # Closed by fdopen context manager

            # Atomic rename/replace
            if hasattr(os, 'replace'):
                # Python 3.3+: atomic on both POSIX and Windows
                os.replace(temp_name, str(file_path))
            else:
                # Fallback for older Python (POSIX only)
                temp_path.replace(file_path)

            return True

        except Exception as e:
            print_colored(f"❌ Error writing {file_path}: {e}", Colors.RED)
            return False

        finally:
            # Cleanup: close file descriptor if still open
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except Exception:
                    pass

            # Cleanup: remove temp file if it still exists
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def process_file(
        self,
        file_path: Path,
        interactive: bool = False,
        preview: bool = False
    ) -> Tuple[int, List[SanitizationMatch]]:
        """Process a single file.

        Args:
            file_path: Path to file to process.
            interactive: Whether to use interactive mode.
            preview: Whether to preview only (no changes).

        Returns:
            Tuple of (matches_applied, all_matches).
        """
        # Read file
        content = self.read_file(file_path)
        if content is None:
            return 0, []

        # Find all matches
        matches = self.sanitizer.preview_sanitization(content)

        if not matches:
            return 0, []

        # Preview mode - just show matches
        if preview:
            return 0, matches

        # Interactive mode - ask user for each match
        if interactive:
            approved_matches = self._interactive_review(file_path, content, matches)
            if approved_matches is None:  # User quit
                return 0, matches
            matches_to_apply = approved_matches
        else:
            # Batch mode - apply all
            matches_to_apply = matches

        if not matches_to_apply:
            return 0, matches

        # Create backup
        backup_path = self.backup_manager.create_backup(file_path)
        if backup_path and self.backup_manager.create_backups:
            print_colored(f"  💾 Backup created: {backup_path.name}", Colors.CYAN)

        # Apply sanitization
        sanitized_content, applied = self.sanitizer.sanitize_text(
            content,
            track_changes=True,
            approved_matches=matches_to_apply
        )

        # Write sanitized content
        if self.write_file(file_path, sanitized_content):
            self.files_modified += 1
            return len(applied) if applied else 0, matches

        return 0, matches

    def _interactive_review(
        self,
        file_path: Path,
        content: str,
        matches: List[SanitizationMatch]
    ) -> Optional[List[SanitizationMatch]]:
        """Interactively review matches with user.

        Args:
            file_path: File being processed.
            content: File content.
            matches: All detected matches.

        Returns:
            List of approved matches, or None if user quit.
        """
        print_colored(f"\n📄 {file_path.name}", Colors.CYAN)
        print_colored(f"Found {len(matches)} potential secret(s)\n", Colors.YELLOW)

        approved = []

        for i, match in enumerate(matches, 1):
            print_colored(f"Match {i} of {len(matches)}", Colors.BLUE)
            print(f"  Type: {match.pattern_type.replace('_', ' ').title()}")
            print(f"  Line: {match.line_number}")

            # Show context (3 lines before and after)
            context = self._get_context(content, match.line_number, context_lines=1)
            print_colored(f"\n  Context:", Colors.CYAN)
            print_colored(f"{context}", Colors.CYAN)

            print(f"\n  Original: {match.original_value}")
            print_colored(f"  Redacted: {match.redacted_value}", Colors.GREEN)

            # Ask user
            while True:
                response = input("\n  Sanitize this match? [Y/n/a/s/q/?] ").strip().lower()

                if response in ('y', 'yes', ''):
                    approved.append(match)
                    print_colored("  ✓ Will sanitize", Colors.GREEN)
                    break
                elif response == 'n':
                    print_colored("  ✗ Skipped", Colors.YELLOW)
                    break
                elif response == 'a':
                    # Approve all remaining
                    approved.extend(matches[i-1:])
                    print_colored(f"  ✓ Approved all {len(matches) - i + 1} remaining matches", Colors.GREEN)
                    return approved
                elif response == 's':
                    # Skip all remaining
                    print_colored(f"  ✗ Skipped all {len(matches) - i + 1} remaining matches", Colors.YELLOW)
                    return approved
                elif response == 'q':
                    # Quit
                    print_colored("\n  ⚠️  Quitting...", Colors.YELLOW)
                    return None
                elif response == '?':
                    # Show more context
                    full_context = self._get_context(content, match.line_number, context_lines=5)
                    print_colored(f"\n  Extended context:", Colors.CYAN)
                    print_colored(f"{full_context}\n", Colors.CYAN)
                else:
                    print_colored("  Invalid option. Use Y/n/a/s/q/?", Colors.RED)

            print()  # Blank line between matches

        return approved

    def _get_context(self, content: str, line_number: int, context_lines: int = 1) -> str:
        """Get context lines around a specific line.

        Args:
            content: Full file content.
            line_number: Target line number (1-indexed).
            context_lines: Number of lines before and after to include.

        Returns:
            Context as formatted string.
        """
        lines = content.split('\n')
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)

        context_lines_list = []
        for i in range(start, end):
            line_num = i + 1
            marker = "→" if line_num == line_number else " "
            # Truncate long lines
            line_text = lines[i][:100]
            if len(lines[i]) > 100:
                line_text += "..."
            context_lines_list.append(f"    {marker} {line_num:4d} | {line_text}")

        return '\n'.join(context_lines_list)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description='Sanitize sensitive data in exported chat markdown files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode - review each match
  python sanitize-chats.py exported-chats/ --interactive

  # Batch mode - auto-sanitize all matches
  python sanitize-chats.py exported-chats/

  # Preview mode - show what would be changed
  python sanitize-chats.py my-chat.md --preview

  # Custom settings (override .env)
  python sanitize-chats.py chats/ --level aggressive --style labeled

  # Generate report
  python sanitize-chats.py chats/ --report sanitization-report.txt
        """
    )

    parser.add_argument(
        'paths',
        nargs='+',
        type=Path,
        help='File(s) or directory to sanitize'
    )

    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Interactive mode - review each match'
    )

    parser.add_argument(
        '-p', '--preview',
        action='store_true',
        help='Preview mode - show what would be sanitized without applying changes'
    )

    parser.add_argument(
        '--level',
        choices=['minimal', 'balanced', 'aggressive', 'custom'],
        help='Sanitization level (default: from .env or balanced)'
    )

    parser.add_argument(
        '--style',
        choices=['simple', 'stars', 'labeled', 'partial', 'hash'],
        help='Redaction style (default: from .env or partial)'
    )

    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup files (not recommended)'
    )

    parser.add_argument(
        '--report',
        type=Path,
        metavar='FILE',
        help='Generate sanitization report to file'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_arguments()

    # Print header
    print_colored("=" * 60, Colors.BLUE)
    print_colored("🔒 Chat Sanitization Tool", Colors.BLUE)
    print_colored("=" * 60, Colors.BLUE)
    print()

    # Load configuration from .env (with CLI overrides)
    level = args.level or config.sanitize_level
    style = args.style or config.sanitize_style

    # Force enable sanitizer for this script
    sanitizer = Sanitizer(
        enabled=True,
        level=level,
        style=style,
        sanitize_paths=config.sanitize_paths,
        custom_patterns=config.sanitize_custom_patterns,
        allowlist=config.sanitize_allowlist
    )

    # Initialize components
    backup_manager = BackupManager(create_backups=not args.no_backup)
    processor = FileProcessor(sanitizer, backup_manager)

    # Find all markdown files
    print_colored("🔍 Finding markdown files...", Colors.CYAN)
    md_files = processor.find_markdown_files(args.paths)

    if not md_files:
        print_colored("❌ No markdown files found", Colors.RED)
        return 1

    print_colored(f"Found {len(md_files)} markdown file(s)\n", Colors.GREEN)

    # Show configuration
    print_colored("Configuration:", Colors.CYAN)
    print(f"  Level: {level}")
    print(f"  Style: {style}")
    print(f"  Mode: {'Preview' if args.preview else 'Interactive' if args.interactive else 'Batch'}")
    print(f"  Backups: {'Disabled' if args.no_backup else 'Enabled'}")
    print()

    # Process files
    all_matches = []

    for file_path in md_files:
        processor.files_processed += 1

        if args.verbose:
            print_colored(f"\n📄 Processing: {file_path}", Colors.CYAN)

        matches_applied, matches_found = processor.process_file(
            file_path,
            interactive=args.interactive,
            preview=args.preview
        )

        processor.total_matches += matches_applied
        all_matches.extend(matches_found)

        if args.preview and matches_found:
            # Show preview summary for this file
            print_colored(f"\n📄 {file_path.name}", Colors.CYAN)
            print_colored(f"   Would sanitize {len(matches_found)} match(es):", Colors.YELLOW)
            for match in matches_found[:5]:  # Show first 5
                print(f"     • Line {match.line_number}: {match.pattern_type.replace('_', ' ').title()}")
            if len(matches_found) > 5:
                print(f"     ... and {len(matches_found) - 5} more")
        elif matches_applied > 0:
            print_colored(f"✓ {file_path.name}: Sanitized {matches_applied} match(es)", Colors.GREEN)
        elif matches_found:
            print_colored(f"○ {file_path.name}: {len(matches_found)} match(es) found, none applied", Colors.YELLOW)

    # Print summary
    print()
    print_colored("=" * 60, Colors.BLUE)
    print_colored("📊 Summary", Colors.BLUE)
    print_colored("=" * 60, Colors.BLUE)

    if args.preview:
        print(f"Files scanned: {processor.files_processed}")
        print(f"Potential secrets found: {len(all_matches)}")
        print_colored("\n⚠️  Preview mode - no changes were made", Colors.YELLOW)
        print_colored("Run without --preview to apply sanitization", Colors.YELLOW)
    else:
        print(f"Files processed: {processor.files_processed}")
        print(f"Files modified: {processor.files_modified}")
        print(f"Secrets sanitized: {processor.total_matches}")

        if processor.files_modified > 0:
            print_colored(f"\n✅ Sanitization complete!", Colors.GREEN)
            if backup_manager.create_backups:
                print_colored(f"Backup files created: {len(backup_manager.backups_created)}", Colors.CYAN)
        else:
            print_colored("\n✓ No changes needed", Colors.GREEN)

    # Generate report if requested
    if args.report and all_matches:
        report = SanitizationReport(matches=all_matches)
        try:
            with open(args.report, 'w', encoding='utf-8') as f:
                f.write(report.to_text())
            print_colored(f"\n📄 Report saved to: {args.report}", Colors.GREEN)
        except Exception as e:
            print_colored(f"\n❌ Error writing report: {e}", Colors.RED)

    print()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Interrupted by user", Colors.YELLOW)
        sys.exit(130)
    except Exception as e:
        print_colored(f"\n❌ Fatal error: {e}", Colors.RED)
        if '--verbose' in sys.argv or '-v' in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)

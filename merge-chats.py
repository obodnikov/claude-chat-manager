#!/usr/bin/env python3
"""Merge exported chat files intelligently avoiding duplicates.

This utility compares exported chat markdown files from different sources
(e.g., different computers) and merges them intelligently by detecting
duplicates and incomplete conversations.

Usage:
    merge-chats.py --source SOURCE_DIR --target TARGET_DIR [options]

Examples:
    # Preview what would be done
    merge-chats.py --source ~/exports/new/ --target ./docs/chats/ --preview

    # Interactive mode - review each decision
    merge-chats.py --source ~/exports/new/ --target ./docs/chats/ --interactive

    # Automatic merge with report
    merge-chats.py --source ~/exports/new/ --target ./docs/chats/ --auto --report merge.txt
"""

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from chat_merger import ChatMerger, MergeAction, MergeDecision

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


class Colors:
    """Terminal color codes."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_colored(text: str, color: str = '', bold: bool = False) -> None:
    """Print colored text to terminal.

    Args:
        text: Text to print.
        color: Color code.
        bold: Whether to use bold.
    """
    prefix = (Colors.BOLD if bold else '') + color
    print(f"{prefix}{text}{Colors.RESET}")


def print_decision(decision: MergeDecision, show_details: bool = True) -> None:
    """Print a merge decision in formatted way.

    Args:
        decision: MergeDecision to print.
        show_details: Whether to show detailed information.
    """
    action_colors = {
        MergeAction.NEW: Colors.GREEN,
        MergeAction.UPDATE: Colors.YELLOW,
        MergeAction.SKIP: Colors.CYAN,
        MergeAction.REVIEW: Colors.RED
    }

    action_icons = {
        MergeAction.NEW: '✅ NEW',
        MergeAction.UPDATE: '🔄 UPDATE',
        MergeAction.SKIP: '⏭️  SKIP',
        MergeAction.REVIEW: '⚠️  REVIEW'
    }

    color = action_colors.get(decision.action, '')
    icon = action_icons.get(decision.action, decision.action.value.upper())

    print_colored(f"  [{icon}] {decision.source_file.name}", color)

    if show_details:
        print(f"    → {decision.reason}")
        if decision.target_file:
            print(f"    → Target: {decision.target_file.name}")


def preview_merge(decisions: List[MergeDecision]) -> None:
    """Display preview of merge actions.

    Args:
        decisions: List of merge decisions.
    """
    print_colored("\n🔍 Merge Preview", Colors.BOLD, bold=True)
    print_colored("=" * 70, Colors.BOLD)

    merger = ChatMerger()
    summary = merger.get_summary(decisions)

    print(f"\nSource files analyzed: {summary['total']}")
    print()

    # Group by action
    for action in MergeAction:
        action_decisions = [d for d in decisions if d.action == action]
        if action_decisions:
            print()
            for decision in action_decisions:
                print_decision(decision)

    # Summary
    print()
    print_colored("=" * 70, Colors.BOLD)
    print_colored("Summary:", Colors.BOLD, bold=True)
    print_colored(f"  ✅ NEW: {summary['new']} conversations (will copy)", Colors.GREEN)
    print_colored(f"  🔄 UPDATE: {summary['update']} conversations (will replace)", Colors.YELLOW)
    print_colored(f"  ⏭️  SKIP: {summary['skip']} conversations (already exist)", Colors.CYAN)
    print_colored(f"  ⚠️  REVIEW: {summary['review']} conversations (need manual check)", Colors.RED)
    print_colored("=" * 70, Colors.BOLD)


def interactive_merge(
    decisions: List[MergeDecision],
    target_dir: Path,
    backup: bool = True
) -> int:
    """Perform interactive merge with user confirmation for each file.

    Args:
        decisions: List of merge decisions.
        target_dir: Target directory.
        backup: Whether to create backups.

    Returns:
        Number of files processed.
    """
    print_colored("\n🎯 Interactive Merge Mode", Colors.BOLD, bold=True)
    print_colored("=" * 70, Colors.BOLD)
    print("\nReview each decision and choose an action.")
    print("Options: (y)es, (n)o, (s)kip all remaining, (q)uit\n")

    processed = 0
    skip_all = False

    for i, decision in enumerate(decisions, 1):
        if skip_all:
            break

        # Only prompt for NEW and UPDATE actions
        if decision.action not in [MergeAction.NEW, MergeAction.UPDATE]:
            continue

        print_colored(f"\n[{i}/{len(decisions)}]", Colors.BOLD, bold=True)
        print_decision(decision, show_details=True)

        while True:
            response = input("\nProceed? (y/n/s/q): ").lower().strip()

            if response == 'y':
                success = execute_decision(decision, target_dir, backup)
                if success:
                    processed += 1
                    print_colored("  ✓ Done", Colors.GREEN)
                break
            elif response == 'n':
                print_colored("  ✗ Skipped", Colors.CYAN)
                break
            elif response == 's':
                skip_all = True
                print_colored("  ⏭️  Skipping all remaining", Colors.CYAN)
                break
            elif response == 'q':
                print_colored("\n❌ Merge cancelled by user", Colors.RED)
                return processed
            else:
                print("Invalid option. Please enter y, n, s, or q.")

    print_colored(f"\n✅ Interactive merge complete. Processed {processed} files.", Colors.GREEN)
    return processed


def auto_merge(
    decisions: List[MergeDecision],
    target_dir: Path,
    backup: bool = True
) -> int:
    """Perform automatic merge based on decisions.

    Args:
        decisions: List of merge decisions.
        target_dir: Target directory.
        backup: Whether to create backups.

    Returns:
        Number of files processed.
    """
    print_colored("\n⚡ Automatic Merge Mode", Colors.BOLD, bold=True)
    print_colored("=" * 70, Colors.BOLD)

    processed = 0
    errors = 0

    for decision in decisions:
        if decision.action in [MergeAction.NEW, MergeAction.UPDATE]:
            print_decision(decision, show_details=False)
            success = execute_decision(decision, target_dir, backup)
            if success:
                processed += 1
            else:
                errors += 1

    print()
    print_colored("=" * 70, Colors.BOLD)
    print_colored(f"✅ Merge complete. Processed {processed} files.", Colors.GREEN)
    if errors > 0:
        print_colored(f"⚠️  {errors} errors occurred.", Colors.RED)

    return processed


def execute_decision(decision: MergeDecision, target_dir: Path, backup: bool) -> bool:
    """Execute a single merge decision.

    Args:
        decision: Merge decision to execute.
        target_dir: Target directory.
        backup: Whether to create backup before overwriting.

    Returns:
        True if successful, False otherwise.
    """
    try:
        target_file = target_dir / decision.source_file.name

        # Create backup if overwriting and backup enabled
        if decision.action == MergeAction.UPDATE and backup and target_file.exists():
            backup_path = target_file.with_suffix('.md.backup')
            shutil.copy2(target_file, backup_path)
            logger.debug(f"Created backup: {backup_path.name}")

        # Copy file
        shutil.copy2(decision.source_file, target_file)
        logger.debug(f"Copied {decision.source_file.name} to {target_file}")

        return True

    except Exception as e:
        logger.error(f"Error processing {decision.source_file.name}: {e}")
        return False


def generate_report(decisions: List[MergeDecision], report_path: Path) -> None:
    """Generate detailed merge report.

    Args:
        decisions: List of merge decisions.
        report_path: Path to save report.
    """
    merger = ChatMerger()
    summary = merger.get_summary(decisions)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# Chat Merge Report\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Summary\n\n")
        f.write(f"- Total files analyzed: {summary['total']}\n")
        f.write(f"- New conversations: {summary['new']}\n")
        f.write(f"- Updates needed: {summary['update']}\n")
        f.write(f"- Duplicates (skipped): {summary['skip']}\n")
        f.write(f"- Review required: {summary['review']}\n\n")

        # Detailed actions
        for action in MergeAction:
            action_decisions = [d for d in decisions if d.action == action]
            if action_decisions:
                f.write(f"## {action.value.upper()} ({len(action_decisions)} files)\n\n")
                for decision in action_decisions:
                    f.write(f"### {decision.source_file.name}\n")
                    f.write(f"- **Reason:** {decision.reason}\n")
                    f.write(f"- **Source messages:** {decision.source_msgs}\n")
                    if decision.target_file:
                        f.write(f"- **Target file:** {decision.target_file.name}\n")
                        f.write(f"- **Target messages:** {decision.target_msgs}\n")
                    if decision.similarity is not None:
                        f.write(f"- **Similarity:** {decision.similarity:.2%}\n")
                    f.write("\n")

    print_colored(f"📄 Report saved to: {report_path}", Colors.GREEN)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Merge exported chat files intelligently, avoiding duplicates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be done (dry-run)
  %(prog)s --source ~/exports/ --target ./docs/chats/ --preview

  # Interactive mode - review each decision
  %(prog)s --source ~/exports/ --target ./docs/chats/ --interactive

  # Automatic merge with backup and report
  %(prog)s --source ~/exports/ --target ./docs/chats/ --auto --backup --report merge.txt

  # Custom similarity threshold
  %(prog)s --source ~/exports/ --target ./docs/chats/ --auto --similarity 0.9
        """
    )

    parser.add_argument(
        '--source', '-s',
        type=Path,
        required=True,
        help='Source directory with new exported chats'
    )

    parser.add_argument(
        '--target', '-t',
        type=Path,
        required=True,
        help='Target directory with existing chats (e.g., docs/chats/)'
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--preview', '-p',
        action='store_true',
        help='Preview what would be done without making changes'
    )
    mode_group.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Interactive mode - review each decision'
    )
    mode_group.add_argument(
        '--auto', '-a',
        action='store_true',
        help='Automatic merge based on heuristics'
    )

    # Options
    parser.add_argument(
        '--similarity',
        type=float,
        default=0.8,
        help='Similarity threshold for matching (0.0-1.0, default: 0.8)'
    )

    parser.add_argument(
        '--fingerprint-messages',
        type=int,
        default=3,
        help='Number of message pairs to use for fingerprint (default: 3)'
    )

    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create backups before overwriting files (.md.backup)'
    )

    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backups (override default)'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Generate detailed merge report to file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (debug logging)'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate directories
    if not args.source.exists():
        print_colored(f"❌ Source directory not found: {args.source}", Colors.RED)
        return 1

    if not args.source.is_dir():
        print_colored(f"❌ Source is not a directory: {args.source}", Colors.RED)
        return 1

    if not args.target.exists():
        print_colored(f"❌ Target directory not found: {args.target}", Colors.RED)
        print_colored(f"💡 Create it first: mkdir -p {args.target}", Colors.YELLOW)
        return 1

    if not args.target.is_dir():
        print_colored(f"❌ Target is not a directory: {args.target}", Colors.RED)
        return 1

    # Determine backup setting
    backup = args.backup or (not args.no_backup and not args.preview)

    try:
        # Initialize merger
        merger = ChatMerger(
            fingerprint_messages=args.fingerprint_messages,
            similarity_threshold=args.similarity,
            prefer_longer=True
        )

        # Analyze directories
        print_colored("\n🔍 Analyzing conversations...", Colors.BOLD, bold=True)
        decisions = merger.analyze_directories(args.source, args.target)

        if not decisions:
            print_colored("\n❌ No markdown files found in source directory.", Colors.RED)
            return 1

        # Execute based on mode
        if args.preview:
            preview_merge(decisions)

        elif args.interactive:
            preview_merge(decisions)
            print()
            response = input("Proceed with interactive merge? (y/n): ").lower().strip()
            if response != 'y':
                print_colored("\n❌ Merge cancelled by user.", Colors.RED)
                return 0
            interactive_merge(decisions, args.target, backup)

        elif args.auto:
            preview_merge(decisions)
            print()
            response = input("Proceed with automatic merge? (y/n): ").lower().strip()
            if response != 'y':
                print_colored("\n❌ Merge cancelled by user.", Colors.RED)
                return 0
            auto_merge(decisions, args.target, backup)

        # Generate report if requested
        if args.report:
            generate_report(decisions, args.report)

        return 0

    except KeyboardInterrupt:
        print_colored("\n\n❌ Merge cancelled by user.", Colors.RED)
        return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())

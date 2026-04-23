#!/usr/bin/env python3
"""Auto-export conversations from all sources to project docs/chats folders.

This utility automates the full export pipeline:
1. Discovers conversations across all sources (Claude Desktop, Kiro IDE, Codex CLI)
2. Maps conversation projects to filesystem project folders
3. Exports and merges chats into each project's docs/chats/ directory

Usage:
    # First time: build mapping config interactively
    auto-export.py --root ~/src --learn

    # Update mappings (keep confirmed, add new projects)
    auto-export.py --root ~/src --learn --update

    # Preview what would happen
    auto-export.py --root ~/src --dry-run

    # Run the full export+merge pipeline
    auto-export.py --root ~/src
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for package imports
sys.path.insert(0, str(Path(__file__).parent))

from src.colors import Colors, print_colored
from src.exceptions import ClaudeReaderError, ConfigurationError, ProjectNotFoundError
from src.models import ChatSource, ProjectInfo
from src.project_matcher import (
    MappingConfig,
    ProjectMapping,
    ProjectMatcher,
    DEFAULT_CONFIG_PATH,
    HIGH_CONFIDENCE_THRESHOLD,
)
from src.projects import list_all_projects

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Source display labels
SOURCE_LABELS: Dict[ChatSource, str] = {
    ChatSource.CLAUDE_DESKTOP: "Claude",
    ChatSource.KIRO_IDE: "Kiro",
    ChatSource.CODEX: "Codex",
    ChatSource.UNKNOWN: "Unknown",
}

# Separator used in source-qualified mapping keys
_KEY_SEP = ":"


def _source_label(source: ChatSource) -> str:
    """Get display label for a chat source.

    Args:
        source: ChatSource enum value.

    Returns:
        Human-readable source label.
    """
    return SOURCE_LABELS.get(source, source.value)


def _mapping_key(project_name: str, source: ChatSource) -> str:
    """Build a source-qualified mapping key.

    Different sources can have projects with the same name (e.g. both
    Claude and Kiro may have a 'claude-chat-manager' project). Using a
    source-qualified key prevents one source's mapping from silently
    overwriting another's.

    Args:
        project_name: Conversation project name.
        source: ChatSource enum value.

    Returns:
        Key string in the form 'claude:project-name'.
    """
    return f"{source.value}{_KEY_SEP}{project_name}"


def _format_target_path(root_dir: Path, mapping: ProjectMapping) -> str:
    """Format the full target path for display.

    Args:
        root_dir: Root directory path.
        mapping: Project mapping with target and docs_chats_path.

    Returns:
        Formatted path string like '~/src/project/docs/chats/'.
    """
    if not mapping.target:
        return "??? (no match)"

    target_path = root_dir / mapping.target / mapping.docs_chats_path
    # Shorten home directory for display
    try:
        home = Path.home()
        if target_path.is_relative_to(home):
            return f"~/{target_path.relative_to(home)}/"
    except (ValueError, TypeError):
        pass
    return f"{target_path}/"


def _count_existing_files(root_dir: Path, mapping: ProjectMapping) -> int:
    """Count existing markdown files in the target docs/chats directory.

    Args:
        root_dir: Root directory path.
        mapping: Project mapping with target and docs_chats_path.

    Returns:
        Number of .md files found, or 0 if directory doesn't exist.
    """
    if not mapping.target:
        return 0
    target_dir = root_dir / mapping.target / mapping.docs_chats_path
    if target_dir.exists() and target_dir.is_dir():
        return len(list(target_dir.glob('*.md')))
    return 0


def _prompt_user(prompt: str, default: str = '') -> str:
    """Prompt user for input with a default value.

    Args:
        prompt: Prompt text to display.
        default: Default value if user presses Enter.

    Returns:
        User input string, or default if empty.
    """
    try:
        response = input(prompt).strip()
        return response if response else default
    except EOFError:
        return default


def _validate_custom_target(custom_folder: str, root_dir: Path) -> Optional[str]:
    """Validate that a custom folder target stays inside root_dir.

    Resolves the path and checks it doesn't escape the root boundary
    via '..' traversal, absolute paths, or symlink tricks.

    Args:
        custom_folder: User-provided folder name (relative).
        root_dir: Resolved root directory path.

    Returns:
        None if valid, or an error message string if invalid.
    """
    # Reject empty or root-equivalent targets
    if not custom_folder or custom_folder in ('.', '/'):
        return "Target folder name cannot be empty or '.'"

    resolved_root = root_dir.resolve()
    resolved_target = (root_dir / custom_folder).resolve()

    # Must be strictly inside root (not equal to root itself)
    try:
        if resolved_target == resolved_root:
            return "Target cannot be the root directory itself"
        if not resolved_target.is_relative_to(resolved_root):
            return (
                f"Target '{custom_folder}' resolves to {resolved_target} "
                f"which is outside root {resolved_root}"
            )
    except (ValueError, TypeError):
        return f"Target '{custom_folder}' could not be validated against root"

    return None


def _canonicalize_custom_target(custom_folder: str, root_dir: Path) -> str:
    """Canonicalize a custom target to a normalized relative path.

    Resolves './project-a', 'project-a/../project-a', and 'project-a'
    to the same canonical form so they don't create duplicate mappings.

    Args:
        custom_folder: User-provided folder name (already validated).
        root_dir: Resolved root directory path.

    Returns:
        Normalized relative path string (e.g. 'project-a').
    """
    resolved_root = root_dir.resolve()
    resolved_target = (root_dir / custom_folder).resolve()
    return str(resolved_target.relative_to(resolved_root))


def _ask_confirmation(
    index: int,
    total: int,
    project_info: ProjectInfo,
    mapping: ProjectMapping,
    root_dir: Path,
    existing_target: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Show match result and ask user for confirmation.

    Args:
        index: Current project index (1-based).
        total: Total number of projects.
        project_info: Source project information.
        mapping: Auto-matched mapping result.
        root_dir: Root directory for path display.
        existing_target: If another source already maps to same target.

    Returns:
        Tuple of (action, custom_target) where action is one of:
        'confirm', 'skip', 'custom' and custom_target is the user-provided
        folder name (only when action is 'custom').
    """
    source_label = _source_label(project_info.source)
    print(f"\n{Colors.CYAN}[{index}/{total}]{Colors.NC} "
          f"{Colors.YELLOW}{project_info.name}{Colors.NC} "
          f"[{source_label}]")

    if mapping.target and mapping.action != 'skip':
        target_display = _format_target_path(root_dir, mapping)
        file_count = _count_existing_files(root_dir, mapping)
        method = mapping.match_method

        # Determine confidence display
        confidence = "high confidence" if mapping.confirmed else method
        print(f"  Auto-matched: {target_display} ({confidence})")

        if file_count > 0:
            print(f"  Docs target:  {target_display} (found, {file_count} files)")
        else:
            print(f"  Docs target:  {target_display} (not found, will create)")

        if existing_target:
            print(f"  → Same target as previous mapping.")
            response = _prompt_user("  → Confirm? [Y/n]: ", 'y')
        else:
            response = _prompt_user("  → Confirm? [Y/n/custom/skip]: ", 'y')

        response_lower = response.lower()
        if response_lower in ('y', 'yes', ''):
            return 'confirm', None
        elif response_lower in ('n', 'no', 'skip', 's'):
            return 'skip', None
        else:
            # Treat as custom folder name
            return 'custom', response

    else:
        # No match found
        print_colored(
            f"  ⚠️  No match found in {root_dir}/",
            Colors.YELLOW
        )
        response = _prompt_user(
            "  → Enter folder name, 'skip', or press Enter for skip: ",
            'skip'
        )

        response_lower = response.lower()
        if response_lower in ('skip', 's', ''):
            return 'skip', None
        else:
            return 'custom', response


def learn_mode(
    root_dir: Path,
    config_path: Path,
    update: bool = False,
    source_filter: Optional[ChatSource] = None,
) -> int:
    """Interactive mapping builder.

    Discovers all conversation projects, matches them to filesystem
    folders, and asks the user to confirm or correct each mapping.
    Saves results to the mapping config file.

    Args:
        root_dir: Root directory containing project folders.
        config_path: Path to mapping config JSON file.
        update: If True, preserve existing confirmed mappings.
        source_filter: Optional filter to only process one source.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    print_colored("🔍 Learning project mappings...\n", Colors.CYAN)

    # Load or create config
    mapping_config = MappingConfig(config_path)
    try:
        mapping_config.load()
    except ConfigurationError as e:
        if update:
            logger.error(f"Cannot load existing config for update: {e}")
            print_colored(f"❌ {e}", Colors.RED)
            return 1
        # Fresh start — use defaults
        logger.info("Starting with fresh config")

    # Set root directory in config
    mapping_config.set_root_directory(str(root_dir))

    # Discover conversation projects
    try:
        all_projects = list_all_projects(source_filter)
    except ProjectNotFoundError as e:
        print_colored(f"❌ {e}", Colors.RED)
        return 1

    # Initialize matcher
    try:
        matcher = ProjectMatcher(root_dir, mapping_config)
    except (ConfigurationError, ValueError) as e:
        print_colored(f"❌ {e}", Colors.RED)
        return 1

    fs_projects = matcher.discover_filesystem_projects()

    # Count by source
    source_counts: Dict[ChatSource, int] = {}
    for p in all_projects:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1

    source_summary = ", ".join(
        f"{_source_label(s)}: {c}" for s, c in sorted(
            source_counts.items(), key=lambda x: x[0].value
        )
    )

    print(f"Root directory: {root_dir} ({len(fs_projects)} project folders found)")
    print(f"Conversation projects: {len(all_projects)} ({source_summary})")

    # Track targets already mapped (to detect merges)
    confirmed_targets: Dict[str, str] = {}  # target_folder → first project name
    if update:
        # Pre-populate from existing confirmed mappings
        for name, target in mapping_config.get_confirmed_targets().items():
            confirmed_targets[target] = name

    # Track stats
    mapped_count = 0
    skipped_count = 0
    merged_count = 0

    for i, project_info in enumerate(all_projects, 1):
        project_name = project_info.name
        mapping_key = _mapping_key(project_name, project_info.source)

        # In update mode, skip already-confirmed mappings
        if update:
            existing = mapping_config.get_mapping(mapping_key)
            if existing and existing.confirmed:
                logger.debug(f"Skipping confirmed mapping: {mapping_key}")
                if existing.action == 'export' and existing.target:
                    mapped_count += 1
                else:
                    skipped_count += 1
                continue

        # Run auto-matching
        auto_mapping = matcher.match_project(project_info)

        # Check if another source already maps to the same target
        existing_target = None
        if auto_mapping.target and auto_mapping.target in confirmed_targets:
            existing_target = confirmed_targets[auto_mapping.target]

        # Ask user
        action, custom_target = _ask_confirmation(
            index=i,
            total=len(all_projects),
            project_info=project_info,
            mapping=auto_mapping,
            root_dir=root_dir,
            existing_target=existing_target,
        )

        if action == 'confirm':
            # Use auto-matched mapping
            auto_mapping.confirmed = True
            mapping_config.set_mapping(mapping_key, auto_mapping)

            if auto_mapping.target:
                confirmed_targets[auto_mapping.target] = mapping_key
                if existing_target:
                    merged_count += 1
                    print_colored("  ✅ Confirmed (merged with existing mapping)", Colors.GREEN)
                else:
                    print_colored("  ✅ Confirmed", Colors.GREEN)
                mapped_count += 1
            else:
                skipped_count += 1

        elif action == 'skip':
            skip_mapping = ProjectMapping(
                source_name=project_name,
                action='skip',
                confirmed=True,
                match_method='user_skip',
                source_type=project_info.source,
                workspace_path=project_info.workspace_path,
            )
            mapping_config.set_mapping(mapping_key, skip_mapping)
            print_colored("  ⏭️  Skipped", Colors.CYAN)
            skipped_count += 1

        elif action == 'custom':
            # User provided a custom folder name
            custom_folder = custom_target.strip().rstrip('/')

            # Reject empty targets (e.g. user entered just '/')
            if not custom_folder or custom_folder == '.':
                print_colored("  ❌ Empty target — skipping", Colors.RED)
                # Write explicit skip to prevent stale mappings
                mapping_config.set_mapping(mapping_key, ProjectMapping(
                    source_name=project_name,
                    action='skip',
                    confirmed=True,
                    match_method='invalid_input',
                    source_type=project_info.source,
                ))
                skipped_count += 1
                continue

            # Validate the custom folder stays inside root
            path_error = _validate_custom_target(custom_folder, root_dir)
            if path_error:
                print_colored(f"  ❌ {path_error}", Colors.RED)
                # Write explicit skip to prevent stale mappings
                mapping_config.set_mapping(mapping_key, ProjectMapping(
                    source_name=project_name,
                    action='skip',
                    confirmed=True,
                    match_method='invalid_input',
                    source_type=project_info.source,
                ))
                skipped_count += 1
                continue

            # Canonicalize so './proj' and 'proj' store the same key
            custom_folder = _canonicalize_custom_target(custom_folder, root_dir)

            # Validate the custom folder exists under root
            custom_path = root_dir / custom_folder
            if not custom_path.exists():
                print(f"  ⚠️  Folder '{custom_folder}' not found under {root_dir}")
                create = _prompt_user("  → Create on first export? [Y/n]: ", 'y')
                if create.lower() not in ('y', 'yes', ''):
                    skip_mapping = ProjectMapping(
                        source_name=project_name,
                        action='skip',
                        confirmed=True,
                        match_method='user_skip',
                        source_type=project_info.source,
                    )
                    mapping_config.set_mapping(mapping_key, skip_mapping)
                    print_colored("  ⏭️  Skipped", Colors.CYAN)
                    skipped_count += 1
                    continue

            # Detect docs/chats path
            docs_path = "docs/chats"
            if custom_path.exists():
                docs_path = matcher.detect_docs_chats_dir(custom_path)

            custom_mapping = ProjectMapping(
                source_name=project_name,
                target=custom_folder,
                docs_chats_path=docs_path,
                action='export',
                confirmed=True,
                match_method='user_custom',
                source_type=project_info.source,
                workspace_path=project_info.workspace_path,
            )
            try:
                mapping_config.set_mapping(mapping_key, custom_mapping)
                confirmed_targets[custom_folder] = mapping_key
                print_colored(
                    f"  ✅ Mapped to {_format_target_path(root_dir, custom_mapping)}",
                    Colors.GREEN
                )
                mapped_count += 1
            except ConfigurationError as e:
                print_colored(f"  ❌ Invalid path: {e}", Colors.RED)
                skipped_count += 1

    # Save config
    mapping_config.set_last_learned()
    try:
        mapping_config.save()
    except ConfigurationError as e:
        print_colored(f"\n❌ Failed to save config: {e}", Colors.RED)
        return 1

    # Print summary
    print_learn_summary(
        mapping_config, root_dir, mapped_count, skipped_count, merged_count
    )
    return 0


def print_learn_summary(
    config: MappingConfig,
    root_dir: Path,
    mapped_count: int,
    skipped_count: int,
    merged_count: int,
) -> None:
    """Print summary of all mappings after learn mode.

    Args:
        config: MappingConfig with saved mappings.
        root_dir: Root directory for path display.
        mapped_count: Number of projects mapped to folders.
        skipped_count: Number of projects skipped.
        merged_count: Number of projects merged with existing mappings.
    """
    all_mappings = config.get_all_mappings()
    export_mappings = {
        k: v for k, v in all_mappings.items() if v.action == 'export'
    }
    skip_mappings = {
        k: v for k, v in all_mappings.items() if v.action == 'skip'
    }

    # Count unique target folders
    unique_targets = set()
    for m in export_mappings.values():
        if m.target:
            unique_targets.add(m.target)

    print(f"\n{'═' * 50}")
    print_colored("📋 Mapping Summary", Colors.CYAN)
    print(f"{'═' * 50}")
    print_colored(
        f"  ✅ Mapped:  {mapped_count} projects → {len(unique_targets)} folders",
        Colors.GREEN
    )
    if merged_count > 0:
        print_colored(
            f"  🔗 Merged:  {merged_count} projects (multiple sources → same folder)",
            Colors.BLUE
        )
    print_colored(
        f"  ⏭️  Skipped: {skipped_count} projects",
        Colors.CYAN
    )
    print(f"  Config saved: {config.config_path}")
    print(f"{'═' * 50}")


def _parse_source(value: str) -> Optional[ChatSource]:
    """Parse source filter string to ChatSource enum.

    Args:
        value: Source string ('claude', 'kiro', 'codex', 'all').

    Returns:
        ChatSource enum value, or None for 'all'.

    Raises:
        argparse.ArgumentTypeError: If value is not recognized.
    """
    source_map = {
        'claude': ChatSource.CLAUDE_DESKTOP,
        'kiro': ChatSource.KIRO_IDE,
        'codex': ChatSource.CODEX,
        'all': None,
    }
    if value.lower() not in source_map:
        raise argparse.ArgumentTypeError(
            f"Invalid source '{value}'. Choose from: claude, kiro, codex, all"
        )
    return source_map[value.lower()]


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Auto-export conversations from all sources "
            "(Claude Desktop, Kiro IDE, Codex CLI) "
            "to project docs/chats/ folders."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First time: build mapping config interactively
  %(prog)s --root ~/src --learn

  # Update mappings (keep confirmed, add new projects)
  %(prog)s --root ~/src --learn --update

  # Preview what would happen (Phase 3)
  %(prog)s --root ~/src --dry-run

  # Run the full export+merge pipeline (Phase 3)
  %(prog)s --root ~/src
        """
    )

    parser.add_argument(
        '--root', '-r',
        type=Path,
        required=True,
        help='Root directory containing project folders (e.g., ~/src)'
    )

    parser.add_argument(
        '--learn',
        action='store_true',
        help='Interactive mode: build/update mapping config'
    )

    parser.add_argument(
        '--update',
        action='store_true',
        help='With --learn: keep existing confirmed mappings, only add new'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview mode: show plan without executing (Phase 3)'
    )

    parser.add_argument(
        '--source',
        type=_parse_source,
        default=None,
        metavar='SOURCE',
        help='Filter by source: claude, kiro, codex, or all (default: all)'
    )

    parser.add_argument(
        '--config',
        type=Path,
        default=None,
        help=f'Path to mapping config file (default: {DEFAULT_CONFIG_PATH})'
    )

    parser.add_argument(
        '--keep-tmp',
        action='store_true',
        help="Don't clean up temporary export directory (Phase 3)"
    )

    parser.add_argument(
        '--format',
        choices=['book', 'markdown'],
        default='book',
        help='Export format: book or markdown (default: book) (Phase 3)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve root directory (expand ~ and make absolute)
    root_dir = args.root.expanduser().resolve()

    # Validate root directory
    if not root_dir.exists():
        print_colored(f"❌ Root directory not found: {root_dir}", Colors.RED)
        return 1

    if not root_dir.is_dir():
        print_colored(f"❌ Root is not a directory: {root_dir}", Colors.RED)
        return 1

    # Resolve config path with clear precedence:
    #   1. Explicit --config flag (highest priority)
    #   2. AUTO_EXPORT_CONFIG env var
    #   3. Default path (lowest priority)
    # argparse default is None, so non-None means user supplied --config
    env_config_val = os.environ.get('AUTO_EXPORT_CONFIG')

    if args.config is not None:
        config_path = args.config.expanduser().resolve()
    elif env_config_val:
        config_path = Path(env_config_val).expanduser().resolve()
    else:
        config_path = DEFAULT_CONFIG_PATH

    # Validate --update requires --learn
    if args.update and not args.learn:
        print_colored("❌ --update requires --learn", Colors.RED)
        return 1

    # Dispatch to mode
    try:
        if args.learn:
            return learn_mode(
                root_dir=root_dir,
                config_path=config_path,
                update=args.update,
                source_filter=args.source,
            )

        elif args.dry_run:
            print_colored(
                "⚠️  Dry-run mode not yet implemented (Phase 3).",
                Colors.YELLOW
            )
            return 1

        else:
            # Execute mode (Phase 3)
            # Check config exists
            if not config_path.exists():
                print_colored(
                    "❌ No mapping config found. Run --learn first to build one.",
                    Colors.RED
                )
                print_colored(
                    f"   Expected: {config_path}",
                    Colors.YELLOW
                )
                return 1

            print_colored(
                "⚠️  Execute mode not yet implemented (Phase 3).",
                Colors.YELLOW
            )
            return 1

    except KeyboardInterrupt:
        print_colored("\n\n❌ Cancelled by user.", Colors.RED)
        return 1
    except ClaudeReaderError as e:
        print_colored(f"\n❌ Error: {e}", Colors.RED)
        return 1


if __name__ == '__main__':
    sys.exit(main())

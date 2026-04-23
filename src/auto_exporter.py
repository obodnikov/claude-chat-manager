"""Auto-export pipeline orchestrator.

This module coordinates the full auto-export pipeline:
1. Load mapping config
2. Discover conversation projects from all sources
3. Group projects by target folder
4. Export chats to temporary directory
5. Merge into each project's docs/chats/ directory
6. Report results and clean up

Uses existing modules for all heavy lifting — no new export/merge/parse logic.
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .chat_merger import ChatMerger, MergeAction, MergeDecision
from .colors import Colors, print_colored
from .exceptions import ConfigurationError, ExportError
from .exporters import export_project_chats
from .models import ChatSource, ProjectInfo
from .project_matcher import MappingConfig, ProjectMapping
from .projects import get_project_chat_files, list_all_projects

logger = logging.getLogger(__name__)

# Source display labels
SOURCE_LABELS: Dict[ChatSource, str] = {
    ChatSource.CLAUDE_DESKTOP: "Claude",
    ChatSource.KIRO_IDE: "Kiro",
    ChatSource.CODEX: "Codex",
    ChatSource.UNKNOWN: "Unknown",
}

# Separator used in source-qualified mapping keys (must match auto-export.py)
_KEY_SEP = ":"


@dataclass
class ExportResult:
    """Result of exporting and merging one target folder.

    Attributes:
        target_name: Target folder name (relative to root).
        target_dir: Full path to the target docs/chats directory.
        sources: List of (project_name, source) tuples that contributed.
        chats_exported: Total number of chat files exported to tmp.
        new_files: Number of new files merged into target.
        updated_files: Number of files updated in target.
        skipped_files: Number of files skipped (already up to date).
        review_files: Number of files needing manual review.
        errors: List of error messages encountered.
    """

    target_name: str
    target_dir: Path
    sources: List[Tuple[str, ChatSource]] = field(default_factory=list)
    chats_exported: int = 0
    new_files: int = 0
    updated_files: int = 0
    skipped_files: int = 0
    review_files: int = 0
    errors: List[str] = field(default_factory=list)


class AutoExporter:
    """Orchestrates the full auto-export pipeline.

    Discovers conversation projects, maps them to filesystem folders
    via MappingConfig, exports chats to a temporary directory, then
    merges into each project's docs/chats/ directory.

    Attributes:
        root_dir: Root directory containing project folders.
        mapping_config: Loaded MappingConfig instance.
        source_filter: Optional filter to process only one source.
        export_format: Export format ('book' or 'markdown').
        dry_run: If True, only preview — don't export or merge.
        keep_tmp: If True, don't clean up temporary directory.
    """

    def __init__(
        self,
        root_dir: Path,
        mapping_config: MappingConfig,
        source_filter: Optional[ChatSource] = None,
        export_format: str = 'book',
        dry_run: bool = False,
        keep_tmp: bool = False,
    ) -> None:
        """Initialize the auto-exporter.

        Args:
            root_dir: Root directory containing project folders.
            mapping_config: Loaded MappingConfig instance.
            source_filter: Optional filter to process only one source.
            export_format: Export format ('book' or 'markdown').
            dry_run: If True, only preview — don't export or merge.
            keep_tmp: If True, don't clean up temporary directory.

        Raises:
            ConfigurationError: If root_dir is invalid.
        """
        if not root_dir.exists() or not root_dir.is_dir():
            raise ConfigurationError(f"Invalid root directory: {root_dir}")

        self.root_dir = root_dir.resolve()
        self.mapping_config = mapping_config
        self.source_filter = source_filter
        self.export_format = export_format
        self.dry_run = dry_run
        self.keep_tmp = keep_tmp
        self._merger = ChatMerger()

    def run(self) -> List[ExportResult]:
        """Execute the full export+merge pipeline.

        Steps:
            1. Discover conversation projects from all sources
            2. Resolve mappings and group by target folder
            3. For each target: export all source projects to tmp, merge
            4. Clean up tmp directory (unless keep_tmp)

        Returns:
            List of ExportResult objects, one per target folder.

        Raises:
            ExportError: If project discovery fails entirely.
        """
        # 1. Discover conversation projects
        all_projects = list_all_projects(self.source_filter)

        # 2. Group by target
        grouped = self._group_projects_by_target(all_projects)

        if not grouped:
            print_colored("ℹ️  No projects mapped for export.", Colors.YELLOW)
            return []

        # 3. Export and merge each target
        results: List[ExportResult] = []
        tmp_base = Path(tempfile.mkdtemp(prefix='auto-export-'))
        logger.info(f"Using temporary directory: {tmp_base}")

        try:
            for target_key, (target_dir, projects) in grouped.items():
                result = self._process_target(
                    target_dir, projects, tmp_base
                )
                results.append(result)
        finally:
            # 4. Clean up
            if not self.keep_tmp:
                try:
                    shutil.rmtree(tmp_base)
                    logger.info(f"Cleaned up temporary directory: {tmp_base}")
                except OSError as e:
                    logger.warning(f"Failed to clean up {tmp_base}: {e}")
            else:
                print_colored(
                    f"ℹ️  Temporary files kept at: {tmp_base}",
                    Colors.CYAN
                )

        return results

    def dry_run_report(self) -> List[ExportResult]:
        """Show what would happen without executing.

        Discovers projects, resolves mappings, and for each target
        counts source chats and analyzes existing target files.

        Returns:
            List of ExportResult objects with estimated counts.

        Raises:
            ExportError: If project discovery fails entirely.
        """
        # Discover conversation projects
        all_projects = list_all_projects(self.source_filter)

        # Group by target
        grouped = self._group_projects_by_target(all_projects)

        if not grouped:
            print_colored("ℹ️  No projects mapped for export.", Colors.YELLOW)
            return []

        results: List[ExportResult] = []

        print_colored("\n📋 Dry Run — Export Plan", Colors.CYAN)
        print(f"{'═' * 60}")

        for target_key, (target_dir, projects) in grouped.items():
            # Derive display-friendly name
            try:
                display_name = str(
                    target_dir.resolve().relative_to(self.root_dir)
                )
            except ValueError:
                display_name = target_key

            result = ExportResult(
                target_name=display_name,
                target_dir=target_dir,
            )

            # Count source chats
            total_chats = 0
            for project_info in projects:
                source_label = SOURCE_LABELS.get(
                    project_info.source, project_info.source.value
                )
                result.sources.append(
                    (project_info.name, project_info.source)
                )

                chat_count = self._count_project_chats(project_info)
                total_chats += chat_count

            result.chats_exported = total_chats

            # Count existing files in target
            existing_count = 0
            if target_dir.exists() and target_dir.is_dir():
                existing_count = len(list(target_dir.glob('*.md')))

            # Display
            print(f"\n  📁 {display_name}")
            for name, source in result.sources:
                label = SOURCE_LABELS.get(source, source.value)
                print(f"     [{label}] {name}")
            print(f"     Source chats: {total_chats}")
            print(f"     Existing files in target: {existing_count}")
            print(f"     Target: {target_dir}")

            results.append(result)

        print(f"\n{'═' * 60}")
        total_sources = sum(len(r.sources) for r in results)
        total_chats = sum(r.chats_exported for r in results)
        print(f"  Targets: {len(results)}")
        print(f"  Source projects: {total_sources}")
        print(f"  Total chats to export: {total_chats}")
        print(f"{'═' * 60}")

        return results

    def _group_projects_by_target(
        self,
        projects: List[ProjectInfo],
    ) -> Dict[str, Tuple[Path, List[ProjectInfo]]]:
        """Group conversation projects that map to the same target folder.

        Looks up each project in the mapping config. Projects with
        action='skip' or no mapping are excluded. Groups by the
        resolved target directory path to correctly handle cases where
        the same target folder name has different docs_chats_path values.

        Args:
            projects: List of ProjectInfo from source discovery.

        Returns:
            Dict of display_key → (target_dir_path, [ProjectInfo list]).
            Ordered by first occurrence.
        """
        grouped: Dict[str, Tuple[Path, List[ProjectInfo]]] = {}

        for project_info in projects:
            mapping_key = (
                f"{project_info.source.value}{_KEY_SEP}{project_info.name}"
            )
            mapping = self.mapping_config.get_mapping(mapping_key)

            if mapping is None:
                logger.debug(
                    f"No mapping for '{mapping_key}', skipping"
                )
                continue

            if mapping.action == 'skip':
                logger.debug(
                    f"Mapping for '{mapping_key}' is skip, skipping"
                )
                continue

            if not mapping.target:
                logger.warning(
                    f"Mapping for '{mapping_key}' has no target, skipping"
                )
                continue

            target_dir = (
                self.root_dir / mapping.target / mapping.docs_chats_path
            )

            # Path confinement: ensure target_dir resolves inside root_dir
            resolved_target = target_dir.resolve()
            if not resolved_target.is_relative_to(self.root_dir):
                logger.warning(
                    f"Mapping for '{mapping_key}' resolves outside root "
                    f"({resolved_target}), skipping"
                )
                continue

            # Group by resolved path to handle different docs_chats_path
            # values for the same target folder correctly.
            group_key = str(resolved_target)

            if group_key not in grouped:
                grouped[group_key] = (target_dir, [])
            grouped[group_key][1].append(project_info)

        return grouped

    def _process_target(
        self,
        target_dir: Path,
        projects: List[ProjectInfo],
        tmp_base: Path,
    ) -> ExportResult:
        """Export and merge all source projects for one target folder.

        Args:
            target_dir: Full path to the target docs/chats directory.
            projects: List of source projects mapping to this target.
            tmp_base: Base temporary directory.

        Returns:
            ExportResult with counts and any errors.
        """
        # Derive a display-friendly name from target_dir relative to root
        try:
            display_name = str(target_dir.resolve().relative_to(self.root_dir))
        except ValueError:
            display_name = str(target_dir)

        result = ExportResult(
            target_name=display_name,
            target_dir=target_dir,
        )

        # Create a shared tmp dir for this target
        tmp_dir = tmp_base / _safe_dirname(display_name)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        source_label_parts = []
        for project_info in projects:
            label = SOURCE_LABELS.get(
                project_info.source, project_info.source.value
            )
            source_label_parts.append(f"[{label}] {project_info.name}")
            result.sources.append(
                (project_info.name, project_info.source)
            )

        print(f"\n{'─' * 60}")
        print_colored(f"📁 {display_name}", Colors.CYAN)
        for part in source_label_parts:
            print(f"   {part}")

        # Export each source project to an isolated subdirectory
        # to prevent within-batch filename overwrites, then consolidate
        # into the shared tmp dir. Filenames are content-derived by
        # export_project_chats() (LLM or first-message based), so we
        # preserve them as-is. Only add a numeric suffix on actual
        # same-name collisions between sources.
        # --- FILENAME NAMING CONVENTION (by design) ---
        # Filenames are generated by export_project_chats() using the
        # existing content-derived naming: LLM-generated titles or
        # first user message, same as claude-chat-manager.py single
        # exports. This is intentional — filenames reflect conversation
        # content, NOT source identity. Do NOT add source/project
        # prefixes to filenames; the ChatMerger handles deduplication
        # via content fingerprinting (first N message pairs), not by
        # filename matching. See: src/exporters.py → _generate_book_filename()
        #
        # Isolated subdirectories prevent within-batch overwrites when
        # two sources happen to produce the same content-derived name.
        # Numeric suffixes (-2, -3) are only added on actual collision.
        # ---
        total_exported = 0
        source_subdirs: List[Tuple[Path, ProjectInfo]] = []

        for project_info in projects:
            source_subdir = tmp_dir / _safe_dirname(
                f"{project_info.source.value}_{project_info.name}"
            )
            source_subdir.mkdir(parents=True, exist_ok=True)
            exported = self._export_project(
                project_info, source_subdir, result
            )
            total_exported += exported
            source_subdirs.append((source_subdir, project_info))

        # Consolidate: move files from isolated subdirs to shared tmp.
        # Preserve original content-derived filenames as-is.
        # On same-name collision between sources, add numeric suffix.
        # This is safe because ChatMerger matches by content, not name.
        for source_subdir, project_info in source_subdirs:
            for exported_file in source_subdir.rglob('*'):
                if not exported_file.is_file():
                    continue
                dest = tmp_dir / exported_file.name
                if dest.exists():
                    dest = self._find_unique_path(dest)
                shutil.move(str(exported_file), str(dest))

            shutil.rmtree(source_subdir, ignore_errors=True)

        result.chats_exported = total_exported

        if total_exported == 0:
            print_colored("   ⚠️  No chats exported", Colors.YELLOW)
            return result

        print(f"   Exported {total_exported} chats to tmp")

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Merge tmp → target
        new_count, update_count, skip_count, review_count = (
            self._merge_to_target(tmp_dir, target_dir, result)
        )
        result.new_files = new_count
        result.updated_files = update_count
        result.skipped_files = skip_count
        result.review_files = review_count

        # Summary line for this target
        parts = []
        if new_count > 0:
            parts.append(f"{new_count} new")
        if update_count > 0:
            parts.append(f"{update_count} updated")
        if skip_count > 0:
            parts.append(f"{skip_count} skipped")
        if review_count > 0:
            parts.append(f"{review_count} review")

        summary = ", ".join(parts) if parts else "nothing to merge"
        print_colored(f"   → {summary}", Colors.GREEN)

        return result

    def _export_project(
        self,
        project_info: ProjectInfo,
        tmp_dir: Path,
        result: ExportResult,
    ) -> int:
        """Export a single project's chats to the tmp directory.

        Args:
            project_info: Source project information.
            tmp_dir: Temporary directory for exported files.
            result: ExportResult to record errors into.

        Returns:
            Number of files exported.
        """
        try:
            exported_files = export_project_chats(
                project_path=project_info.path,
                export_dir=tmp_dir,
                format_type=self.export_format,
                source=project_info.source,
            )
            return len(exported_files)
        except ExportError as e:
            error_msg = (
                f"Export failed for {project_info.name} "
                f"[{project_info.source.value}]: {e}"
            )
            logger.error(error_msg)
            result.errors.append(error_msg)
            return 0
        except Exception as e:
            error_msg = (
                f"Unexpected error exporting {project_info.name} "
                f"[{project_info.source.value}]: {e}"
            )
            logger.error(error_msg)
            result.errors.append(error_msg)
            return 0

    def _merge_to_target(
        self,
        source_dir: Path,
        target_dir: Path,
        result: ExportResult,
    ) -> Tuple[int, int, int, int]:
        """Merge exported files from tmp into the target directory.

        Uses ChatMerger to analyze and execute merge decisions.

        Args:
            source_dir: Temporary directory with exported files.
            target_dir: Target docs/chats directory.
            result: ExportResult to record errors into.

        Returns:
            Tuple of (new_count, update_count, skip_count, review_count).
        """
        new_count = 0
        update_count = 0
        skip_count = 0
        review_count = 0

        try:
            decisions = self._merger.analyze_directories(
                source_dir, target_dir
            )
        except Exception as e:
            error_msg = f"Merge analysis failed for {target_dir}: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            return 0, 0, 0, 0

        for decision in decisions:
            if decision.action == MergeAction.NEW:
                if self._execute_merge(decision, target_dir, result):
                    new_count += 1
            elif decision.action == MergeAction.UPDATE:
                if self._execute_merge(decision, target_dir, result):
                    update_count += 1
            elif decision.action == MergeAction.SKIP:
                skip_count += 1
            elif decision.action == MergeAction.REVIEW:
                review_count += 1
                logger.info(
                    f"Review needed: {decision.source_file.name} "
                    f"({decision.reason})"
                )

        return new_count, update_count, skip_count, review_count

    def _execute_merge(
        self,
        decision: MergeDecision,
        target_dir: Path,
        result: ExportResult,
    ) -> bool:
        """Execute a single merge decision (NEW or UPDATE).

        Follows the same merge convention as merge-chats.py:
        - NEW: copy source file to target using its content-derived name.
          Unlike merge-chats.py (which overwrites), auto-export adds a
          numeric suffix on name collision since it runs unattended.
        - UPDATE: overwrite the matched target file (identified by
          content fingerprint, not filename). Creates .md.backup first.
        - Backup uses .md.backup extension (same as merge-chats.py).

        Args:
            decision: The merge decision to execute.
            target_dir: Target directory.
            result: ExportResult to record errors into.

        Returns:
            True if successful, False otherwise.
        """
        try:
            if decision.action == MergeAction.UPDATE:
                if not decision.target_file:
                    error_msg = (
                        f"UPDATE decision for {decision.source_file.name} "
                        f"is missing target_file"
                    )
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    return False
                dest = decision.target_file
            else:
                dest = target_dir / decision.source_file.name
                # For NEW files, avoid overwriting an existing file that
                # the merger didn't match (different content, same name).
                # This prevents cross-source/cross-run filename collisions.
                if dest.exists():
                    dest = self._find_unique_path(dest)

            # Path confinement check
            resolved_dest = dest.resolve()
            resolved_dir = target_dir.resolve()
            if not resolved_dest.is_relative_to(resolved_dir):
                error_msg = (
                    f"Refusing to write outside target: "
                    f"{resolved_dest} not inside {resolved_dir}"
                )
                logger.error(error_msg)
                result.errors.append(error_msg)
                return False

            # Create backup for updates (same convention as merge-chats.py)
            if decision.action == MergeAction.UPDATE and dest.exists():
                backup_path = dest.with_suffix('.md.backup')
                shutil.copy2(dest, backup_path)

            shutil.copy2(decision.source_file, dest)
            return True

        except OSError as e:
            error_msg = (
                f"Failed to merge {decision.source_file.name}: {e}"
            )
            logger.error(error_msg)
            result.errors.append(error_msg)
            return False

    @staticmethod
    def _find_unique_path(path: Path) -> Path:
        """Find a unique filename by appending a numeric suffix.

        Args:
            path: Original file path that already exists.

        Returns:
            A path with a numeric suffix that doesn't exist yet.
        """
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 2
        while True:
            candidate = parent / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _count_project_chats(self, project_info: ProjectInfo) -> int:
        """Count chat files in a project (for dry run).

        Args:
            project_info: Source project information.

        Returns:
            Number of chat files found.
        """
        try:
            files = get_project_chat_files(
                project_info.path,
                source=project_info.source,
                session_ids=project_info.session_ids,
            )
            return len(files)
        except Exception as e:
            logger.warning(
                f"Failed to count chats for {project_info.name}: {e}"
            )
            return 0


def print_results(results: List[ExportResult]) -> None:
    """Print formatted summary of all export results.

    Args:
        results: List of ExportResult objects from the pipeline.
    """
    total_exported = sum(r.chats_exported for r in results)
    total_new = sum(r.new_files for r in results)
    total_updated = sum(r.updated_files for r in results)
    total_skipped = sum(r.skipped_files for r in results)
    total_review = sum(r.review_files for r in results)
    total_errors = sum(len(r.errors) for r in results)

    print(f"\n{'═' * 60}")
    print_colored("📊 Auto-Export Summary", Colors.CYAN)
    print(f"{'═' * 60}")
    print(f"  Targets processed: {len(results)}")
    print(f"  Chats exported:    {total_exported}")
    print_colored(f"  New files:         {total_new}", Colors.GREEN)
    if total_updated > 0:
        print_colored(f"  Updated files:     {total_updated}", Colors.BLUE)
    if total_skipped > 0:
        print(f"  Skipped (up to date): {total_skipped}")
    if total_review > 0:
        print_colored(
            f"  Needs review:      {total_review}", Colors.YELLOW
        )
    if total_errors > 0:
        print_colored(f"  Errors:            {total_errors}", Colors.RED)
        for r in results:
            for err in r.errors:
                print_colored(f"    ⚠️  {err}", Colors.RED)
    print(f"{'═' * 60}")


def _safe_dirname(name: str) -> str:
    """Convert a target name to a safe directory name for tmp.

    Rejects traversal-dangerous names ('.', '..') and strips
    path separators. Falls back to a hash-based name if
    sanitization produces an empty or dangerous result.

    Args:
        name: Target folder name.

    Returns:
        Filesystem-safe directory name, guaranteed non-empty
        and free of '.', '..', or path separator characters.
    """
    import hashlib
    import re

    # Strip path separators and replace non-word chars (except hyphens)
    safe = re.sub(r'[^\w\-]', '_', name)

    # Strip leading/trailing dots and underscores
    safe = safe.strip('._')

    # Reject dangerous names or empty results
    if not safe or safe in ('.', '..'):
        # Generate a deterministic safe name from the original
        name_hash = hashlib.sha256(name.encode()).hexdigest()[:12]
        return f"target_{name_hash}"

    return safe

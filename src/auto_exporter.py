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
from .projects import list_all_projects

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

        # 2b. Flag projects with no mapping entry at all (not intentional skips)
        unmapped = self._find_unmapped_projects(all_projects)

        if not grouped:
            print_colored("ℹ️  No projects mapped for export.", Colors.YELLOW)
            self._print_unmapped_warning(unmapped)
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

        # 5. Warn about unmapped conversation projects (skipped silently)
        self._print_unmapped_warning(unmapped)

        return results

    def dry_run_report(self) -> List[ExportResult]:
        """Show what would happen without executing.

        Discovers projects, resolves mappings, exports each source
        project to an isolated temporary directory, and runs the real
        ChatMerger analysis to produce accurate new/update/skip/review
        counts. The target directory is never created or written to.

        Returns:
            List of ExportResult objects with accurate counts.

        Raises:
            ExportError: If project discovery fails entirely.
        """
        all_projects = list_all_projects(self.source_filter)
        grouped = self._group_projects_by_target(all_projects)
        unmapped = self._find_unmapped_projects(all_projects)

        if not grouped:
            print_colored("ℹ️  No projects mapped for export.", Colors.YELLOW)
            self._print_unmapped_warning(unmapped)
            return []

        results: List[ExportResult] = []
        tmp_base = Path(tempfile.mkdtemp(prefix='auto-export-dryrun-'))
        logger.info(f"Dry-run tmp directory: {tmp_base}")

        print_colored("\n📋 Dry Run — Export Plan", Colors.CYAN)
        print(f"{'═' * 60}")

        try:
            for _, (target_dir, projects) in grouped.items():
                result = self._analyze_target_dry_run(
                    target_dir, projects, tmp_base
                )
                existing = 0
                if target_dir.exists() and target_dir.is_dir():
                    existing = len(list(target_dir.glob('*.md')))

                print(f"\n  📁 {result.target_name}")
                for name, source in result.sources:
                    label = SOURCE_LABELS.get(source, source.value)
                    print(f"     [{label}] {name}")
                print(f"     Source chats:              {result.chats_exported}")
                print(f"     Existing files in target:  {existing}")
                print( "     Merge preview:")
                self._print_merge_counts(result, indent="       ")
                print(f"     Target: {target_dir}")
                for err in result.errors:
                    print_colored(f"     ⚠️  {err}", Colors.RED)

                results.append(result)
        finally:
            if not self.keep_tmp:
                try:
                    shutil.rmtree(tmp_base)
                except OSError as e:
                    logger.warning(f"Failed to clean up {tmp_base}: {e}")
            else:
                print_colored(
                    f"\nℹ️  Dry-run tmp kept at: {tmp_base}", Colors.CYAN
                )

        # Grand totals.
        totals = ExportResult(target_name="", target_dir=Path())
        for r in results:
            totals.chats_exported += r.chats_exported
            totals.new_files += r.new_files
            totals.updated_files += r.updated_files
            totals.skipped_files += r.skipped_files
            totals.review_files += r.review_files
            totals.errors.extend(r.errors)
        total_sources = sum(len(r.sources) for r in results)

        print(f"\n{'═' * 60}")
        print(f"  Targets:                  {len(results)}")
        print(f"  Source projects:          {total_sources}")
        print(f"  Total chats to export:    {totals.chats_exported}")
        self._print_merge_counts(totals, indent="  ")
        if totals.errors:
            print_colored(
                f"  ⚠️  Errors:               {len(totals.errors)}",
                Colors.RED,
            )
        print(f"{'═' * 60}")

        # Warn about unmapped conversation projects (skipped silently)
        self._print_unmapped_warning(unmapped)

        return results

    def _analyze_target_dry_run(
        self,
        target_dir: Path,
        projects: List[ProjectInfo],
        tmp_base: Path,
    ) -> ExportResult:
        """Export to tmp and analyze merge for one target (dry-run).

        Never writes to the target directory. Populates an ExportResult
        with accurate new/update/skip/review counts from ChatMerger.
        """
        try:
            display_name = str(target_dir.resolve().relative_to(self.root_dir))
        except ValueError:
            display_name = str(target_dir)

        result = ExportResult(target_name=display_name, target_dir=target_dir)
        for project_info in projects:
            result.sources.append((project_info.name, project_info.source))

        tmp_dir = tmp_base / _safe_dirname(display_name)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Real export to tmp — never touches target.
        result.chats_exported = self._collect_source_exports(
            projects, tmp_dir, result
        )
        if result.chats_exported == 0:
            return result

        # Target missing → every exported file will be new.
        if not target_dir.exists() or not target_dir.is_dir():
            result.new_files = len(list(tmp_dir.glob('*.md')))
            return result

        try:
            decisions = self._merger.analyze_directories(tmp_dir, target_dir)
        except Exception as e:
            error_msg = f"Dry-run merge analysis failed for {target_dir}: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            return result

        for decision in decisions:
            if decision.action == MergeAction.NEW:
                result.new_files += 1
            elif decision.action == MergeAction.UPDATE:
                result.updated_files += 1
            elif decision.action == MergeAction.SKIP:
                result.skipped_files += 1
            elif decision.action == MergeAction.REVIEW:
                result.review_files += 1

        return result

    @staticmethod
    def _print_merge_counts(result: ExportResult, indent: str = "") -> None:
        """Print the new/update/skip/review block for a result."""
        print_colored(
            f"{indent}🆕 New (will be added):    {result.new_files}",
            Colors.GREEN,
        )
        if result.updated_files > 0:
            print_colored(
                f"{indent}🔄 Update (will replace): {result.updated_files}",
                Colors.BLUE,
            )
        print(f"{indent}⏭️  Skip (already synced): {result.skipped_files}")
        if result.review_files > 0:
            print_colored(
                f"{indent}⚠️  Review (manual):       {result.review_files}",
                Colors.YELLOW,
            )

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

    def _find_unmapped_projects(
        self,
        projects: List[ProjectInfo],
    ) -> List[ProjectInfo]:
        """Find conversation projects with no mapping entry at all.

        Distinguishes "never learned" (user hasn't run ``--learn`` since
        the project appeared) from "intentionally skipped" (user chose
        skip during learn mode, which writes a mapping with action='skip').
        Only the former indicates chats are silently falling through.

        Args:
            projects: All discovered conversation projects.

        Returns:
            Projects with no entry in the mapping config. Preserves
            discovery order.
        """
        unmapped: List[ProjectInfo] = []
        for project_info in projects:
            mapping_key = (
                f"{project_info.source.value}{_KEY_SEP}{project_info.name}"
            )
            if self.mapping_config.get_mapping(mapping_key) is None:
                unmapped.append(project_info)
        return unmapped

    @staticmethod
    def _print_unmapped_warning(unmapped: List[ProjectInfo]) -> None:
        """Print a warning block for conversation projects with no mapping.

        Highlights chats that were skipped because the project has never
        been mapped via ``--learn``. Nothing is printed when the list is
        empty.

        Args:
            unmapped: Projects missing from the mapping config.
        """
        if not unmapped:
            return

        print_colored(
            f"\n⚠️  Unmapped projects: {len(unmapped)} "
            f"(chats skipped — no project mapping)",
            Colors.YELLOW,
        )
        for project_info in unmapped:
            label = SOURCE_LABELS.get(
                project_info.source, project_info.source.value
            )
            print_colored(
                f"    [{label}] {project_info.name}", Colors.YELLOW
            )
        print_colored(
            "    → Run `auto-export.py --root <root> --learn --update` "
            "to map them.",
            Colors.YELLOW,
        )

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
        # and consolidate into the shared tmp dir. See
        # _collect_source_exports for the full naming-convention
        # contract (why filenames stay content-derived, not source-
        # prefixed). Numeric suffixes are only added on same-name
        # collisions between sources.
        total_exported = self._collect_source_exports(
            projects, tmp_dir, result
        )

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

    def _collect_source_exports(
        self,
        projects: List[ProjectInfo],
        tmp_dir: Path,
        result: ExportResult,
    ) -> int:
        """Export each source project to tmp and consolidate filenames.

        Exports each project to an isolated subdirectory first to prevent
        within-batch overwrites, then moves files into the shared tmp_dir.

        --- FILENAME NAMING CONVENTION (by design) ---
        Filenames are generated by export_project_chats() using the
        existing content-derived naming: LLM-generated titles or first
        user message, same as claude-chat-manager.py single exports.
        This is intentional — filenames reflect conversation content,
        NOT source identity. Do NOT add source/project prefixes to
        filenames; the ChatMerger handles deduplication via content
        fingerprinting (first N message pairs), not by filename matching.
        See: src/exporters.py → _generate_book_filename()

        On same-name collision between sources, a numeric suffix (-2,
        -3) is appended. This is safe because ChatMerger matches by
        content, not name.

        Args:
            projects: Source projects to export.
            tmp_dir: Shared target tmp directory to consolidate into.
            result: ExportResult to record per-project errors into.

        Returns:
            Total number of files exported across all projects.
        """
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
        for source_subdir, _ in source_subdirs:
            for exported_file in source_subdir.rglob('*'):
                if not exported_file.is_file():
                    continue
                dest = tmp_dir / exported_file.name
                if dest.exists():
                    dest = self._find_unique_path(dest)
                shutil.move(str(exported_file), str(dest))

            shutil.rmtree(source_subdir, ignore_errors=True)

        return total_exported

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

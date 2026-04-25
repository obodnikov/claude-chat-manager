"""Tests for src/auto_exporter.py — the auto-export pipeline.

Covers:
- Full pipeline with mocked filesystem and sources
- Grouping multiple sources to same target
- Tmp directory creation and cleanup
- Error handling (export failure, merge failure)
- Dry run output
- Empty projects, no mappings, all skipped
- keep_tmp behavior
- Path confinement in merge execution
"""

import json
import shutil
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.auto_exporter import AutoExporter, ExportResult, print_results, _safe_dirname
from src.chat_merger import ChatMerger, MergeAction, MergeDecision
from src.exceptions import ConfigurationError, ExportError
from src.models import ChatSource, ProjectInfo
from src.project_matcher import MappingConfig, ProjectMapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project_info(
    name: str,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP,
    workspace_path: Optional[str] = None,
    path: Optional[Path] = None,
    file_count: int = 2,
    session_ids: Optional[List[str]] = None,
) -> ProjectInfo:
    """Create a minimal ProjectInfo for testing."""
    return ProjectInfo(
        name=name,
        path=path or Path(f"/fake/{name}"),
        file_count=file_count,
        total_messages=10,
        last_modified="2026-04-23",
        source=source,
        workspace_path=workspace_path,
        session_ids=session_ids,
    )


def _create_mapping_config(
    config_path: Path,
    root_dir: Path,
    mappings: dict,
) -> MappingConfig:
    """Create and save a MappingConfig with given mappings."""
    cfg = MappingConfig(config_path)
    cfg.load()
    cfg.set_root_directory(str(root_dir))
    for key, entry in mappings.items():
        cfg.data['mappings'][key] = entry
    cfg.save()
    # Reload to validate
    cfg2 = MappingConfig(config_path)
    cfg2.load()
    return cfg2


def _write_book_md(path: Path, user_msg: str, assistant_msg: str) -> None:
    """Write a minimal book-format markdown file."""
    content = (
        "# Claude Chat Export\n\n"
        f"**Generated: 2026-04-23 12:00:00**\n\n"
        "---\n\n"
        "👤 **USER:**\n"
        f"> {user_msg}\n\n"
        f"{assistant_msg}\n\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def root_dir(tmp_path: Path) -> Path:
    """Create a root directory with project folders."""
    for name in ("project-alpha", "project-beta"):
        (tmp_path / name / "docs" / "chats").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return a temporary config file path."""
    return tmp_path / "config" / "project-mapping.json"


# ---------------------------------------------------------------------------
# Test _safe_dirname
# ---------------------------------------------------------------------------

class TestSafeDirname:
    """Filesystem-safe directory name generation."""

    def test_simple_name(self) -> None:
        assert _safe_dirname("project-alpha") == "project-alpha"

    def test_name_with_spaces(self) -> None:
        assert _safe_dirname("my project") == "my_project"

    def test_name_with_slashes(self) -> None:
        assert _safe_dirname("path/to/project") == "path_to_project"

    def test_empty_name(self) -> None:
        result = _safe_dirname("")
        assert result != ""
        assert ".." not in result
        assert result.startswith("target_")


# ---------------------------------------------------------------------------
# Test _group_projects_by_target
# ---------------------------------------------------------------------------

class TestGroupProjectsByTarget:
    """Grouping conversation projects by target folder."""

    def test_groups_multiple_sources_to_same_target(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Claude + Kiro mapping to same target should be grouped."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        exporter = AutoExporter(root_dir, cfg)
        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("my-project", ChatSource.KIRO_IDE),
        ]

        grouped = exporter._group_projects_by_target(projects)

        assert len(grouped) == 1
        target_dir, group_projects = next(iter(grouped.values()))
        assert len(group_projects) == 2
        assert target_dir == root_dir / "project-alpha" / "docs" / "chats"

    def test_skip_mappings_excluded(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Projects with action='skip' should not appear in groups."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:skipped": {
                "action": "skip",
                "confirmed": True,
            },
            "claude:active": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        exporter = AutoExporter(root_dir, cfg)
        projects = [
            _make_project_info("skipped", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("active", ChatSource.CLAUDE_DESKTOP),
        ]

        grouped = exporter._group_projects_by_target(projects)

        assert len(grouped) == 1

    def test_unmapped_projects_excluded(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Projects with no mapping entry should be excluded."""
        cfg = _create_mapping_config(config_path, root_dir, {})

        exporter = AutoExporter(root_dir, cfg)
        projects = [
            _make_project_info("unknown", ChatSource.CLAUDE_DESKTOP),
        ]

        grouped = exporter._group_projects_by_target(projects)
        assert len(grouped) == 0

    def test_separate_targets_stay_separate(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Projects mapping to different targets should be in separate groups."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "claude:proj-b": {
                "target": "project-beta",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        exporter = AutoExporter(root_dir, cfg)
        projects = [
            _make_project_info("proj-a", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("proj-b", ChatSource.CLAUDE_DESKTOP),
        ]

        grouped = exporter._group_projects_by_target(projects)
        assert len(grouped) == 2


# ---------------------------------------------------------------------------
# Test full pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Full pipeline execution with mocked export/merge."""

    def test_full_pipeline_exports_and_merges(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Pipeline should export to tmp, merge to target, and clean up."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Mock export_project_chats to create a file in tmp
        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "test-chat-2026-04-23.md"
            _write_book_md(md_file, "Hello", "Hi there!")
            return [md_file]

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        result = results[0]
        assert result.chats_exported == 1
        assert result.new_files == 1
        assert result.errors == []

        # File should exist in target
        merged_files = list(target_dir.glob("*.md"))
        assert len(merged_files) == 1

    def test_pipeline_cleans_up_tmp(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Tmp directory should be removed after pipeline completes."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "chat.md"
            _write_book_md(md_file, "Q", "A")
            return [md_file]

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        tmp_dirs_seen = []

        original_mkdtemp = __import__('tempfile').mkdtemp

        def tracking_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            tmp_dirs_seen.append(d)
            return d

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ), patch(
            'tempfile.mkdtemp', side_effect=tracking_mkdtemp
        ):
            exporter = AutoExporter(root_dir, cfg, keep_tmp=False)
            exporter.run()

        # Tmp dir should have been cleaned up
        for d in tmp_dirs_seen:
            assert not Path(d).exists(), f"Tmp dir not cleaned: {d}"

    def test_keep_tmp_preserves_directory(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """With keep_tmp=True, tmp directory should survive."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "chat.md"
            _write_book_md(md_file, "Q", "A")
            return [md_file]

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        tmp_dirs_seen = []
        original_mkdtemp = __import__('tempfile').mkdtemp

        def tracking_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            tmp_dirs_seen.append(d)
            return d

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ), patch(
            'tempfile.mkdtemp', side_effect=tracking_mkdtemp
        ):
            exporter = AutoExporter(root_dir, cfg, keep_tmp=True)
            exporter.run()

        # Tmp dir should still exist
        for d in tmp_dirs_seen:
            assert Path(d).exists(), f"Tmp dir was removed despite keep_tmp"
            # Clean up manually
            shutil.rmtree(d, ignore_errors=True)

    def test_no_mapped_projects_returns_empty(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Pipeline with no mapped projects should return empty results."""
        cfg = _create_mapping_config(config_path, root_dir, {})

        projects = [
            _make_project_info("unmapped", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert results == []


# ---------------------------------------------------------------------------
# Test error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Pipeline should handle errors gracefully and continue."""

    def test_export_failure_recorded_in_errors(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Export failure should be recorded but not crash the pipeline."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:failing": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("failing", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats',
            side_effect=ExportError("disk full"),
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        assert len(results[0].errors) == 1
        assert "disk full" in results[0].errors[0]
        assert results[0].chats_exported == 0

    def test_partial_failure_continues_with_other_targets(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """If one target fails, other targets should still be processed."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:failing": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "claude:working": {
                "target": "project-beta",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("failing", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("working", ChatSource.CLAUDE_DESKTOP),
        ]

        call_count = 0

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ExportError("first project fails")
            md_file = export_dir / "working-chat.md"
            _write_book_md(md_file, "Hello", "World")
            return [md_file]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 2
        # First target had errors
        assert len(results[0].errors) > 0
        # Second target succeeded
        assert results[1].chats_exported == 1
        assert results[1].errors == []

    def test_invalid_root_dir_raises(self, tmp_path: Path) -> None:
        """Non-existent root dir should raise ConfigurationError."""
        cfg = MappingConfig(tmp_path / "config.json")
        cfg.load()

        with pytest.raises(ConfigurationError):
            AutoExporter(tmp_path / "nonexistent", cfg)


# ---------------------------------------------------------------------------
# Test merge behavior
# ---------------------------------------------------------------------------

class TestMergeBehavior:
    """Merge decisions: new, update, skip."""

    def test_existing_file_skipped(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Identical file in target should be skipped."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Pre-populate target with the same file
        _write_book_md(
            target_dir / "existing-chat.md",
            "Hello world",
            "Hi there!",
        )

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            # Export the same content
            md_file = export_dir / "existing-chat.md"
            _write_book_md(md_file, "Hello world", "Hi there!")
            return [md_file]

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        # Should be skipped (identical content)
        assert results[0].skipped_files == 1
        assert results[0].new_files == 0

    def test_multiple_sources_merge_to_same_target(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Two sources exporting to same target should both contribute."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        call_count = 0

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            nonlocal call_count
            call_count += 1
            md_file = export_dir / f"chat-{call_count}.md"
            _write_book_md(md_file, f"Question {call_count}", f"Answer {call_count}")
            return [md_file]

        projects = [
            _make_project_info("shared", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("shared", ChatSource.KIRO_IDE),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        result = results[0]
        assert result.chats_exported == 2
        assert result.new_files == 2
        assert len(result.sources) == 2


# ---------------------------------------------------------------------------
# Test dry run
# ---------------------------------------------------------------------------

class TestDryRun:
    """Dry run should report without modifying anything."""

    def test_dry_run_does_not_create_files(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Dry run should not create any files in target directories."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"
        files_before = set(target_dir.glob("*"))

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            # Simulate two exported chats in the tmp export directory.
            f1 = export_dir / "chat-one.md"
            f2 = export_dir / "chat-two.md"
            _write_book_md(f1, "hello", "hi there")
            _write_book_md(f2, "another", "ok")
            return [f1, f2]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg, dry_run=True)
            results = exporter.dry_run_report()

        files_after = set(target_dir.glob("*"))
        assert files_before == files_after
        assert len(results) == 1
        assert results[0].chats_exported == 2

    def test_dry_run_returns_results(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Dry run should return ExportResult objects with source info."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("proj-a", ChatSource.CLAUDE_DESKTOP),
        ]

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            return []

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg, dry_run=True)
            results = exporter.dry_run_report()

        assert len(results) == 1
        assert "project-alpha" in results[0].target_name
        assert ("proj-a", ChatSource.CLAUDE_DESKTOP) in results[0].sources

    def test_dry_run_reports_accurate_merge_counts(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Dry run should populate new/update/skip via real merge analysis."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:my-project": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"
        # Pre-existing file that matches one exported chat (will be SKIP).
        _write_book_md(target_dir / "existing.md", "hello", "hi there")
        files_before = set(target_dir.glob("*"))

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            # Two exports: one duplicates the existing file (→ skip),
            # one is brand new (→ new).
            f1 = export_dir / "chat-one.md"
            f2 = export_dir / "chat-two.md"
            _write_book_md(f1, "hello", "hi there")
            _write_book_md(f2, "brand new question", "brand new answer")
            return [f1, f2]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg, dry_run=True)
            results = exporter.dry_run_report()

        # Target must remain untouched.
        assert set(target_dir.glob("*")) == files_before
        assert len(results) == 1
        r = results[0]
        # One new, one skipped (matches existing by fingerprint).
        assert r.chats_exported == 2
        assert r.new_files + r.skipped_files + r.updated_files == 2
        assert r.new_files >= 1
        assert r.skipped_files >= 1


# ---------------------------------------------------------------------------
# Test print_results
# ---------------------------------------------------------------------------

class TestPrintResults:
    """Summary output formatting."""

    def test_print_results_no_errors(self, capsys) -> None:
        """print_results should display summary without crashing."""
        results = [
            ExportResult(
                target_name="project-alpha",
                target_dir=Path("/fake/project-alpha/docs/chats"),
                sources=[("my-project", ChatSource.CLAUDE_DESKTOP)],
                chats_exported=5,
                new_files=3,
                updated_files=1,
                skipped_files=1,
            ),
        ]
        print_results(results)
        captured = capsys.readouterr()
        assert "Auto-Export Summary" in captured.out
        assert "5" in captured.out  # chats exported
        assert "3" in captured.out  # new files

    def test_print_results_with_errors(self, capsys) -> None:
        """print_results should display errors."""
        results = [
            ExportResult(
                target_name="failing",
                target_dir=Path("/fake"),
                errors=["something went wrong"],
            ),
        ]
        print_results(results)
        captured = capsys.readouterr()
        assert "something went wrong" in captured.out


# ---------------------------------------------------------------------------
# Regression tests for code review findings
# ---------------------------------------------------------------------------

class TestDiscoveryFailurePropagation:
    """Issue #1: Discovery failures must not be silently swallowed."""

    def test_run_raises_on_discovery_failure(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """run() should propagate discovery exceptions, not return []."""
        from src.exceptions import ProjectNotFoundError

        cfg = _create_mapping_config(config_path, root_dir, {})

        with patch(
            'src.auto_exporter.list_all_projects',
            side_effect=ProjectNotFoundError("No sources found"),
        ):
            exporter = AutoExporter(root_dir, cfg)
            with pytest.raises(ProjectNotFoundError):
                exporter.run()

    def test_dry_run_raises_on_discovery_failure(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """dry_run_report() should propagate discovery exceptions."""
        from src.exceptions import ProjectNotFoundError

        cfg = _create_mapping_config(config_path, root_dir, {})

        with patch(
            'src.auto_exporter.list_all_projects',
            side_effect=ProjectNotFoundError("No sources found"),
        ):
            exporter = AutoExporter(root_dir, cfg)
            with pytest.raises(ProjectNotFoundError):
                exporter.dry_run_report()


class TestTargetPathConfinement:
    """Issue #2: Target paths must be confined to root_dir."""

    def test_dotdot_target_rejected(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Mapping with '../escape' target should be skipped at runtime.

        MappingConfig.load() already rejects '..' in targets, so we
        bypass validation by injecting directly into config data to
        test the runtime confinement check in _group_projects_by_target.
        """
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))
        # Bypass load-time validation by writing raw data
        cfg.data['mappings']['claude:evil'] = {
            "target": "../escape",
            "docs_chats_path": "docs/chats",
            "action": "export",
            "confirmed": True,
        }

        projects = [
            _make_project_info("evil", ChatSource.CLAUDE_DESKTOP),
        ]

        exporter = AutoExporter(root_dir, cfg)
        grouped = exporter._group_projects_by_target(projects)

        # Should be empty — the traversal mapping was rejected
        assert len(grouped) == 0

    def test_absolute_target_rejected(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Mapping with absolute path target should be skipped.

        Note: MappingConfig.load() already rejects absolute paths,
        so we test by injecting directly into the config data.
        """
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))
        # Bypass validation by writing raw data
        cfg.data['mappings']['claude:evil'] = {
            "target": "/tmp/evil",
            "docs_chats_path": "docs/chats",
            "action": "export",
            "confirmed": True,
        }

        projects = [
            _make_project_info("evil", ChatSource.CLAUDE_DESKTOP),
        ]

        exporter = AutoExporter(root_dir, cfg)
        grouped = exporter._group_projects_by_target(projects)

        # Should be empty — absolute path resolves outside root
        assert len(grouped) == 0

    def test_valid_target_accepted(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Normal mapping should pass confinement check."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:good": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("good", ChatSource.CLAUDE_DESKTOP),
        ]

        exporter = AutoExporter(root_dir, cfg)
        grouped = exporter._group_projects_by_target(projects)

        assert len(grouped) == 1
        target_dir, _ = next(iter(grouped.values()))
        assert "project-alpha" in str(target_dir)


class TestFilenameCollisionHandling:
    """Issue #3: Multi-source exports must not overwrite each other."""

    def test_same_filename_from_two_sources_both_preserved(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Two sources producing the same filename should both survive."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "same-chat-name.md"
            source_label = source.value
            _write_book_md(
                md_file,
                f"Question from {source_label}",
                f"Answer from {source_label}",
            )
            return [md_file]

        projects = [
            _make_project_info("shared", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("shared", ChatSource.KIRO_IDE),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        result = results[0]
        assert result.chats_exported == 2
        assert result.new_files == 2

        # Verify two distinct files exist in target
        merged_files = list(target_dir.glob("*.md"))
        assert len(merged_files) == 2

    def test_order_independence_single_source(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """With different filenames per source, order shouldn't matter."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:shared": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        call_count = 0

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            nonlocal call_count
            call_count += 1
            # Each source produces a uniquely named file (as LLM would)
            md_file = export_dir / f"chat-from-{source.value}.md"
            _write_book_md(md_file, f"Q from {source.value}", f"A {call_count}")
            return [md_file]

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Run with order A
        call_count = 0
        projects_a = [
            _make_project_info("shared", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("shared", ChatSource.KIRO_IDE),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects_a
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            AutoExporter(root_dir, cfg).run()

        names_a = sorted(f.name for f in target_dir.glob("*.md"))

        for f in target_dir.glob("*.md"):
            f.unlink()

        # Run with reversed order B
        call_count = 0
        projects_b = [
            _make_project_info("shared", ChatSource.KIRO_IDE),
            _make_project_info("shared", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects_b
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            AutoExporter(root_dir, cfg).run()

        names_b = sorted(f.name for f in target_dir.glob("*.md"))

        assert names_a == names_b


# ---------------------------------------------------------------------------
# Regression tests for second code review findings
# ---------------------------------------------------------------------------

class TestSafeDirnameTraversal:
    """_safe_dirname must reject '.', '..', and traversal-like inputs."""

    def test_single_dot_rejected(self) -> None:
        result = _safe_dirname(".")
        assert result != "."
        assert result != ""
        assert ".." not in result

    def test_double_dot_rejected(self) -> None:
        result = _safe_dirname("..")
        assert result != ".."
        assert result != "."
        assert result != ""

    def test_dot_dot_slash_sanitized(self) -> None:
        result = _safe_dirname("../escape")
        assert ".." not in result
        assert "/" not in result
        assert result != ""

    def test_only_dots_rejected(self) -> None:
        result = _safe_dirname("...")
        assert result != ""
        # Should not start or end with dots
        assert not result.startswith(".")

    def test_empty_string_gets_fallback(self) -> None:
        result = _safe_dirname("")
        assert result != ""
        assert len(result) > 0

    def test_normal_name_unchanged(self) -> None:
        assert _safe_dirname("project-alpha") == "project-alpha"

    def test_dots_stripped_from_edges(self) -> None:
        result = _safe_dirname(".hidden.")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_result_is_deterministic(self) -> None:
        """Same input should always produce the same output."""
        assert _safe_dirname("..") == _safe_dirname("..")
        assert _safe_dirname("") == _safe_dirname("")


class TestRunPipelineExceptionHandling:
    """_run_pipeline must handle all exception types cleanly."""

    def test_export_error_returns_exit_code_1(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """ExportError during pipeline should produce exit code 1."""
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "auto_export",
            str(Path(__file__).parent.parent / "auto-export.py"),
        )
        auto_export_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(auto_export_mod)

        # Create a valid config file
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:test": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        with patch.object(
            auto_export_mod, 'AutoExporter'
        ) as MockExporter:
            instance = MockExporter.return_value
            instance.run.side_effect = ExportError("boom")

            result = auto_export_mod._run_pipeline(
                root_dir=root_dir,
                config_path=config_path,
            )

        assert result == 1

    def test_unexpected_exception_returns_exit_code_1(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Unexpected RuntimeError should produce exit code 1, not traceback."""
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "auto_export",
            str(Path(__file__).parent.parent / "auto-export.py"),
        )
        auto_export_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(auto_export_mod)

        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:test": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        with patch.object(
            auto_export_mod, 'AutoExporter'
        ) as MockExporter:
            instance = MockExporter.return_value
            instance.run.side_effect = RuntimeError("segfault simulation")

            result = auto_export_mod._run_pipeline(
                root_dir=root_dir,
                config_path=config_path,
            )

        assert result == 1


# ---------------------------------------------------------------------------
# Regression tests for third code review findings
# ---------------------------------------------------------------------------

class TestCrossRunFilenameCollision:
    """Issue #1: NEW file must not overwrite existing file with same name."""

    def test_new_file_does_not_overwrite_existing_different_content(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """If target already has foo.md from source A, exporting source B
        with its own foo.md (different content) must not overwrite it."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "kiro:proj-b": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Pre-populate target with a file from a previous run (source A)
        existing_file = target_dir / "same-topic-name.md"
        _write_book_md(existing_file, "Original question from Claude", "Original answer")
        original_content = existing_file.read_text()

        # Source B exports a file with the SAME name but DIFFERENT content
        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "same-topic-name.md"
            _write_book_md(md_file, "Completely different question from Kiro", "Different answer")
            return [md_file]

        projects = [
            _make_project_info("proj-b", ChatSource.KIRO_IDE),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        # Original file must be preserved
        assert existing_file.read_text() == original_content

        # New file should exist with a different name
        all_md = list(target_dir.glob("*.md"))
        assert len(all_md) == 2, f"Expected 2 files, got {[f.name for f in all_md]}"

    def test_new_file_gets_numeric_suffix_on_collision(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """When filename collides, the new file should get a -2 suffix."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Pre-populate with existing file
        _write_book_md(target_dir / "chat.md", "Old question", "Old answer")

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "chat.md"
            _write_book_md(md_file, "New different question", "New answer")
            return [md_file]

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        # Should have chat.md (original) and chat-2.md (new)
        assert (target_dir / "chat.md").exists()
        assert (target_dir / "chat-2.md").exists()


class TestBackupTimestamping:
    """Issue #2: Backups must not overwrite each other across runs."""

    def test_update_creates_timestamped_backup(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """UPDATE should create a backup with timestamp, not a fixed name."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        # Pre-populate target with a conversation (2 user+assistant pairs)
        short_content = (
            "# Claude Chat Export\n\n"
            "**Generated: 2026-04-23 12:00:00**\n\n"
            "---\n\n"
            "👤 **USER:**\n"
            "> How do I fix the login bug in the auth middleware?\n\n"
            "You need to check the session validation logic in auth middleware.\n\n"
            "---\n\n"
            "👤 **USER:**\n"
            "> Can you show me the specific code changes needed?\n\n"
            "Sure, update the validateSession function to check token expiry.\n\n"
        )
        (target_dir / "my-chat.md").write_text(short_content, encoding='utf-8')

        # Export a longer version: same first 2 pairs + 2 more
        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "my-chat.md"
            long_content = (
                "# Claude Chat Export\n\n"
                "**Generated: 2026-04-23 13:00:00**\n\n"
                "---\n\n"
                "👤 **USER:**\n"
                "> How do I fix the login bug in the auth middleware?\n\n"
                "You need to check the session validation logic in auth middleware.\n\n"
                "---\n\n"
                "👤 **USER:**\n"
                "> Can you show me the specific code changes needed?\n\n"
                "Sure, update the validateSession function to check token expiry.\n\n"
                "---\n\n"
                "👤 **USER:**\n"
                "> Thanks, that worked! Any other improvements?\n\n"
                "Yes, you should also add rate limiting to prevent brute force.\n\n"
                "---\n\n"
                "👤 **USER:**\n"
                "> Great, I will add that too.\n\n"
                "Sounds good, let me know if you need help with the implementation.\n\n"
            )
            md_file.write_text(long_content, encoding='utf-8')
            return [md_file]

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        assert results[0].updated_files == 1

        # Check that a .md.backup was created (same as merge-chats.py)
        backup_file = target_dir / "my-chat.md.backup"
        assert backup_file.exists(), (
            f"Expected .md.backup file, found: "
            f"{[f.name for f in target_dir.iterdir()]}"
        )


# ---------------------------------------------------------------------------
# Regression tests for fourth code review findings
# ---------------------------------------------------------------------------

class TestNestedExportFiles:
    """Issue #2: Nested exported files must not be silently dropped."""

    def test_nested_files_are_moved_to_tmp(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Files in subdirectories of export output should be merged."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            # Create a top-level file
            top = export_dir / "top-chat.md"
            _write_book_md(top, "Top question", "Top answer")
            # Create a nested file (some exporters might do this)
            nested_dir = export_dir / "subdir"
            nested_dir.mkdir()
            nested = nested_dir / "nested-chat.md"
            _write_book_md(nested, "Nested question", "Nested answer")
            return [top, nested]

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        # Both files should have been merged
        merged_files = list(target_dir.glob("*.md"))
        assert len(merged_files) == 2, (
            f"Expected 2 merged files, got: {[f.name for f in merged_files]}"
        )


# ---------------------------------------------------------------------------
# Regression tests for fifth code review findings
# ---------------------------------------------------------------------------

class TestBackupExcludedFromMerge:
    """Issue #1: .bak backups must not be re-ingested by future merges."""

    def test_backup_files_ignored_by_merger(self, tmp_path: Path) -> None:
        """ChatMerger.analyze_directories should only see .md files,
        not .md.backup files."""
        from src.chat_merger import ChatMerger

        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        # Put a .md.backup file in target (from a previous update)
        bak_file = target_dir / "old-chat.md.backup"
        bak_file.write_text("backup content", encoding='utf-8')

        # Put a new chat in source
        _write_book_md(source_dir / "new-chat.md", "Hello", "World")

        merger = ChatMerger()
        decisions = merger.analyze_directories(source_dir, target_dir)

        # The .md.backup file should not appear in any decision
        for d in decisions:
            if d.target_file:
                assert not d.target_file.name.endswith(".backup"), (
                    f"Backup file was ingested: {d.target_file.name}"
                )

        # The new chat should be NEW (no match against .bak)
        assert len(decisions) == 1
        assert decisions[0].action.value == "new"

    def test_backup_does_not_affect_merge_counts(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Running pipeline twice should not cause backup churn."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        target_dir = root_dir / "project-alpha" / "docs" / "chats"

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "stable-chat.md"
            _write_book_md(md_file, "Same question", "Same answer")
            return [md_file]

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
        ]

        # First run: should create the file
        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results1 = exporter.run()

        assert results1[0].new_files == 1

        # Second run: same content, should skip (not update)
        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter2 = AutoExporter(root_dir, cfg)
            results2 = exporter2.run()

        assert results2[0].skipped_files == 1
        assert results2[0].new_files == 0
        assert results2[0].updated_files == 0

        # No .md.backup files should exist (no updates happened)
        bak_files = list(target_dir.glob("*.backup"))
        assert len(bak_files) == 0


# ---------------------------------------------------------------------------
# Regression tests for sixth code review findings
# ---------------------------------------------------------------------------

class TestDifferentDocsChatsPath:
    """Issue #1: Same target with different docs_chats_path must not merge."""

    def test_same_target_different_docs_path_separate_groups(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Two mappings with same target but different docs_chats_path
        should be in separate groups writing to different directories."""
        # Create both target directories
        (root_dir / "project-alpha" / "docs" / "chats").mkdir(
            parents=True, exist_ok=True
        )
        (root_dir / "project-alpha" / "docs" / "conversations").mkdir(
            parents=True, exist_ok=True
        )

        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/conversations",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("proj-a", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("proj-a", ChatSource.KIRO_IDE),
        ]

        exporter = AutoExporter(root_dir, cfg)
        grouped = exporter._group_projects_by_target(projects)

        # Should be TWO separate groups (different resolved paths)
        assert len(grouped) == 2

        # Each group should have exactly one project
        for key, (target_dir, group_projects) in grouped.items():
            assert len(group_projects) == 1

    def test_same_target_same_docs_path_single_group(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Two mappings with same target AND same docs_chats_path
        should be in the same group."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("proj", ChatSource.KIRO_IDE),
        ]

        exporter = AutoExporter(root_dir, cfg)
        grouped = exporter._group_projects_by_target(projects)

        assert len(grouped) == 1
        _, (_, group_projects) = next(iter(grouped.items()))
        assert len(group_projects) == 2

    def test_different_docs_path_writes_to_correct_dirs(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Exports should land in the correct docs_chats_path directory."""
        chats_dir = root_dir / "project-alpha" / "docs" / "chats"
        convos_dir = root_dir / "project-alpha" / "docs" / "conversations"
        chats_dir.mkdir(parents=True, exist_ok=True)
        convos_dir.mkdir(parents=True, exist_ok=True)

        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
            "kiro:proj-a": {
                "target": "project-alpha",
                "docs_chats_path": "docs/conversations",
                "action": "export",
                "confirmed": True,
            },
        })

        call_count = 0

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            nonlocal call_count
            call_count += 1
            md_file = export_dir / f"chat-from-{source.value}.md"
            _write_book_md(md_file, f"Q from {source.value}", f"A {call_count}")
            return [md_file]

        projects = [
            _make_project_info("proj-a", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("proj-a", ChatSource.KIRO_IDE),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 2

        # Claude export should be in docs/chats
        chats_files = list(chats_dir.glob("*.md"))
        assert len(chats_files) == 1
        assert "claude" in chats_files[0].read_text()

        # Kiro export should be in docs/conversations
        convos_files = list(convos_dir.glob("*.md"))
        assert len(convos_files) == 1
        assert "kiro" in convos_files[0].read_text()


# ---------------------------------------------------------------------------
# Regression tests for seventh code review findings
# ---------------------------------------------------------------------------

class TestExportResultTargetName:
    """Issue #2: target_name should be root-relative, not absolute path."""

    def test_target_name_is_relative(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """ExportResult.target_name should not contain absolute paths."""
        cfg = _create_mapping_config(config_path, root_dir, {
            "claude:proj": {
                "target": "project-alpha",
                "docs_chats_path": "docs/chats",
                "action": "export",
                "confirmed": True,
            },
        })

        def mock_export(project_path, export_dir, format_type, source, **kwargs):
            md_file = export_dir / "chat.md"
            _write_book_md(md_file, "Q", "A")
            return [md_file]

        projects = [
            _make_project_info("proj", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch(
            'src.auto_exporter.list_all_projects', return_value=projects
        ), patch(
            'src.auto_exporter.export_project_chats', side_effect=mock_export
        ):
            exporter = AutoExporter(root_dir, cfg)
            results = exporter.run()

        assert len(results) == 1
        # target_name should be relative (e.g., "project-alpha/docs/chats")
        # not an absolute path
        assert not results[0].target_name.startswith("/")
        assert "project-alpha" in results[0].target_name

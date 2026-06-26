"""Tests for projects.py — Step 5: Cline VS Code wiring.

Covers list_all_projects(), find_project_by_name(), and get_project_chat_files()
for ChatSource.CLINE_VSCODE, using a temporary globalStorage fixture.
"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import ProjectNotFoundError
from src.models import ChatSource, ProjectInfo
from src.projects import (
    find_project_by_name,
    get_project_chat_files,
    list_all_projects,
    _workspace_path_basename,
)


# ============================================================================
# Fixture helpers (mirrors pattern in test_cline_vscode_projects.py)
# ============================================================================

def _make_task_entry(
    task_id: str,
    cwd: str,
    ts: int,
    task: str = "Test task",
    model: str = "claude-opus-4.6",
) -> dict:
    """Create a minimal taskHistory.json entry."""
    return {
        "id": task_id,
        "ts": ts,
        "task": task,
        "cwdOnTaskInitialization": cwd,
        "modelId": model,
        "totalCost": 0.01,
    }


def _setup_globalStorage(
    base_dir: Path,
    task_entries: List[dict],
    create_ui_messages: bool = True,
) -> Path:
    """Build a minimal fake globalStorage directory.

    Args:
        base_dir: Root temp directory used as the Cline data dir.
        task_entries: Entries to write into state/taskHistory.json.
        create_ui_messages: Whether to create ui_messages.json per task.

    Returns:
        Path to the Cline data directory (same as base_dir).
    """
    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True)
    tasks_dir = base_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    (state_dir / "taskHistory.json").write_text(
        json.dumps(task_entries), encoding="utf-8"
    )

    if create_ui_messages:
        for entry in task_entries:
            task_dir = tasks_dir / entry["id"]
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "ui_messages.json").write_text(
                json.dumps([
                    {"ts": entry.get("ts", 1000), "type": "say",
                     "say": "task", "text": entry.get("task", "Hello")}
                ]),
                encoding="utf-8",
            )

    return base_dir


def _make_config_mock(
    cline_dir: Path,
    cline_valid: bool = True,
    kiro_valid: bool = False,
    codex_valid: bool = False,
    claude_dir: Path = None,
) -> MagicMock:
    """Build a MagicMock that stands in for src.projects.config.

    Args:
        cline_dir: Path returned by cline_vscode_data_dir.
        cline_valid: Return value of validate_cline_vscode_directory().
        kiro_valid: Return value of validate_kiro_directory().
        codex_valid: Return value of validate_codex_directory().
        claude_dir: Path returned by claude_projects_dir (non-existent by default).

    Returns:
        Configured MagicMock.
    """
    mock = MagicMock()
    mock.cline_vscode_data_dir = cline_dir
    mock.validate_cline_vscode_directory.return_value = cline_valid
    mock.validate_kiro_directory.return_value = kiro_valid
    mock.validate_codex_directory.return_value = codex_valid
    # Point Claude dir at something that doesn't exist so it's skipped
    mock.claude_projects_dir = claude_dir or (cline_dir / "_no_claude")
    return mock


# ============================================================================
# _workspace_path_basename helper
# ============================================================================

class TestWorkspacePathBasename:
    """Unit tests for the cross-platform workspace path basename helper."""

    def test_posix_path(self):
        assert _workspace_path_basename("/home/user/my-project") == "my-project"

    def test_windows_path_on_posix(self):
        # PurePosixPath('C:\\Users\\me\\repo').name == 'C:\\Users\\me\\repo'
        # so the helper must fall through to PureWindowsPath
        result = _workspace_path_basename("C:\\Users\\me\\cool-tool")
        assert result == "cool-tool"

    def test_nested_posix_path(self):
        assert _workspace_path_basename("/deep/nested/path/proj") == "proj"

    def test_bare_name(self):
        # No separators — name equals the whole string; fallback returns it
        assert _workspace_path_basename("myrepo") == "myrepo"


# ============================================================================
# list_all_projects — Cline VS Code
# ============================================================================

class TestListAllProjectsClineVscode:
    """list_all_projects() correctly discovers and surfaces Cline VS Code projects."""

    def test_cline_project_appears_in_list(self):
        """A Cline workspace is returned as a ProjectInfo with the right source."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("1000", "/home/user/my-project", 1_000_000_000_000)],
            )
            cfg = _make_config_mock(cline_dir)
            with patch("src.projects.config", cfg):
                projects = list_all_projects(source_filter=ChatSource.CLINE_VSCODE)

        assert len(projects) == 1
        p = projects[0]
        assert p.source == ChatSource.CLINE_VSCODE
        assert p.name == "my-project"
        assert p.workspace_path == "/home/user/my-project"

    def test_session_ids_are_task_ids(self):
        """session_ids hold task ID strings, not full filesystem paths."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [
                    _make_task_entry("100", "/home/user/proj", 1_000_000_000_000),
                    _make_task_entry("200", "/home/user/proj", 2_000_000_000_000),
                ],
            )
            cfg = _make_config_mock(cline_dir)
            with patch("src.projects.config", cfg):
                projects = list_all_projects(source_filter=ChatSource.CLINE_VSCODE)

        assert len(projects) == 1
        assert projects[0].file_count == 2
        assert set(projects[0].session_ids) == {"100", "200"}
        # Must not contain path separators
        for sid in projects[0].session_ids:
            assert "/" not in sid
            assert "\\" not in sid

    def test_multiple_cwds_produce_multiple_projects(self):
        """Tasks from different cwds each become a separate ProjectInfo."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [
                    _make_task_entry("100", "/home/user/alpha", 1_000_000_000_000),
                    _make_task_entry("200", "/home/user/beta", 2_000_000_000_000),
                ],
            )
            cfg = _make_config_mock(cline_dir)
            with patch("src.projects.config", cfg):
                projects = list_all_projects(source_filter=ChatSource.CLINE_VSCODE)

        assert len(projects) == 2
        names = {p.name for p in projects}
        assert names == {"alpha", "beta"}

    def test_project_path_points_to_tasks_subdir(self):
        """ProjectInfo.path is cline_vscode_data_dir / 'tasks'."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/proj", 1_000_000_000_000)],
            )
            cfg = _make_config_mock(cline_dir)
            with patch("src.projects.config", cfg):
                projects = list_all_projects(source_filter=ChatSource.CLINE_VSCODE)

        assert projects[0].path == cline_dir / "tasks"

    def test_skipped_when_directory_invalid(self):
        """No Cline projects appear when validate_cline_vscode_directory() is False."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = Path(tmpdir)
            cfg = _make_config_mock(cline_dir, cline_valid=False)
            with patch("src.projects.config", cfg):
                with pytest.raises(ProjectNotFoundError):
                    list_all_projects(source_filter=ChatSource.CLINE_VSCODE)


# ============================================================================
# find_project_by_name — Cline VS Code
# ============================================================================

class TestFindProjectByNameClineVscode:
    """find_project_by_name() matches Cline workspaces by name and by path basename."""

    def _run_find(self, cline_dir: Path, name: str) -> ProjectInfo:
        cfg = _make_config_mock(cline_dir)
        with patch("src.projects.config", cfg):
            return find_project_by_name(name, source_filter=ChatSource.CLINE_VSCODE)

    def test_match_by_workspace_name(self):
        """find_project_by_name matches the workspace_name (cwd basename)."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/my-repo", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "my-repo")

        assert result is not None
        assert result.source == ChatSource.CLINE_VSCODE
        assert result.name == "my-repo"
        assert result.workspace_path == "/home/user/my-repo"

    def test_match_is_case_insensitive(self):
        """Name matching is case-insensitive."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/MyRepo", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "myrepo")

        assert result is not None
        assert result.name == "MyRepo"

    def test_match_by_posix_path_basename(self):
        """find_project_by_name matches against Path(workspace_path).name for POSIX paths."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/deep/nested/path/cool-tool", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "cool-tool")

        assert result is not None
        assert result.workspace_path == "/deep/nested/path/cool-tool"

    def test_match_by_windows_path_basename(self):
        """find_project_by_name matches against Windows-style workspace paths."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "C:\\Users\\me\\win-project", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "win-project")

        assert result is not None
        assert result.workspace_path == "C:\\Users\\me\\win-project"

    def test_returns_none_when_not_found(self):
        """Returns None if no workspace matches the given name."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/alpha", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "nonexistent-project")

        assert result is None

    def test_session_ids_are_task_ids_on_match(self):
        """Matched ProjectInfo carries task ID session_ids (not full paths)."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [
                    _make_task_entry("100", "/home/user/proj", 1_000_000_000_000),
                    _make_task_entry("200", "/home/user/proj", 2_000_000_000_000),
                ],
            )
            result = self._run_find(cline_dir, "proj")

        assert result is not None
        assert set(result.session_ids) == {"100", "200"}
        for sid in result.session_ids:
            assert "/" not in sid

    def test_result_path_points_to_tasks_subdir(self):
        """Matched ProjectInfo.path is cline_vscode_data_dir / 'tasks'."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/proj", 1_000_000_000_000)],
            )
            result = self._run_find(cline_dir, "proj")

        assert result is not None
        assert result.path == cline_dir / "tasks"


# ============================================================================
# get_project_chat_files — Cline VS Code
# ============================================================================

class TestGetProjectChatFilesClineVscode:
    """get_project_chat_files() with ChatSource.CLINE_VSCODE."""

    def test_returns_existing_task_dirs(self):
        """Returns task directory paths for task IDs that exist on disk."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [
                    _make_task_entry("100", "/home/user/proj", 1_000_000_000_000),
                    _make_task_entry("200", "/home/user/proj", 2_000_000_000_000),
                ],
            )
            tasks_dir = cline_dir / "tasks"

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["100", "200"],
            )

        assert len(result) == 2
        result_names = {p.name for p in result}
        assert result_names == {"100", "200"}

    def test_skips_deleted_task_dirs(self):
        """Task IDs whose directories don't exist are silently skipped."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/proj", 1_000_000_000_000)],
            )
            tasks_dir = cline_dir / "tasks"

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["100", "999"],  # "999" never created
            )

        assert len(result) == 1
        assert result[0].name == "100"

    def test_returns_directories_not_files(self):
        """Returned paths are directories (the exporter reads files inside them)."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("100", "/home/user/proj", 1_000_000_000_000)],
            )
            tasks_dir = cline_dir / "tasks"

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["100"],
            )

            # Assert inside the with block while tmpdir still exists
            assert len(result) == 1
            assert result[0].is_dir()

    def test_empty_session_ids_returns_empty(self):
        """Passing session_ids=[] returns an empty list."""
        result = get_project_chat_files(
            project_path=Path("/tmp/irrelevant"),
            source=ChatSource.CLINE_VSCODE,
            session_ids=[],
        )
        assert result == []

    def test_none_session_ids_returns_empty(self):
        """Passing session_ids=None returns an empty list."""
        result = get_project_chat_files(
            project_path=Path("/tmp/irrelevant"),
            source=ChatSource.CLINE_VSCODE,
            session_ids=None,
        )
        assert result == []

    def test_sorted_newest_first_by_mtime(self):
        """Results are sorted by directory mtime, newest first."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [
                    _make_task_entry("old", "/home/user/proj", 1_000_000_000_000),
                    _make_task_entry("new", "/home/user/proj", 2_000_000_000_000),
                ],
            )
            tasks_dir = cline_dir / "tasks"
            old_dir = tasks_dir / "old"
            new_dir = tasks_dir / "new"

            # Set mtimes explicitly so the test isn't timing-dependent
            old_time = 1_000_000_000.0
            new_time = 2_000_000_000.0
            os.utime(old_dir, (old_time, old_time))
            os.utime(new_dir, (new_time, new_time))

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["old", "new"],
            )

            assert result[0].name == "new"
            assert result[1].name == "old"

    # -----------------------------------------------------------------------
    # Path confinement / traversal rejection
    # -----------------------------------------------------------------------

    def test_rejects_task_id_with_forward_slash(self):
        """Task IDs containing '/' are rejected before filesystem access."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            # Create a directory that would be reached via traversal
            outside = Path(tmpdir) / "outside"
            outside.mkdir()

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["../outside"],
            )

        assert result == []

    def test_rejects_task_id_with_backslash(self):
        """Task IDs containing '\\' are rejected."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()

            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=["..\\outside"],
            )

        assert result == []

    def test_rejects_absolute_path_outside_tasks_root(self):
        """An absolute path string that resolves outside tasks_dir is rejected."""
        with TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / "tasks"
            tasks_dir.mkdir()
            # Create a real directory outside
            outside = Path(tmpdir) / "outside"
            outside.mkdir()

            # Pass the absolute path of 'outside' as a task ID.
            # It contains '/' so must be rejected at the separator check.
            result = get_project_chat_files(
                project_path=tasks_dir,
                source=ChatSource.CLINE_VSCODE,
                session_ids=[str(outside)],
            )

        assert result == []

    def test_valid_task_id_not_rejected(self):
        """A plain alphanumeric task ID resolves correctly and is not rejected."""
        with TemporaryDirectory() as tmpdir:
            cline_dir = _setup_globalStorage(
                Path(tmpdir),
                [_make_task_entry("1781697826685", "/home/user/proj", 1_000_000_000_000)],
            )
            result = get_project_chat_files(
                project_path=cline_dir / "tasks",
                source=ChatSource.CLINE_VSCODE,
                session_ids=["1781697826685"],
            )

        assert len(result) == 1
        assert result[0].name == "1781697826685"

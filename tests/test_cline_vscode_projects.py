"""Tests for cline_vscode_projects module."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.cline_vscode_projects import (
    ClineVscodeTaskInfo,
    ClineVscodeWorkspace,
    discover_cline_vscode_workspaces,
    get_cline_vscode_session_files,
)


# ============================================================================
# Test Helpers
# ============================================================================

def _make_task_history_entry(
    task_id: str = "1781697826685",
    cwd: str = "/home/user/project",
    ts: int = 1781697826685,
    task: str = "Implement feature",
    model: str = "claude-opus-4.6",
) -> dict:
    """Create a taskHistory.json entry."""
    return {
        "id": task_id,
        "ts": ts,
        "task": task,
        "cwdOnTaskInitialization": cwd,
        "modelId": model,
        "totalCost": 0.05,
        "tokensIn": 1000,
        "tokensOut": 500,
    }


def _setup_cline_data(
    base_dir: Path,
    task_entries: list,
    create_dirs: bool = True,
    create_ui_messages: bool = True,
) -> Path:
    """Set up a fake Cline data directory with taskHistory and task dirs.

    Args:
        base_dir: Temp directory to use as cline data dir
        task_entries: List of taskHistory entry dicts
        create_dirs: Whether to create task directories
        create_ui_messages: Whether to create ui_messages.json in each task dir

    Returns:
        Path to the cline data directory
    """
    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True)
    tasks_dir = base_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    # Write taskHistory.json
    with open(state_dir / "taskHistory.json", 'w', encoding='utf-8') as f:
        json.dump(task_entries, f)

    if create_dirs:
        for entry in task_entries:
            task_dir = tasks_dir / entry["id"]
            task_dir.mkdir(parents=True, exist_ok=True)
            if create_ui_messages:
                ui_file = task_dir / "ui_messages.json"
                ui_file.write_text(json.dumps([
                    {"ts": entry.get("ts", 1000), "type": "say",
                     "say": "task", "text": entry.get("task", "Hello")}
                ]))

    return base_dir


# ============================================================================
# Tests for discover_cline_vscode_workspaces
# ============================================================================

class TestDiscoverClineWorkspaces:
    """Tests for discover_cline_vscode_workspaces function."""

    def test_groups_tasks_by_cwd(self):
        """Tasks with the same cwd are grouped into one workspace."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project-a", 1000, "Task 1"),
                _make_task_history_entry("200", "/project-a", 2000, "Task 2"),
                _make_task_history_entry("300", "/project-b", 3000, "Task 3"),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))

            assert len(workspaces) == 2
            # Should be sorted newest-first
            ws_paths = [w.workspace_path for w in workspaces]
            assert "/project-b" in ws_paths
            assert "/project-a" in ws_paths

    def test_multiple_cwds_create_multiple_workspaces(self):
        """Different cwds create separate workspaces."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/proj1", 1000),
                _make_task_history_entry("200", "/proj2", 2000),
                _make_task_history_entry("300", "/proj3", 3000),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 3

    def test_skips_tasks_with_missing_dir(self):
        """Tasks whose task dir doesn't exist are skipped."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000),
                _make_task_history_entry("200", "/project", 2000),
            ]
            # Only create dir for first task
            _setup_cline_data(Path(tmpdir), entries, create_dirs=False)
            tasks_dir = Path(tmpdir) / "tasks"
            task_100 = tasks_dir / "100"
            task_100.mkdir(parents=True)
            (task_100 / "ui_messages.json").write_text("[]")

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            # Only 1 task discovered (task 200 dir missing)
            assert len(workspaces) == 1
            assert workspaces[0].session_count == 1

    def test_skips_tasks_without_conversation_files(self):
        """Tasks with no conversation files are skipped."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000),
            ]
            # Create dir but no conversation files
            _setup_cline_data(Path(tmpdir), entries, create_ui_messages=False)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 0

    def test_last_modified_is_newest_task(self):
        """last_modified reflects the newest task timestamp."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000000000000),
                _make_task_history_entry("200", "/project", 1700000000000),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1
            # last_modified should be from ts=1700000000000 (newer)
            assert workspaces[0].last_modified != "Unknown"

    def test_workspaces_sorted_newest_first(self):
        """Workspaces are sorted by last_modified (newest first)."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/old-proj", 1000000000000),
                _make_task_history_entry("200", "/new-proj", 1700000000000),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces[0].workspace_path == "/new-proj"
            assert workspaces[1].workspace_path == "/old-proj"

    def test_empty_task_history_returns_empty(self):
        """Empty taskHistory.json returns empty list."""
        with TemporaryDirectory() as tmpdir:
            _setup_cline_data(Path(tmpdir), [])
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_missing_task_history_returns_empty(self):
        """Missing taskHistory.json returns empty list (no crash)."""
        with TemporaryDirectory() as tmpdir:
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_invalid_json_task_history_returns_empty(self):
        """Invalid JSON in taskHistory.json returns empty list."""
        with TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "taskHistory.json").write_text("not json")
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_skips_entries_without_cwd(self):
        """Entries missing cwdOnTaskInitialization are skipped."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                {"id": "100", "ts": 1000, "task": "No cwd task"},
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_workspace_name_is_basename(self):
        """workspace_name is the basename of the cwd path."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/home/user/my-project", 1000),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces[0].workspace_name == "my-project"


# ============================================================================
# Tests for get_cline_vscode_session_files
# ============================================================================

class TestGetClineSessionFiles:
    """Tests for get_cline_vscode_session_files function."""

    def test_returns_task_dirs(self):
        """Returns task directory paths for tasks with conversation files."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000),
                _make_task_history_entry("200", "/project", 2000),
            ]
            cline_dir = _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(cline_dir)
            assert len(workspaces) == 1

            files = get_cline_vscode_session_files(workspaces[0])
            assert len(files) == 2
            # Should be task directories, not individual files
            for f in files:
                assert f.is_dir()
                assert (f / "ui_messages.json").exists()

    def test_includes_tasks_with_only_api_history(self):
        """Tasks with only api_conversation_history.json are included."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000),
            ]
            # Create task dir with only api_history (no ui_messages)
            _setup_cline_data(Path(tmpdir), entries, create_ui_messages=False)
            task_dir = Path(tmpdir) / "tasks" / "100"
            (task_dir / "api_conversation_history.json").write_text(json.dumps([
                {"role": "user", "content": [{"type": "text", "text": "hello"}]}
            ]))

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1

            files = get_cline_vscode_session_files(workspaces[0])
            assert len(files) == 1
            assert files[0] == task_dir

    def test_empty_workspace_returns_empty(self):
        """Workspace with no tasks returns empty list."""
        workspace = ClineVscodeWorkspace(
            workspace_path="/project",
            workspace_name="project",
            tasks=[],
            session_count=0,
        )
        assert get_cline_vscode_session_files(workspace) == []


# ============================================================================
# Robustness tests for malformed taskHistory entries
# ============================================================================

class TestDiscoveryClineRobustness:
    """Tests for malformed taskHistory.json entries."""

    def test_numeric_id_converted_to_string(self):
        """Numeric task id is converted to string and used."""
        with TemporaryDirectory() as tmpdir:
            # Use numeric id in JSON but create dir with string version
            entries = [{"id": 100, "ts": 1000, "task": "Test",
                        "cwdOnTaskInitialization": "/project"}]
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "taskHistory.json").write_text(json.dumps(entries))
            tasks_dir = Path(tmpdir) / "tasks" / "100"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "ui_messages.json").write_text('[]')

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1
            assert workspaces[0].tasks[0].task_id == "100"

    def test_null_id_skipped(self):
        """Entry with null id is skipped."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                {"id": None, "ts": 1000, "cwdOnTaskInitialization": "/proj"},
                _make_task_history_entry("200", "/proj", 2000),
            ]
            _setup_cline_data(Path(tmpdir), [_make_task_history_entry("200", "/proj", 2000)])
            # Rewrite taskHistory with the null-id entry included
            state_path = Path(tmpdir) / "state" / "taskHistory.json"
            state_path.write_text(json.dumps(entries))

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1
            assert workspaces[0].session_count == 1

    def test_null_cwd_skipped(self):
        """Entry with null cwd is skipped."""
        with TemporaryDirectory() as tmpdir:
            entries = [{"id": "100", "ts": 1000, "cwdOnTaskInitialization": None}]
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "taskHistory.json").write_text(json.dumps(entries))
            tasks_dir = Path(tmpdir) / "tasks" / "100"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "ui_messages.json").write_text('[]')

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_invalid_total_cost_defaults_to_zero(self):
        """Non-numeric totalCost defaults to 0.0."""
        with TemporaryDirectory() as tmpdir:
            entries = [{"id": "100", "ts": 1000, "task": "Test",
                        "cwdOnTaskInitialization": "/project",
                        "totalCost": "not a number"}]
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "taskHistory.json").write_text(json.dumps(entries))
            tasks_dir = Path(tmpdir) / "tasks" / "100"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "ui_messages.json").write_text('[]')

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1
            assert workspaces[0].tasks[0].total_cost == 0.0

    def test_malformed_entries_mixed_with_valid(self):
        """Malformed entries don't crash discovery of valid entries."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                "not a dict",
                {"id": None},
                {"id": "", "cwdOnTaskInitialization": "/proj"},
                _make_task_history_entry("300", "/proj", 3000),
            ]
            # Only create dir for the valid entry
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "taskHistory.json").write_text(json.dumps(entries))
            tasks_dir = Path(tmpdir) / "tasks" / "300"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "ui_messages.json").write_text(json.dumps([
                {"ts": 3000, "type": "say", "say": "task", "text": "Hello"}
            ]))

            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1
            assert workspaces[0].session_count == 1

    def test_session_files_sorted_newest_first(self):
        """get_cline_vscode_session_files returns tasks sorted by timestamp."""
        with TemporaryDirectory() as tmpdir:
            entries = [
                _make_task_history_entry("100", "/project", 1000),
                _make_task_history_entry("300", "/project", 3000),
                _make_task_history_entry("200", "/project", 2000),
            ]
            _setup_cline_data(Path(tmpdir), entries)
            workspaces = discover_cline_vscode_workspaces(Path(tmpdir))
            assert len(workspaces) == 1

            files = get_cline_vscode_session_files(workspaces[0])
            # Should be sorted newest first: 300, 200, 100
            assert files[0].name == "300"
            assert files[1].name == "200"
            assert files[2].name == "100"

"""Tests for codex_projects module."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.codex_projects import (
    CodexSessionInfo,
    CodexWorkspace,
    discover_codex_workspaces,
    get_codex_session_files
)


def _create_rollout_file(
    base_dir: Path,
    date_path: str,
    filename: str,
    cwd: str,
    session_id: str = "test-uuid",
    timestamp: str = "2026-02-20T09:00:00.000Z"
) -> Path:
    """Create a minimal rollout file with session_meta."""
    dir_path = base_dir / 'sessions' / date_path
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / filename
    session_meta = json.dumps({
        "timestamp": timestamp,
        "type": "session_meta",
        "payload": {
            "id": session_id,
            "timestamp": timestamp,
            "cwd": cwd,
            "cli_version": "0.104.0",
            "model_provider": "openai",
            "git": {"branch": "main"}
        }
    })
    file_path.write_text(session_meta + '\n')
    return file_path


class TestDiscoverCodexWorkspaces:
    """Tests for discover_codex_workspaces function."""

    def test_discover_single_project(self):
        """Single cwd should produce single workspace."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1
            assert workspaces[0].workspace_name == "project-a"
            assert workspaces[0].workspace_path == "/home/user/project-a"
            assert workspaces[0].session_count == 1

    def test_discover_multiple_projects(self):
        """Sessions with different cwds should produce separate workspaces."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T10-00-00-uuid2.jsonl",
                cwd="/home/user/project-b",
                session_id="uuid2"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 2
            names = {w.workspace_name for w in workspaces}
            assert "project-a" in names
            assert "project-b" in names

    def test_group_sessions_by_cwd(self):
        """Multiple sessions with same cwd should be grouped."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/19",
                "rollout-2026-02-19T09-00-00-uuid1.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid1",
                timestamp="2026-02-19T09:00:00.000Z"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid2.jsonl",
                cwd="/home/user/project-a",
                session_id="uuid2",
                timestamp="2026-02-20T09:00:00.000Z"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1
            assert workspaces[0].session_count == 2

    def test_empty_sessions_dir(self):
        """Empty sessions directory returns empty list."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            (codex_dir / 'sessions').mkdir()

            workspaces = discover_codex_workspaces(codex_dir)
            assert workspaces == []

    def test_missing_sessions_dir(self):
        """Missing sessions directory returns empty list."""
        with TemporaryDirectory() as tmpdir:
            workspaces = discover_codex_workspaces(Path(tmpdir))
            assert workspaces == []

    def test_invalid_rollout_file_skipped(self):
        """Files with invalid JSON should be skipped gracefully."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            sessions_dir = codex_dir / 'sessions' / '2026' / '02' / '20'
            sessions_dir.mkdir(parents=True)

            # Invalid JSON file
            invalid_file = sessions_dir / 'rollout-invalid.jsonl'
            invalid_file.write_text('not valid json\n')

            # Valid file
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-2026-02-20T09-00-00-uuid1.jsonl",
                cwd="/home/user/project",
                session_id="uuid1"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1

    def test_workspaces_sorted_by_last_modified(self):
        """Workspaces should be sorted newest first."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/18",
                "rollout-old.jsonl",
                cwd="/home/user/old-project",
                session_id="uuid1",
                timestamp="2026-02-18T09:00:00.000Z"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-new.jsonl",
                cwd="/home/user/new-project",
                session_id="uuid2",
                timestamp="2026-02-20T09:00:00.000Z"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 2
            assert workspaces[0].workspace_name == "new-project"
            assert workspaces[1].workspace_name == "old-project"

    def test_session_with_empty_cwd_skipped(self):
        """Sessions with empty cwd should be skipped."""
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-empty-cwd.jsonl",
                cwd="",
                session_id="uuid1"
            )
            _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-valid.jsonl",
                cwd="/home/user/project",
                session_id="uuid2"
            )

            workspaces = discover_codex_workspaces(codex_dir)
            assert len(workspaces) == 1
            assert workspaces[0].workspace_name == "project"


class TestGetCodexSessionFiles:
    """Tests for get_codex_session_files function."""

    def test_returns_existing_files(self):
        with TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir)
            file1 = _create_rollout_file(
                codex_dir, "2026/02/20",
                "rollout-1.jsonl", cwd="/project"
            )
            file2 = _create_rollout_file(
                codex_dir, "2026/02/19",
                "rollout-2.jsonl", cwd="/project"
            )

            workspace = CodexWorkspace(
                workspace_path="/project",
                workspace_name="project",
                sessions=[
                    CodexSessionInfo(
                        session_id="1", file_path=file1,
                        cwd="/project", timestamp=""
                    ),
                    CodexSessionInfo(
                        session_id="2", file_path=file2,
                        cwd="/project", timestamp=""
                    ),
                ],
                session_count=2
            )

            files = get_codex_session_files(workspace)
            assert len(files) == 2

    def test_filters_missing_files(self):
        workspace = CodexWorkspace(
            workspace_path="/project",
            workspace_name="project",
            sessions=[
                CodexSessionInfo(
                    session_id="1",
                    file_path=Path("/nonexistent/file.jsonl"),
                    cwd="/project", timestamp=""
                ),
            ],
            session_count=1
        )

        files = get_codex_session_files(workspace)
        assert len(files) == 0

"""Tests for pi coding agent project discovery (src/pi_projects.py)."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from src.pi_projects import (
    PiSessionInfo,
    PiWorkspace,
    discover_pi_workspaces,
    get_pi_session_files,
    clear_pi_workspace_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the workspace discovery cache before each test."""
    clear_pi_workspace_cache()
    yield
    clear_pi_workspace_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_file(
    sessions_dir: Path,
    cwd: str,
    session_id: str,
    timestamp: str,
    subdir: str = "session-dir",
) -> Path:
    """Write a minimal pi session JSONL file and return its path."""
    slot = sessions_dir / subdir
    slot.mkdir(parents=True, exist_ok=True)
    file_path = slot / f"{timestamp.replace(':', '-')}_{session_id}.jsonl"
    header = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": timestamp,
        "cwd": cwd,
    }
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
    return file_path


# ---------------------------------------------------------------------------
# discover_pi_workspaces
# ---------------------------------------------------------------------------


class TestDiscoverPiWorkspaces:
    def test_single_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _make_session_file(
            sessions_dir,
            cwd="/home/user/project-a",
            session_id="uuid-001",
            timestamp="2026-06-01T10:00:00.000Z",
        )
        workspaces = discover_pi_workspaces(tmp_path)
        assert len(workspaces) == 1
        ws = workspaces[0]
        assert ws.workspace_path == "/home/user/project-a"
        assert ws.workspace_name == "project-a"
        assert ws.session_count == 1
        assert ws.pi_data_dir == tmp_path

    def test_groups_by_cwd(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        # Two sessions in project-a, one in project-b
        _make_session_file(sessions_dir, "/home/user/project-a", "uuid-001",
                           "2026-06-01T10:00:00.000Z", "dir-a")
        _make_session_file(sessions_dir, "/home/user/project-a", "uuid-002",
                           "2026-06-02T11:00:00.000Z", "dir-a")
        _make_session_file(sessions_dir, "/home/user/project-b", "uuid-003",
                           "2026-06-01T09:00:00.000Z", "dir-b")

        workspaces = discover_pi_workspaces(tmp_path)
        assert len(workspaces) == 2

        by_path = {ws.workspace_path: ws for ws in workspaces}
        assert by_path["/home/user/project-a"].session_count == 2
        assert by_path["/home/user/project-b"].session_count == 1

    def test_sorted_newest_first(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _make_session_file(sessions_dir, "/home/user/old-project", "uuid-old",
                           "2025-01-01T00:00:00.000Z", "dir-old")
        _make_session_file(sessions_dir, "/home/user/new-project", "uuid-new",
                           "2026-06-28T12:00:00.000Z", "dir-new")

        workspaces = discover_pi_workspaces(tmp_path)
        assert workspaces[0].workspace_path == "/home/user/new-project"
        assert workspaces[1].workspace_path == "/home/user/old-project"

    def test_last_modified_is_newest_timestamp(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _make_session_file(sessions_dir, "/home/user/proj", "uuid-a",
                           "2026-06-01T08:00:00.000Z", "dir-a1")
        _make_session_file(sessions_dir, "/home/user/proj", "uuid-b",
                           "2026-06-28T15:30:00.000Z", "dir-a2")

        workspaces = discover_pi_workspaces(tmp_path)
        assert len(workspaces) == 1
        # last_modified should reflect the newer timestamp
        assert "2026-06-28" in workspaces[0].last_modified

    def test_empty_sessions_dir_returns_empty(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        assert discover_pi_workspaces(tmp_path) == []

    def test_absent_sessions_dir_returns_empty(self, tmp_path):
        # No sessions/ subdirectory at all
        assert discover_pi_workspaces(tmp_path) == []

    def test_ignores_non_jsonl_files(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        # .wingman-titles.json has wrong extension — must not be treated as a session
        (sessions_dir / ".wingman-titles.json").write_text('{"version":1,"titles":{}}')
        # A random .txt file
        (sessions_dir / "notes.txt").write_text("hello")
        assert discover_pi_workspaces(tmp_path) == []

    def test_ignores_corrupt_jsonl(self, tmp_path):
        sessions_dir = tmp_path / "sessions" / "subdir"
        sessions_dir.mkdir(parents=True)
        bad = sessions_dir / "corrupt.jsonl"
        bad.write_text("{bad json\n")
        # Should return empty rather than raise
        assert discover_pi_workspaces(tmp_path) == []

    def test_ignores_jsonl_with_wrong_type(self, tmp_path):
        sessions_dir = tmp_path / "sessions" / "subdir"
        sessions_dir.mkdir(parents=True)
        wrong = sessions_dir / "codex-style.jsonl"
        wrong.write_text(json.dumps({"type": "session_meta", "id": "x"}) + "\n")
        assert discover_pi_workspaces(tmp_path) == []

    def test_naive_timestamp_does_not_crash(self, tmp_path):
        """A session with a naive (no offset/Z) ISO timestamp must not raise TypeError."""
        sessions_dir = tmp_path / "sessions" / "dir-naive"
        sessions_dir.mkdir(parents=True)
        naive_file = sessions_dir / "naive_session.jsonl"
        naive_file.write_text(
            json.dumps({"type": "session", "version": 3, "id": "uuid-naive",
                        "timestamp": "2026-06-28T12:00:00",  # no Z / offset
                        "cwd": "/home/user/naive-project"}) + "\n"
        )
        # Must not raise TypeError (naive vs aware datetime comparison)
        workspaces = discover_pi_workspaces(tmp_path)
        assert len(workspaces) == 1
        assert workspaces[0].workspace_path == "/home/user/naive-project"
        assert "2026-06-28" in workspaces[0].last_modified

    def test_unknown_timestamp_sorts_last(self, tmp_path):
        """A workspace with unparseable timestamps must sort after ones with real timestamps."""
        sessions_dir = tmp_path / "sessions"

        # Valid-timestamp workspace
        _make_session_file(sessions_dir, "/home/user/good-project", "uuid-good",
                           "2026-06-28T12:00:00.000Z", "dir-good")

        # Corrupt-timestamp workspace: header parses fine but timestamp is empty
        slot = sessions_dir / "dir-bad"
        slot.mkdir(parents=True)
        bad_file = slot / "session_bad.jsonl"
        import json as _json
        bad_file.write_text(
            _json.dumps({"type": "session", "version": 3, "id": "uuid-bad",
                         "timestamp": "", "cwd": "/home/user/bad-project"}) + "\n"
        )

        workspaces = discover_pi_workspaces(tmp_path)
        assert len(workspaces) == 2
        # Workspace with a real timestamp must come first
        assert workspaces[0].workspace_path == "/home/user/good-project"
        assert workspaces[1].workspace_path == "/home/user/bad-project"
        assert workspaces[1].last_modified == "Unknown"

    def test_workspace_name_is_cwd_basename(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _make_session_file(sessions_dir, "/very/deep/nested/my-repo", "uuid-1",
                           "2026-06-28T00:00:00.000Z")
        workspaces = discover_pi_workspaces(tmp_path)
        assert workspaces[0].workspace_name == "my-repo"


# ---------------------------------------------------------------------------
# get_pi_session_files
# ---------------------------------------------------------------------------


class TestGetPiSessionFiles:
    def test_returns_existing_paths_only(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        f1 = _make_session_file(sessions_dir, "/proj", "uuid-1",
                                "2026-06-01T10:00:00.000Z", "d1")
        f2 = _make_session_file(sessions_dir, "/proj", "uuid-2",
                                "2026-06-02T10:00:00.000Z", "d2")

        workspace = PiWorkspace(
            workspace_path="/proj",
            workspace_name="proj",
            sessions=[
                PiSessionInfo("uuid-1", f1, "/proj", "2026-06-01T10:00:00.000Z"),
                PiSessionInfo("uuid-2", f2, "/proj", "2026-06-02T10:00:00.000Z"),
                # Dangling path — should be excluded
                PiSessionInfo("uuid-3", tmp_path / "ghost.jsonl", "/proj", ""),
            ],
            session_count=3,
            pi_data_dir=tmp_path,
        )

        result = get_pi_session_files(workspace)
        assert len(result) == 2
        assert all(p.exists() for p in result)

    def test_sorted_newest_first(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        import time
        f1 = _make_session_file(sessions_dir, "/proj", "uuid-old",
                                "2026-06-01T10:00:00.000Z", "d-old")
        time.sleep(0.05)
        f2 = _make_session_file(sessions_dir, "/proj", "uuid-new",
                                "2026-06-28T10:00:00.000Z", "d-new")

        workspace = PiWorkspace(
            workspace_path="/proj",
            workspace_name="proj",
            sessions=[
                PiSessionInfo("uuid-old", f1, "/proj", "2026-06-01T10:00:00.000Z"),
                PiSessionInfo("uuid-new", f2, "/proj", "2026-06-28T10:00:00.000Z"),
            ],
            session_count=2,
            pi_data_dir=tmp_path,
        )

        result = get_pi_session_files(workspace)
        # Newer file should be first
        assert result[0] == f2

    def test_empty_workspace_returns_empty(self, tmp_path):
        workspace = PiWorkspace(
            workspace_path="/proj",
            workspace_name="proj",
            sessions=[],
            session_count=0,
            pi_data_dir=tmp_path,
        )
        assert get_pi_session_files(workspace) == []

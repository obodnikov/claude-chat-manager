"""OpenAI Codex CLI project discovery and session management.

This module provides functionality for discovering Codex CLI sessions,
grouping them by working directory (project), and listing sessions.

Codex stores sessions organized by date:
    ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl

Sessions are grouped into "projects" by their cwd (working directory)
from the session_meta header.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CodexSessionInfo:
    """Lightweight session info for project discovery.

    Attributes:
        session_id: UUID of the session
        file_path: Path to the rollout JSONL file
        cwd: Working directory where session was started
        timestamp: Session start timestamp
        model: Model used for the session
        git_branch: Git branch (optional)
    """
    session_id: str
    file_path: Path
    cwd: str
    timestamp: str
    model: str = ""
    git_branch: Optional[str] = None


@dataclass
class CodexWorkspace:
    """Represents a Codex project (sessions grouped by cwd).

    Attributes:
        workspace_path: Full cwd path (project directory)
        workspace_name: Human-readable name (basename of cwd)
        sessions: List of sessions in this project
        session_count: Number of sessions
        last_modified: Most recent session timestamp as formatted string
        codex_data_dir: Path to ~/.codex directory
    """
    workspace_path: str
    workspace_name: str
    sessions: List[CodexSessionInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    codex_data_dir: Optional[Path] = None


def _scan_rollout_files(sessions_dir: Path) -> List[Path]:
    """Recursively find all rollout JSONL files under sessions directory.

    Scans the date-organized directory structure:
    sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl

    Args:
        sessions_dir: Path to ~/.codex/sessions/

    Returns:
        List of paths to rollout files, sorted by modification time (newest first)
    """
    rollout_files = []

    if not sessions_dir.exists():
        return rollout_files

    for jsonl_file in sessions_dir.rglob('rollout-*.jsonl'):
        if jsonl_file.is_file():
            rollout_files.append(jsonl_file)

    rollout_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return rollout_files


def _parse_session_meta_lightweight(file_path: Path) -> Optional[CodexSessionInfo]:
    """Parse only the first line of a rollout file for project discovery.

    This is optimized for speed — reads only one line per file.

    Args:
        file_path: Path to rollout JSONL file

    Returns:
        CodexSessionInfo or None if parsing fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if not first_line:
                return None

            data = json.loads(first_line)

            if data.get('type') != 'session_meta':
                return None

            payload = data.get('payload', {})
            git_info = payload.get('git', {}) or {}

            return CodexSessionInfo(
                session_id=payload.get('id', file_path.stem),
                file_path=file_path,
                cwd=payload.get('cwd', ''),
                timestamp=payload.get('timestamp', ''),
                model=payload.get('model', ''),
                git_branch=git_info.get('branch')
            )
    except (json.JSONDecodeError, IOError, KeyError) as e:
        logger.warning(f"Failed to parse session meta from {file_path}: {e}")
        return None


def discover_codex_workspaces(codex_data_dir: Path) -> List[CodexWorkspace]:
    """Discover all Codex projects by scanning sessions and grouping by cwd.

    Scans all rollout files, reads their session_meta headers,
    and groups sessions by working directory.

    Args:
        codex_data_dir: Path to ~/.codex/ directory

    Returns:
        List of CodexWorkspace objects (one per unique cwd)
    """
    sessions_dir = codex_data_dir / 'sessions'

    if not sessions_dir.exists():
        logger.debug(f"Codex sessions directory not found: {sessions_dir}")
        return []

    # Scan all rollout files
    rollout_files = _scan_rollout_files(sessions_dir)
    logger.debug(f"Found {len(rollout_files)} Codex rollout files")

    # Parse session_meta from each file and group by cwd
    cwd_groups: Dict[str, List[CodexSessionInfo]] = {}

    for file_path in rollout_files:
        session_info = _parse_session_meta_lightweight(file_path)
        if session_info and session_info.cwd:
            if session_info.cwd not in cwd_groups:
                cwd_groups[session_info.cwd] = []
            cwd_groups[session_info.cwd].append(session_info)

    # Convert groups to CodexWorkspace objects
    workspaces = []

    for cwd, sessions in cwd_groups.items():
        workspace_name = Path(cwd).name or cwd

        # Calculate last modified from session timestamps
        last_modified = "Unknown"
        latest_timestamp = None

        for session in sessions:
            if session.timestamp:
                try:
                    ts = datetime.fromisoformat(
                        session.timestamp.replace('Z', '+00:00')
                    )
                    if latest_timestamp is None or ts > latest_timestamp:
                        latest_timestamp = ts
                except (ValueError, TypeError):
                    pass

        if latest_timestamp:
            last_modified = latest_timestamp.strftime('%Y-%m-%d %H:%M:%S')

        workspaces.append(CodexWorkspace(
            workspace_path=cwd,
            workspace_name=workspace_name,
            sessions=sessions,
            session_count=len(sessions),
            last_modified=last_modified,
            codex_data_dir=codex_data_dir
        ))

    # Sort workspaces by last_modified (newest first)
    workspaces.sort(key=lambda w: w.last_modified, reverse=True)

    logger.info(f"Discovered {len(workspaces)} Codex projects from {len(rollout_files)} sessions")
    return workspaces


def get_codex_session_files(workspace: CodexWorkspace) -> List[Path]:
    """Get all rollout file paths for a Codex workspace/project.

    Args:
        workspace: CodexWorkspace containing session info

    Returns:
        List of rollout file paths, sorted by modification time
    """
    paths = [s.file_path for s in workspace.sessions if s.file_path.exists()]
    paths.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return paths

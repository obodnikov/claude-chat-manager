"""Cline (VS Code extension) project discovery and task management.

This module provides functionality for discovering Cline VS Code tasks,
grouping them by working directory (project), and listing tasks.

The VS Code extension stores tasks in VS Code globalStorage:
    ~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/
    (or the OS-equivalent globalStorage path)

Discovery reads state/taskHistory.json (an array) and groups tasks by
cwdOnTaskInitialization (the workspace path), similar to Codex's cwd grouping.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ClineVscodeTaskInfo:
    """Lightweight task info for project discovery.

    Attributes:
        task_id: Epoch-ms string task identifier
        task_dir: Path to the task directory (tasks/<task-id>/)
        cwd: Working directory where task was initialized
        timestamp: Task start timestamp (epoch ms)
        title: Task title (from taskHistory.task or first user msg)
        model: Model used for the task
        total_cost: Total API cost for the task
    """
    task_id: str
    task_dir: Path
    cwd: str
    timestamp: str
    title: str = ""
    model: str = ""
    total_cost: float = 0.0


@dataclass
class ClineVscodeWorkspace:
    """Represents a Cline VS Code project (tasks grouped by cwd).

    Attributes:
        workspace_path: Full cwd path (project directory)
        workspace_name: Human-readable name (basename of cwd)
        tasks: List of tasks in this project
        session_count: Number of tasks
        last_modified: Most recent task timestamp as formatted string
        cline_data_dir: Path to Cline data directory
    """
    workspace_path: str
    workspace_name: str
    tasks: List[ClineVscodeTaskInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    cline_data_dir: Optional[Path] = None


def discover_cline_vscode_workspaces(cline_data_dir: Path) -> List[ClineVscodeWorkspace]:
    """Discover all Cline VS Code projects by reading taskHistory.json.

    Reads state/taskHistory.json (an array of task summaries), then groups
    tasks by cwdOnTaskInitialization. Skips tasks whose directory or
    conversation files are absent.

    Args:
        cline_data_dir: Path to Cline data directory (globalStorage/saoudrizwan.claude-dev/)

    Returns:
        List of ClineVscodeWorkspace objects (one per unique cwd)
    """
    task_history_path = cline_data_dir / "state" / "taskHistory.json"

    if not task_history_path.exists():
        logger.debug(f"taskHistory.json not found: {task_history_path}")
        return []

    try:
        with open(task_history_path, 'r', encoding='utf-8') as f:
            task_history = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to read taskHistory.json: {e}")
        return []

    if not isinstance(task_history, list):
        logger.warning(f"taskHistory.json is not an array: {task_history_path}")
        return []

    # Group tasks by cwd
    cwd_groups: Dict[str, List[ClineVscodeTaskInfo]] = {}

    for entry in task_history:
        if not isinstance(entry, dict):
            continue

        task_id = entry.get('id', '')
        cwd = entry.get('cwdOnTaskInitialization', '')

        # Normalize and validate field types (external JSON — can't trust types)
        if not isinstance(task_id, str):
            if task_id is not None and task_id != '':
                task_id = str(task_id)
            else:
                continue
        if not isinstance(cwd, str):
            if cwd is not None and cwd != '':
                cwd = str(cwd)
            else:
                continue

        # Skip if no cwd or task_id
        if not task_id or not cwd:
            continue

        # Check if task directory exists
        try:
            task_dir = cline_data_dir / "tasks" / task_id
        except TypeError:
            logger.debug(f"Invalid task_id type for path: {task_id!r}")
            continue

        if not task_dir.exists():
            logger.debug(f"Task directory not found: {task_dir}")
            continue

        # Check if at least one conversation file exists
        ui_path = task_dir / "ui_messages.json"
        api_path = task_dir / "api_conversation_history.json"
        if not ui_path.exists() and not api_path.exists():
            logger.debug(f"No conversation files for task {task_id}")
            continue

        # Parse total_cost defensively
        raw_cost = entry.get('totalCost', 0.0)
        try:
            total_cost = float(raw_cost) if raw_cost is not None else 0.0
        except (ValueError, TypeError):
            total_cost = 0.0

        # Create task info
        task_info = ClineVscodeTaskInfo(
            task_id=task_id,
            task_dir=task_dir,
            cwd=cwd,
            timestamp=entry.get('ts', ''),
            title=entry.get('task', '') or '',
            model=entry.get('modelId', '') or '',
            total_cost=total_cost
        )

        # Group by cwd
        if cwd not in cwd_groups:
            cwd_groups[cwd] = []
        cwd_groups[cwd].append(task_info)

    # Convert groups to ClineVscodeWorkspace objects
    workspaces = []

    for cwd, tasks in cwd_groups.items():
        workspace_name = Path(cwd).name or cwd

        # Calculate last modified from task timestamps
        last_modified = "Unknown"
        latest_timestamp_ms: int = 0

        for task in tasks:
            if task.timestamp:
                try:
                    ts_ms = int(task.timestamp)
                    if ts_ms > latest_timestamp_ms:
                        latest_timestamp_ms = ts_ms
                except (ValueError, TypeError):
                    pass

        if latest_timestamp_ms > 0:
            try:
                last_modified = datetime.fromtimestamp(
                    latest_timestamp_ms / 1000.0
                ).strftime('%Y-%m-%d %H:%M:%S')
            except (OverflowError, OSError, ValueError):
                last_modified = "Unknown"

        workspaces.append(ClineVscodeWorkspace(
            workspace_path=cwd,
            workspace_name=workspace_name,
            tasks=tasks,
            session_count=len(tasks),
            last_modified=last_modified,
            cline_data_dir=cline_data_dir
        ))

    # Sort workspaces by newest timestamp first (0 = oldest for unknowns)
    def _sort_key(ws: ClineVscodeWorkspace) -> int:
        """Return the max epoch-ms timestamp across tasks for sorting."""
        max_ts = 0
        for t in ws.tasks:
            try:
                ts = int(t.timestamp)
                if ts > max_ts:
                    max_ts = ts
            except (ValueError, TypeError):
                pass
        return max_ts

    workspaces.sort(key=_sort_key, reverse=True)

    logger.info(f"Discovered {len(workspaces)} Cline projects from {len(task_history)} tasks")
    return workspaces


def get_cline_vscode_session_files(workspace: ClineVscodeWorkspace) -> List[Path]:
    """Get task directory paths for a Cline VS Code workspace/project.

    Returns the task directory path for each task, sorted by timestamp
    (newest first). The parser (parse_cline_vscode_task) expects a task
    directory and handles primary/fallback file selection internally.

    Args:
        workspace: ClineVscodeWorkspace containing task info

    Returns:
        List of task directory paths that contain at least one conversation file,
        sorted newest-first by task timestamp.
    """
    # Sort tasks by timestamp (newest first)
    def _task_sort_key(task: ClineVscodeTaskInfo) -> int:
        try:
            return int(task.timestamp)
        except (ValueError, TypeError):
            return 0

    sorted_tasks = sorted(workspace.tasks, key=_task_sort_key, reverse=True)

    paths = []
    for task in sorted_tasks:
        ui_path = task.task_dir / "ui_messages.json"
        api_path = task.task_dir / "api_conversation_history.json"

        if ui_path.exists() or api_path.exists():
            paths.append(task.task_dir)

    return paths

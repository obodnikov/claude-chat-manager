"""Project management utilities.

This module handles discovery, listing, and searching of Claude projects.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from datetime import datetime
from typing import List, Optional
import logging
import os

from .config import config
from .exceptions import ProjectNotFoundError
from .models import ProjectInfo, ChatSource
from .formatters import clean_project_name
from .parser import count_messages_in_file

logger = logging.getLogger(__name__)


def _workspace_path_basename(workspace_path: str) -> str:
    """Return the final path component of a workspace path, cross-platform.

    Cline stores the raw OS path in cwdOnTaskInitialization. When the data
    was produced on Windows and is read on POSIX (or vice-versa), the native
    Path() class may not split the path correctly. We check both PurePosixPath
    and PureWindowsPath and return whichever gives a non-empty, different name
    from the full path, falling back to the native Path result.

    Args:
        workspace_path: Raw cwd string, e.g. '/home/user/repo' or
            'C:\\Users\\me\\repo'.

    Returns:
        The final path component, e.g. 'repo'.
    """
    native_name = Path(workspace_path).name
    if native_name and native_name != workspace_path:
        return native_name
    # Try POSIX
    posix_name = PurePosixPath(workspace_path).name
    if posix_name and posix_name != workspace_path:
        return posix_name
    # Try Windows
    win_name = PureWindowsPath(workspace_path).name
    if win_name and win_name != workspace_path:
        return win_name
    return native_name


def _cline_workspace_to_project_info(
    workspace: "ClineVscodeWorkspace",  # type: ignore[name-defined]  # noqa: F821
    cline_vscode_data_dir: Path,
) -> ProjectInfo:
    """Convert a ClineVscodeWorkspace to a ProjectInfo.

    Centralises field construction to avoid duplicated logic in
    list_all_projects() and find_project_by_name().

    Args:
        workspace: Discovered Cline VS Code workspace.
        cline_vscode_data_dir: Root Cline data directory; used to build
            the canonical tasks/ path stored in ProjectInfo.path.

    Returns:
        ProjectInfo with source=CLINE_VSCODE.
    """
    return ProjectInfo(
        name=workspace.workspace_name,
        path=cline_vscode_data_dir / 'tasks',
        file_count=workspace.session_count,
        total_messages=0,
        last_modified=workspace.last_modified,
        sort_timestamp=None,
        source=ChatSource.CLINE_VSCODE,
        workspace_path=workspace.workspace_path,
        # Store task IDs (not full paths) so get_project_chat_files()
        # can resolve them safely under the tasks directory.
        session_ids=[t.task_id for t in workspace.tasks],
    )


def get_project_info(project_dir: Path, source: ChatSource = ChatSource.CLAUDE_DESKTOP) -> ProjectInfo:
    """Get information about a Claude project.

    Args:
        project_dir: Path to the project directory.
        source: Source of the project (default: Claude Desktop).

    Returns:
        ProjectInfo object with project details.
    """
    project_name = clean_project_name(project_dir.name)
    jsonl_files = list(project_dir.glob('*.jsonl'))
    file_count = len(jsonl_files)
    last_modified = None
    total_messages = 0
    sort_timestamp = None

    if jsonl_files:
        # Get most recent modification time
        timestamps = []
        for file in jsonl_files:
            try:
                timestamps.append(file.stat().st_mtime)
                # Count messages in file
                total_messages += count_messages_in_file(file)
            except Exception as e:
                logger.warning(f"Error reading file {file}: {e}")

        if timestamps:
            sort_timestamp = max(timestamps)
            last_modified = datetime.fromtimestamp(sort_timestamp).strftime('%Y-%m-%d %H:%M')

    return ProjectInfo(
        name=project_name,
        path=project_dir,
        file_count=file_count,
        total_messages=total_messages,
        last_modified=last_modified or 'unknown',
        sort_timestamp=sort_timestamp,
        source=source
    )


def list_all_projects(source_filter: Optional[ChatSource] = None) -> List[ProjectInfo]:
    """List all available projects from specified sources.

    Args:
        source_filter: Filter by source (None = all sources, ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE).

    Returns:
        List of ProjectInfo objects.

    Raises:
        ProjectNotFoundError: If no valid source directories exist.
    """
    projects = []
    
    # Determine which sources to scan
    scan_claude = source_filter is None or source_filter == ChatSource.CLAUDE_DESKTOP
    scan_kiro = source_filter is None or source_filter == ChatSource.KIRO_IDE
    scan_codex = source_filter is None or source_filter == ChatSource.CODEX
    scan_cline_vscode = source_filter is None or source_filter == ChatSource.CLINE_VSCODE
    
    # Scan Claude Desktop projects
    if scan_claude:
        claude_dir = config.claude_projects_dir
        if claude_dir.exists():
            for project_dir in claude_dir.iterdir():
                if project_dir.is_dir():
                    info = get_project_info(project_dir, source=ChatSource.CLAUDE_DESKTOP)
                    if info.file_count > 0:  # Only include projects with JSONL files
                        projects.append(info)
            logger.info(f"Found {len([p for p in projects if p.source == ChatSource.CLAUDE_DESKTOP])} Claude Desktop projects")
        else:
            logger.warning(f"Claude projects directory not found: {claude_dir}")
    
    # Scan Kiro IDE projects
    if scan_kiro:
        if config.validate_kiro_directory():
            try:
                from .kiro_projects import discover_kiro_workspaces
                kiro_workspaces = discover_kiro_workspaces(config.kiro_data_dir)
                
                # Convert Kiro workspaces to ProjectInfo objects
                for workspace in kiro_workspaces:
                    # TODO: Calculate total_messages by parsing session files for accurate counts
                    # Currently set to 0 to avoid expensive I/O operations during listing
                    # For Kiro: path points to session_dir (where .chat files are stored)
                    # workspace_path stores the decoded human-readable workspace path
                    projects.append(ProjectInfo(
                        name=workspace.workspace_name,
                        path=workspace.session_dir,
                        file_count=workspace.session_count,
                        total_messages=0,  # Deferred: requires parsing all session files
                        last_modified=workspace.last_modified,
                        sort_timestamp=None,  # Could be parsed from last_modified if needed
                        source=ChatSource.KIRO_IDE,
                        workspace_path=workspace.workspace_path,
                        session_ids=[s.session_id for s in workspace.sessions]
                    ))
                logger.info(f"Found {len([p for p in projects if p.source == ChatSource.KIRO_IDE])} Kiro IDE workspaces")
            except Exception as e:
                logger.warning(f"Error discovering Kiro projects: {e}")
        else:
            logger.debug("Kiro data directory not found, skipping Kiro projects")
    
    # Scan Codex CLI projects
    if scan_codex:
        if config.validate_codex_directory():
            try:
                from .codex_projects import discover_codex_workspaces
                codex_workspaces = discover_codex_workspaces(config.codex_data_dir)

                for workspace in codex_workspaces:
                    projects.append(ProjectInfo(
                        name=workspace.workspace_name,
                        path=config.codex_data_dir / 'sessions',
                        file_count=workspace.session_count,
                        total_messages=0,
                        last_modified=workspace.last_modified,
                        sort_timestamp=None,
                        source=ChatSource.CODEX,
                        workspace_path=workspace.workspace_path,
                        session_ids=[str(s.file_path) for s in workspace.sessions]
                    ))
                logger.info(
                    f"Found {len([p for p in projects if p.source == ChatSource.CODEX])} "
                    f"Codex CLI projects"
                )
            except Exception as e:
                logger.warning(f"Error discovering Codex projects: {e}")
        else:
            logger.debug("Codex data directory not found, skipping Codex projects")

    # Scan Cline VS Code extension projects
    if scan_cline_vscode:
        if config.validate_cline_vscode_directory():
            try:
                from .cline_vscode_projects import discover_cline_vscode_workspaces
                cline_vscode_data_dir = config.cline_vscode_data_dir
                cline_workspaces = discover_cline_vscode_workspaces(cline_vscode_data_dir)

                for workspace in cline_workspaces:
                    projects.append(_cline_workspace_to_project_info(workspace, cline_vscode_data_dir))
                logger.info(
                    f"Found {len([p for p in projects if p.source == ChatSource.CLINE_VSCODE])} "
                    f"Cline VS Code projects"
                )
            except Exception as e:
                logger.warning(f"Error discovering Cline VS Code projects: {e}")
        else:
            logger.debug("Cline VS Code data directory not found, skipping Cline VS Code projects")

    if not projects:
        raise ProjectNotFoundError("No projects found in any configured source")
    
    logger.info(f"Found {len(projects)} total projects")
    return projects


def find_project_by_name(project_name: str, source_filter: Optional[ChatSource] = None) -> Optional[ProjectInfo]:
    """Find a project by name (supports both clean and original names).

    Args:
        project_name: The project name to search for.
        source_filter: Filter by source (None = all sources, ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE).

    Returns:
        ProjectInfo object if found, None otherwise.
    """
    # Determine which sources to search
    # None means search all sources (consistent with list_all_projects)
    search_claude = source_filter is None or source_filter == ChatSource.CLAUDE_DESKTOP
    search_kiro = source_filter is None or source_filter == ChatSource.KIRO_IDE
    search_codex = source_filter is None or source_filter == ChatSource.CODEX
    search_cline_vscode = source_filter is None or source_filter == ChatSource.CLINE_VSCODE
    
    # Search Claude Desktop projects
    if search_claude:
        claude_dir = config.claude_projects_dir
        if claude_dir.exists():
            for project_dir in claude_dir.iterdir():
                if project_dir.is_dir():
                    clean_name = clean_project_name(project_dir.name)
                    if (clean_name.lower() == project_name.lower() or
                            project_dir.name.lower() == project_name.lower()):
                        logger.debug(f"Found Claude project: {project_dir}")
                        # Return ProjectInfo with source information
                        file_count = len(list(project_dir.glob('*.jsonl')))
                        return ProjectInfo(
                            name=clean_name,
                            path=project_dir,
                            file_count=file_count,
                            total_messages=0,  # Not calculated for single project lookup
                            last_modified="",
                            source=ChatSource.CLAUDE_DESKTOP
                        )
    
    # Search Kiro IDE projects
    if search_kiro:
        if config.validate_kiro_directory():
            try:
                from .kiro_projects import discover_kiro_workspaces
                kiro_workspaces = discover_kiro_workspaces(config.kiro_data_dir)
                
                for workspace in kiro_workspaces:
                    # Match against workspace name
                    if workspace.workspace_name.lower() == project_name.lower():
                        logger.debug(f"Found Kiro workspace: {workspace.workspace_path}")
                        # Return ProjectInfo for Kiro workspace
                        # path points to session_dir where .chat files are stored
                        return ProjectInfo(
                            name=workspace.workspace_name,
                            path=workspace.session_dir,
                            file_count=workspace.session_count,
                            total_messages=0,  # Not calculated for single project lookup
                            last_modified=workspace.last_modified,
                            source=ChatSource.KIRO_IDE,
                            workspace_path=workspace.workspace_path,
                            session_ids=[s.session_id for s in workspace.sessions]
                        )
                    
                    # Also try matching against the base name of the path
                    workspace_basename = Path(workspace.workspace_path).name
                    if workspace_basename.lower() == project_name.lower():
                        logger.debug(f"Found Kiro workspace by path: {workspace.workspace_path}")
                        return ProjectInfo(
                            name=workspace.workspace_name,
                            path=workspace.session_dir,
                            file_count=workspace.session_count,
                            total_messages=0,
                            last_modified=workspace.last_modified,
                            source=ChatSource.KIRO_IDE,
                            workspace_path=workspace.workspace_path,
                            session_ids=[s.session_id for s in workspace.sessions]
                        )
            except Exception as e:
                logger.warning(f"Error searching Kiro projects: {e}")
    
    # Search Codex CLI projects
    if search_codex:
        if config.validate_codex_directory():
            try:
                from .codex_projects import discover_codex_workspaces
                codex_workspaces = discover_codex_workspaces(config.codex_data_dir)

                for workspace in codex_workspaces:
                    if workspace.workspace_name.lower() == project_name.lower():
                        logger.debug(f"Found Codex project: {workspace.workspace_path}")
                        return ProjectInfo(
                            name=workspace.workspace_name,
                            path=config.codex_data_dir / 'sessions',
                            file_count=workspace.session_count,
                            total_messages=0,
                            last_modified=workspace.last_modified,
                            source=ChatSource.CODEX,
                            workspace_path=workspace.workspace_path,
                            session_ids=[str(s.file_path) for s in workspace.sessions]
                        )

                    workspace_basename = Path(workspace.workspace_path).name
                    if workspace_basename.lower() == project_name.lower():
                        logger.debug(f"Found Codex project by path: {workspace.workspace_path}")
                        return ProjectInfo(
                            name=workspace.workspace_name,
                            path=config.codex_data_dir / 'sessions',
                            file_count=workspace.session_count,
                            total_messages=0,
                            last_modified=workspace.last_modified,
                            source=ChatSource.CODEX,
                            workspace_path=workspace.workspace_path,
                            session_ids=[str(s.file_path) for s in workspace.sessions]
                        )
            except Exception as e:
                logger.warning(f"Error searching Codex projects: {e}")

    # Search Cline VS Code extension projects
    if search_cline_vscode:
        if config.validate_cline_vscode_directory():
            try:
                from .cline_vscode_projects import discover_cline_vscode_workspaces
                cline_vscode_data_dir = config.cline_vscode_data_dir
                cline_workspaces = discover_cline_vscode_workspaces(cline_vscode_data_dir)

                for workspace in cline_workspaces:
                    if workspace.workspace_name.lower() == project_name.lower():
                        logger.debug(f"Found Cline VS Code project: {workspace.workspace_path}")
                        return _cline_workspace_to_project_info(workspace, cline_vscode_data_dir)

                    workspace_basename = _workspace_path_basename(workspace.workspace_path)
                    if workspace_basename.lower() == project_name.lower():
                        logger.debug(f"Found Cline VS Code project by path: {workspace.workspace_path}")
                        return _cline_workspace_to_project_info(workspace, cline_vscode_data_dir)
            except Exception as e:
                logger.warning(f"Error searching Cline VS Code projects: {e}")

    logger.warning(f"Project not found: {project_name}")
    return None


def search_projects_by_name(search_term: str, source_filter: Optional[ChatSource] = None) -> List[ProjectInfo]:
    """Search for projects containing the search term in their name.

    Args:
        search_term: The term to search for in project names.
        source_filter: Filter by source (None = all sources).

    Returns:
        List of matching ProjectInfo objects.
    """
    try:
        all_projects = list_all_projects(source_filter)
        found_projects = [
            p for p in all_projects
            if search_term.lower() in p.name.lower()
        ]
        logger.info(f"Found {len(found_projects)} projects matching '{search_term}'")
        return found_projects
    except ProjectNotFoundError:
        logger.warning("Cannot search projects: No valid source directories found")
        return []


def get_recent_projects(count: int = 10, source_filter: Optional[ChatSource] = None) -> List[ProjectInfo]:
    """Get most recently modified projects.

    Args:
        count: Maximum number of projects to return.
        source_filter: Filter by source (None = all sources).

    Returns:
        List of ProjectInfo objects sorted by modification time (most recent first).
    """
    try:
        all_projects = list_all_projects(source_filter)

        # Filter projects with valid timestamps
        projects_with_time = [p for p in all_projects if p.sort_timestamp is not None]

        # Sort by timestamp and return top N
        projects_with_time.sort(key=lambda x: x.sort_timestamp, reverse=True)

        logger.info(f"Retrieved {min(count, len(projects_with_time))} recent projects")
        return projects_with_time[:count]
    except ProjectNotFoundError:
        logger.error("Cannot get recent projects: No valid source directories found")
        return []


def get_project_chat_files(
    project_path: Path,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP,
    session_ids: Optional[List[str]] = None
) -> List[Path]:
    """Get all chat files in a project based on source type.

    Args:
        project_path: Path to the project directory.
        source: Chat source type (Claude Desktop, Kiro IDE, or Codex CLI).
        session_ids: For Codex: list of absolute file path strings.

    Returns:
        Sorted list of chat file paths.
    """
    if source == ChatSource.CODEX:
        # Codex sessions are stored as absolute paths in session_ids
        if session_ids:
            chat_files = [Path(p) for p in session_ids if Path(p).exists()]
            chat_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return chat_files
        return []

    if source == ChatSource.CLINE_VSCODE:
        # Cline VS Code: session_ids are task IDs (not full paths).
        # Resolve each under project_path (the tasks/ directory) and verify
        # the resolved path is still inside project_path to prevent traversal.
        if session_ids:
            tasks_root = project_path.resolve()
            task_dirs: List[Path] = []
            for task_id in session_ids:
                # Reject IDs that look like paths (contain separators) or
                # traversal components before even resolving.
                if '/' in task_id or '\\' in task_id or '..' in task_id.split(os.sep):
                    logger.warning(
                        f"Rejected Cline task_id with path separator or traversal: {task_id!r}"
                    )
                    continue
                candidate = (project_path / task_id).resolve()
                # Confinement check: must be inside the tasks directory
                try:
                    candidate.relative_to(tasks_root)
                except ValueError:
                    logger.warning(
                        f"Rejected Cline task path outside tasks root: {candidate}"
                    )
                    continue
                if candidate.exists() and candidate.is_dir():
                    task_dirs.append(candidate)
            task_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            return task_dirs
        return []

    if not project_path.exists() or not project_path.is_dir():
        logger.error(f"Invalid project path: {project_path}")
        return []

    if source == ChatSource.KIRO_IDE:
        # For Kiro, look for .json files (Kiro session files)
        chat_files = list(project_path.glob('*.json'))
        # Filter out sessions.json which is metadata, not a chat file
        chat_files = [f for f in chat_files if f.name != 'sessions.json']
    else:
        # For Claude Desktop, look for JSONL files
        chat_files = list(project_path.glob('*.jsonl'))
    
    chat_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    logger.debug(f"Found {len(chat_files)} chat files in {project_path.name} (source: {source.value})")
    return chat_files

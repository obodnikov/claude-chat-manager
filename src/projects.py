"""Project management utilities.

This module handles discovery, listing, and searching of Claude projects.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional
import logging

from .config import config
from .exceptions import ProjectNotFoundError
from .models import ProjectInfo
from .formatters import clean_project_name
from .parser import count_messages_in_file

logger = logging.getLogger(__name__)


def get_project_info(project_dir: Path) -> ProjectInfo:
    """Get information about a Claude project.

    Args:
        project_dir: Path to the project directory.

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
        sort_timestamp=sort_timestamp
    )


def list_all_projects() -> List[ProjectInfo]:
    """List all available Claude projects.

    Returns:
        List of ProjectInfo objects.

    Raises:
        ProjectNotFoundError: If Claude projects directory doesn't exist.
    """
    claude_dir = config.claude_projects_dir

    if not claude_dir.exists():
        raise ProjectNotFoundError(f"Claude projects directory not found: {claude_dir}")

    projects = []
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            info = get_project_info(project_dir)
            if info.file_count > 0:  # Only include projects with JSONL files
                projects.append(info)

    logger.info(f"Found {len(projects)} projects with chat files")
    return projects


def find_project_by_name(project_name: str) -> Optional[Path]:
    """Find a project by name (supports both clean and original names).

    Args:
        project_name: The project name to search for.

    Returns:
        Path to the project directory if found, None otherwise.
    """
    claude_dir = config.claude_projects_dir

    if not claude_dir.exists():
        return None

    # Search through all project directories
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            clean_name = clean_project_name(project_dir.name)
            if (clean_name.lower() == project_name.lower() or
                    project_dir.name.lower() == project_name.lower()):
                logger.debug(f"Found project: {project_dir}")
                return project_dir

    logger.warning(f"Project not found: {project_name}")
    return None


def search_projects_by_name(search_term: str) -> List[ProjectInfo]:
    """Search for projects containing the search term in their name.

    Args:
        search_term: The term to search for in project names.

    Returns:
        List of matching ProjectInfo objects.
    """
    claude_dir = config.claude_projects_dir

    if not claude_dir.exists():
        logger.warning(f"Claude projects directory not found: {claude_dir}")
        return []

    found_projects = []
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            clean_name = clean_project_name(project_dir.name)
            if (search_term.lower() in clean_name.lower() or
                    search_term.lower() in project_dir.name.lower()):
                info = get_project_info(project_dir)
                found_projects.append(info)
                logger.debug(f"Found matching project: {clean_name}")

    logger.info(f"Found {len(found_projects)} projects matching '{search_term}'")
    return found_projects


def get_recent_projects(count: int = 10) -> List[ProjectInfo]:
    """Get most recently modified projects.

    Args:
        count: Maximum number of projects to return.

    Returns:
        List of ProjectInfo objects sorted by modification time (most recent first).
    """
    try:
        all_projects = list_all_projects()

        # Filter projects with valid timestamps
        projects_with_time = [p for p in all_projects if p.sort_timestamp is not None]

        # Sort by timestamp and return top N
        projects_with_time.sort(key=lambda x: x.sort_timestamp, reverse=True)

        logger.info(f"Retrieved {min(count, len(projects_with_time))} recent projects")
        return projects_with_time[:count]
    except ProjectNotFoundError:
        logger.error("Cannot get recent projects: Claude directory not found")
        return []


def get_project_chat_files(project_path: Path) -> List[Path]:
    """Get all JSONL chat files in a project.

    Args:
        project_path: Path to the project directory.

    Returns:
        Sorted list of JSONL file paths.
    """
    if not project_path.exists() or not project_path.is_dir():
        logger.error(f"Invalid project path: {project_path}")
        return []

    chat_files = list(project_path.glob('*.jsonl'))
    chat_files.sort()

    logger.debug(f"Found {len(chat_files)} chat files in {project_path.name}")
    return chat_files

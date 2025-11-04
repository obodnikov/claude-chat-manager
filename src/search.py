"""Search functionality for chat content.

This module provides content search across all chat files.
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple
import logging

from .config import config
from .formatters import clean_project_name

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a search result.

    Attributes:
        project_name: Name of the project containing the result.
        chat_name: Name of the chat file.
        line_number: Line number in the file.
        role: Message role (user/assistant/system).
        preview: Preview of the matching content.
    """

    project_name: str
    chat_name: str
    line_number: int
    role: str
    preview: str


def search_chat_content(search_term: str) -> List[SearchResult]:
    """Search for content within all chat files.

    Args:
        search_term: The term to search for in chat content.

    Returns:
        List of SearchResult objects.
    """
    claude_dir = config.claude_projects_dir

    if not claude_dir.exists():
        logger.warning(f"Claude projects directory not found: {claude_dir}")
        return []

    results = []

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue

        project_name = clean_project_name(project_dir.name)

        for jsonl_file in project_dir.glob('*.jsonl'):
            chat_name = jsonl_file.stem

            try:
                with open(jsonl_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        if search_term.lower() not in line.lower():
                            continue

                        # Try to extract meaningful context
                        try:
                            data = json.loads(line)
                            message = data.get('message', {})
                            content = message.get('content', '')
                            role = message.get('role', 'unknown')

                            preview = _extract_preview(content, search_term)
                            if preview:
                                result = SearchResult(
                                    project_name=project_name,
                                    chat_name=chat_name,
                                    line_number=line_num,
                                    role=role,
                                    preview=preview
                                )
                                results.append(result)
                                break  # Only first match per file

                        except Exception as e:
                            logger.debug(f"Error parsing line {line_num} in {jsonl_file}: {e}")
                            # Fallback to simple line preview
                            preview = line[:100] + '...' if len(line) > 100 else line
                            result = SearchResult(
                                project_name=project_name,
                                chat_name=chat_name,
                                line_number=line_num,
                                role='unknown',
                                preview=preview
                            )
                            results.append(result)
                            break

            except Exception as e:
                logger.error(f"Error searching file {jsonl_file}: {e}")
                continue

    logger.info(f"Found {len(results)} results for '{search_term}'")
    return results


def _extract_preview(content: any, search_term: str, max_length: int = 100) -> str:
    """Extract a preview of content containing the search term.

    Args:
        content: Message content (string or list).
        search_term: The search term to find.
        max_length: Maximum length of preview.

    Returns:
        Preview string or empty string if not found.
    """
    if isinstance(content, str) and search_term.lower() in content.lower():
        preview = content[:max_length] + '...' if len(content) > max_length else content
        return preview

    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text = item.get('text', '')
                if search_term.lower() in text.lower():
                    preview = text[:max_length] + '...' if len(text) > max_length else text
                    return preview

    return ''


# Import dataclass here to avoid circular import
from dataclasses import dataclass

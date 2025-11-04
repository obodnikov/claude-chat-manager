"""Configuration management for Claude Chat Manager.

This module handles loading and accessing configuration values from
environment variables and config files.
"""

import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Configuration management class."""

    def __init__(self) -> None:
        """Initialize configuration with default values."""
        self._claude_dir: Optional[Path] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from environment variables and defaults."""
        # Claude projects directory
        claude_dir_env = os.getenv('CLAUDE_PROJECTS_DIR')
        if claude_dir_env:
            self._claude_dir = Path(claude_dir_env)
            logger.info(f"Using CLAUDE_PROJECTS_DIR from environment: {self._claude_dir}")
        else:
            # Default location
            home = Path.home()
            self._claude_dir = home / '.claude' / 'projects'
            logger.debug(f"Using default Claude directory: {self._claude_dir}")

    @property
    def claude_projects_dir(self) -> Path:
        """Get the Claude projects directory path.

        Returns:
            Path to Claude projects directory.
        """
        return self._claude_dir

    @property
    def default_export_format(self) -> str:
        """Get the default export format.

        Returns:
            Default export format name.
        """
        return os.getenv('CLAUDE_DEFAULT_FORMAT', 'pretty')

    @property
    def terminal_page_height(self) -> int:
        """Get the terminal page height for paging.

        Returns:
            Number of lines per page.
        """
        height = os.getenv('CLAUDE_PAGE_HEIGHT', '24')
        try:
            return int(height)
        except ValueError:
            logger.warning(f"Invalid CLAUDE_PAGE_HEIGHT: {height}, using default 24")
            return 24

    @property
    def log_level(self) -> str:
        """Get the logging level.

        Returns:
            Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        return os.getenv('CLAUDE_LOG_LEVEL', 'INFO').upper()


# Global configuration instance
config = Config()

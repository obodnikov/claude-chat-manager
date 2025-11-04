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

    @property
    def openrouter_api_key(self) -> Optional[str]:
        """Get the OpenRouter API key.

        Returns:
            API key or None if not set.
        """
        return os.getenv('OPENROUTER_API_KEY')

    @property
    def openrouter_model(self) -> str:
        """Get the OpenRouter model to use.

        Returns:
            Model identifier.
        """
        return os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3-haiku')

    @property
    def openrouter_base_url(self) -> str:
        """Get the OpenRouter API base URL.

        Returns:
            Base URL for API.
        """
        return os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')

    @property
    def openrouter_timeout(self) -> int:
        """Get the OpenRouter API timeout.

        Returns:
            Timeout in seconds.
        """
        timeout = os.getenv('OPENROUTER_TIMEOUT', '30')
        try:
            return int(timeout)
        except ValueError:
            logger.warning(f"Invalid OPENROUTER_TIMEOUT: {timeout}, using default 30")
            return 30

    @property
    def wiki_title_max_tokens(self) -> int:
        """Get the maximum tokens for wiki title generation.

        Returns:
            Maximum tokens to analyze for title generation.
        """
        max_tokens = os.getenv('WIKI_TITLE_MAX_TOKENS', '2000')
        try:
            return int(max_tokens)
        except ValueError:
            logger.warning(f"Invalid WIKI_TITLE_MAX_TOKENS: {max_tokens}, using default 2000")
            return 2000

    @property
    def wiki_generate_titles(self) -> bool:
        """Check if wiki title generation is enabled.

        Returns:
            True if title generation should use LLM.
        """
        value = os.getenv('WIKI_GENERATE_TITLES', 'true').lower()
        return value in ('true', '1', 'yes', 'on')


# Global configuration instance
config = Config()

"""Configuration management for Claude Chat Manager.

This module handles loading and accessing configuration values from
environment variables and config files.
"""

import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _load_env_file() -> None:
    """Load environment variables from .env file in script directory.

    This function looks for .env file in the project root directory
    (where the script is located) and loads variables into os.environ.
    Variables already set in the environment take precedence.
    """
    # Get project root directory (parent of src/)
    project_root = Path(__file__).parent.parent
    env_file = project_root / '.env'

    if not env_file.exists():
        logger.debug(f"No .env file found at {env_file}")
        return

    logger.debug(f"Loading .env from {env_file}")

    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse KEY=VALUE
                if '=' not in line:
                    logger.warning(f"Invalid .env line {line_num}: {line}")
                    continue

                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]

                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value
                    logger.debug(f"Loaded env var: {key}")

    except Exception as e:
        logger.warning(f"Error loading .env file: {e}")


# Load .env file before creating config instance
_load_env_file()


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
        return os.getenv('OPENROUTER_MODEL', 'anthropic/claude-haiku-4.5')

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

    @property
    def wiki_min_messages(self) -> int:
        """Get the minimum message count for a chat to be included in wiki.

        Returns:
            Minimum number of messages.
        """
        min_messages = os.getenv('WIKI_MIN_MESSAGES', '3')
        try:
            return int(min_messages)
        except ValueError:
            logger.warning(f"Invalid WIKI_MIN_MESSAGES: {min_messages}, using default 3")
            return 3

    @property
    def wiki_min_words(self) -> int:
        """Get the minimum word count for a chat to be included in wiki.

        Returns:
            Minimum total word count.
        """
        min_words = os.getenv('WIKI_MIN_WORDS', '75')
        try:
            return int(min_words)
        except ValueError:
            logger.warning(f"Invalid WIKI_MIN_WORDS: {min_words}, using default 75")
            return 75

    @property
    def wiki_skip_trivial(self) -> bool:
        """Check if trivial chats should be filtered out.

        Returns:
            True if trivial chats should be skipped.
        """
        value = os.getenv('WIKI_SKIP_TRIVIAL', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def wiki_skip_keywords(self) -> list:
        """Get the list of keywords that indicate trivial chats.

        Returns:
            List of keywords to skip.
        """
        keywords = os.getenv('WIKI_SKIP_KEYWORDS', 'warmup,test,hello,hi,ready')
        return [k.strip().lower() for k in keywords.split(',') if k.strip()]

    @property
    def wiki_require_content(self) -> bool:
        """Check if wiki entries must have code blocks or file references.

        Returns:
            True if content (code/files) is required.
        """
        value = os.getenv('WIKI_REQUIRE_CONTENT', 'false').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def wiki_filter_system_tags(self) -> bool:
        """Check if system tags should be filtered from user messages.

        Returns:
            True if system tags should be filtered.
        """
        value = os.getenv('WIKI_FILTER_SYSTEM_TAGS', 'true').lower()
        return value in ('true', '1', 'yes', 'on')


# Global configuration instance
config = Config()

"""Configuration management for Claude Chat Manager.

This module handles loading and accessing configuration values from
environment variables and config files.
"""

import os
import sys
from pathlib import Path
from typing import Optional
import logging
from src.models import ChatSource

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
        self._kiro_dir: Optional[Path] = None
        self._codex_dir: Optional[Path] = None
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

        # Kiro data directory
        kiro_dir_env = os.getenv('KIRO_DATA_DIR')
        if kiro_dir_env:
            self._kiro_dir = Path(kiro_dir_env)
            logger.info(f"Using KIRO_DATA_DIR from environment: {self._kiro_dir}")
        else:
            # Default location based on OS
            self._kiro_dir = self._get_default_kiro_dir()
            logger.debug(f"Using default Kiro directory: {self._kiro_dir}")

        # Codex data directory
        codex_dir_env = os.getenv('CODEX_DATA_DIR')
        if codex_dir_env:
            self._codex_dir = Path(codex_dir_env)
            logger.info(f"Using CODEX_DATA_DIR from environment: {self._codex_dir}")
        else:
            codex_home = os.getenv('CODEX_HOME')
            if codex_home:
                self._codex_dir = Path(codex_home)
            else:
                self._codex_dir = Path.home() / '.codex'
            logger.debug(f"Using default Codex directory: {self._codex_dir}")

    def _get_default_kiro_dir(self) -> Path:
        """Get OS-specific default Kiro data directory.
        
        Returns:
            Path to default Kiro data directory based on operating system.
            
        Raises:
            ValueError: If APPDATA environment variable is not set on Windows.
        """
        if sys.platform == 'win32':
            # Windows: %APPDATA%\Kiro\User\globalStorage\kiro.kiroagent\
            appdata = os.environ.get('APPDATA')
            if not appdata:
                raise ValueError('APPDATA environment variable not set on Windows')
            base = Path(appdata)
            return base / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        elif sys.platform == 'darwin':
            # macOS: ~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/
            return Path.home() / 'Library' / 'Application Support' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        else:
            # Linux: ~/.config/Kiro/User/globalStorage/kiro.kiroagent/
            return Path.home() / '.config' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'

    def validate_kiro_directory(self) -> bool:
        """Validate that the Kiro data directory exists.
        
        Returns:
            True if directory exists, False otherwise.
            Logs a warning if directory is not found.
        """
        if not self._kiro_dir.exists():
            logger.warning(f"Kiro data directory not found: {self._kiro_dir}")
            return False
        if not self._kiro_dir.is_dir():
            logger.warning(f"Kiro data path exists but is not a directory: {self._kiro_dir}")
            return False
        return True

    @property
    def claude_projects_dir(self) -> Path:
        """Get the Claude projects directory path.

        Returns:
            Path to Claude projects directory.
        """
        return self._claude_dir

    @property
    def kiro_data_dir(self) -> Path:
        """Get the Kiro data directory path.

        Returns:
            Path to Kiro data directory.
        """
        return self._kiro_dir

    @property
    def codex_data_dir(self) -> Path:
        """Get the Codex data directory path.

        Returns:
            Path to Codex data directory (~/.codex by default).
        """
        return self._codex_dir

    def validate_codex_directory(self) -> bool:
        """Validate that the Codex data directory exists.

        Returns:
            True if directory exists and contains a sessions subdirectory.
        """
        if not self._codex_dir.exists():
            logger.warning(f"Codex data directory not found: {self._codex_dir}")
            return False
        if not self._codex_dir.is_dir():
            logger.warning(f"Codex data path is not a directory: {self._codex_dir}")
            return False
        sessions_dir = self._codex_dir / 'sessions'
        if not sessions_dir.exists():
            logger.warning(f"Codex sessions directory not found: {sessions_dir}")
            return False
        return True

    @property
    def chat_source_filter(self) -> Optional[ChatSource]:
        """Get configured chat source filter.
        
        Returns:
            ChatSource enum value or None for all sources.
            - ChatSource.CLAUDE_DESKTOP: Show only Claude Desktop chats
            - ChatSource.KIRO_IDE: Show only Kiro IDE chats
            - ChatSource.CODEX: Show only Codex CLI chats
            - None: Show all sources
        """
        source = os.getenv('CHAT_SOURCE', 'claude').lower()
        if source == 'claude':
            return ChatSource.CLAUDE_DESKTOP
        elif source == 'kiro':
            return ChatSource.KIRO_IDE
        elif source == 'codex':
            return ChatSource.CODEX
        elif source == 'all':
            return None  # None means show all sources
        else:
            logger.warning(f"Invalid CHAT_SOURCE: {source}, defaulting to 'claude'")
            return ChatSource.CLAUDE_DESKTOP

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

    # Book Export Settings

    @property
    def book_skip_trivial(self) -> bool:
        """Check if trivial chats should be filtered out in book exports.

        Returns:
            True if trivial chats should be skipped.
        """
        value = os.getenv('BOOK_SKIP_TRIVIAL', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_min_messages(self) -> int:
        """Get the minimum message count for a chat to be included in book.

        Returns:
            Minimum number of messages.
        """
        min_messages = os.getenv('BOOK_MIN_MESSAGES', '3')
        try:
            return int(min_messages)
        except ValueError:
            logger.warning(f"Invalid BOOK_MIN_MESSAGES: {min_messages}, using default 3")
            return 3

    @property
    def book_min_words(self) -> int:
        """Get the minimum word count for a chat to be included in book.

        Returns:
            Minimum total word count.
        """
        min_words = os.getenv('BOOK_MIN_WORDS', '75')
        try:
            return int(min_words)
        except ValueError:
            logger.warning(f"Invalid BOOK_MIN_WORDS: {min_words}, using default 75")
            return 75

    @property
    def book_skip_keywords(self) -> list:
        """Get the list of keywords that indicate trivial chats.

        Returns:
            List of keywords to skip.
        """
        keywords = os.getenv('BOOK_SKIP_KEYWORDS', 'warmup,test,hello,hi,ready')
        return [k.strip().lower() for k in keywords.split(',') if k.strip()]

    @property
    def book_generate_titles(self) -> bool:
        """Check if book exports should generate descriptive filenames.

        Returns:
            True if descriptive filenames should be generated.
        """
        value = os.getenv('BOOK_GENERATE_TITLES', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_use_llm_titles(self) -> bool:
        """Check if book exports should use LLM for title generation.

        Returns:
            True if LLM should be used for titles.
        """
        value = os.getenv('BOOK_USE_LLM_TITLES', 'false').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_filter_system_tags(self) -> bool:
        """Check if system tags should be filtered from user messages in book.

        Returns:
            True if system tags should be filtered.
        """
        value = os.getenv('BOOK_FILTER_SYSTEM_TAGS', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_filter_tool_noise(self) -> bool:
        """Check if tool use/result messages should be filtered in book.

        Returns:
            True if tool noise should be filtered.
        """
        value = os.getenv('BOOK_FILTER_TOOL_NOISE', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_show_file_refs(self) -> bool:
        """Check if file references should be shown in book exports.

        Returns:
            True if file references should be displayed.
        """
        value = os.getenv('BOOK_SHOW_FILE_REFS', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def book_include_date(self) -> bool:
        """Check if date should be included in book export filenames.

        Returns:
            True if date should be appended to filenames.
        """
        value = os.getenv('BOOK_INCLUDE_DATE', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    # Sanitization Settings

    @property
    def sanitize_enabled(self) -> bool:
        """Check if sanitization is enabled.

        Returns:
            True if sanitization should be applied to exports.
        """
        value = os.getenv('SANITIZE_ENABLED', 'false').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def sanitize_level(self) -> str:
        """Get the sanitization detection level.

        Returns:
            Sanitization level ('minimal', 'balanced', 'aggressive', 'custom').
        """
        level = os.getenv('SANITIZE_LEVEL', 'balanced').lower()
        valid_levels = ['minimal', 'balanced', 'aggressive', 'custom']
        if level not in valid_levels:
            logger.warning(f"Invalid SANITIZE_LEVEL: {level}, using default 'balanced'")
            return 'balanced'
        return level

    @property
    def sanitize_style(self) -> str:
        """Get the redaction style for sanitization.

        Returns:
            Redaction style ('simple', 'stars', 'labeled', 'partial', 'hash').
        """
        style = os.getenv('SANITIZE_STYLE', 'partial').lower()
        valid_styles = ['simple', 'stars', 'labeled', 'partial', 'hash']
        if style not in valid_styles:
            logger.warning(f"Invalid SANITIZE_STYLE: {style}, using default 'partial'")
            return 'partial'
        return style

    @property
    def sanitize_paths(self) -> bool:
        """Check if file paths should be sanitized.

        Returns:
            True if file paths should be redacted.
        """
        value = os.getenv('SANITIZE_PATHS', 'false').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def sanitize_custom_patterns(self) -> list:
        """Get custom regex patterns for sanitization.

        Returns:
            List of custom regex pattern strings.
        """
        patterns = os.getenv('SANITIZE_CUSTOM_PATTERNS', '')
        return [p.strip() for p in patterns.split(',') if p.strip()]

    @property
    def sanitize_allowlist(self) -> list:
        """Get allowlist patterns that should never be sanitized.

        Returns:
            List of regex patterns to exclude from sanitization.
        """
        allowlist = os.getenv(
            'SANITIZE_ALLOWLIST',
            'example\\.com,localhost,127\\.0\\.0\\.1'
        )
        return [p.strip() for p in allowlist.split(',') if p.strip()]

    @property
    def sanitize_report(self) -> bool:
        """Check if sanitization report should be generated.

        Returns:
            True if a sanitization report should be created.
        """
        value = os.getenv('SANITIZE_REPORT', 'false').lower()
        return value in ('true', '1', 'yes', 'on')


# Global configuration instance
config = Config()

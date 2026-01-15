"""Custom exceptions for Claude Chat Manager.

This module defines custom exception classes for better error handling
throughout the application.
"""


class ClaudeReaderError(Exception):
    """Base exception class for Claude Chat Manager."""

    def __init__(self, message: str) -> None:
        """Initialize the exception.

        Args:
            message: The error message.
        """
        self.message = message
        super().__init__(self.message)


class ProjectNotFoundError(ClaudeReaderError):
    """Raised when a Claude project cannot be found."""

    pass


class ChatFileNotFoundError(ClaudeReaderError):
    """Raised when a chat JSONL file cannot be found."""

    pass


class InvalidJSONLError(ClaudeReaderError):
    """Raised when JSONL data is malformed or invalid."""

    pass


class ConfigurationError(ClaudeReaderError):
    """Raised when there's a configuration error."""

    pass


class ExportError(ClaudeReaderError):
    """Raised when export operation fails."""

    pass



class InvalidChatFileError(ClaudeReaderError):
    """Raised when a chat file (JSONL or JSON) is malformed or invalid."""

    pass

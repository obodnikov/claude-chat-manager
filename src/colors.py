"""Terminal color codes and utilities for colored output.

This module provides ANSI color codes and utility functions for
colorized terminal output.
"""

from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""

    RED: str = '\033[0;31m'
    GREEN: str = '\033[0;32m'
    YELLOW: str = '\033[1;33m'
    BLUE: str = '\033[0;34m'
    CYAN: str = '\033[0;36m'
    PURPLE: str = '\033[0;35m'
    NC: str = '\033[0m'  # No Color


def colorize(message: str, color: str) -> str:
    """Apply color to a message string.

    Args:
        message: The message to colorize.
        color: The color code to apply.

    Returns:
        Colorized message string.

    Example:
        >>> colorize("Hello", Colors.GREEN)
        '\033[0;32mHello\033[0m'
    """
    return f"{color}{message}{Colors.NC}"


def print_colored(message: str, color: str) -> None:
    """Print a colored message to terminal.

    Args:
        message: The message to print.
        color: The color code to apply.
    """
    print(colorize(message, color))


def get_role_color(role: str) -> tuple[str, str]:
    """Get color and icon for a message role.

    Args:
        role: The message role (user, assistant, system).

    Returns:
        Tuple of (color code, icon string).

    Example:
        >>> color, icon = get_role_color('user')
        >>> print(f"{color}{icon} User message{Colors.NC}")
    """
    role_mapping = {
        'user': (Colors.GREEN, '👤'),
        'assistant': (Colors.BLUE, '🤖'),
        'system': (Colors.PURPLE, '⚙️'),
    }
    return role_mapping.get(role.lower(), (Colors.YELLOW, '❓'))

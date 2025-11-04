"""Terminal display utilities including pager functionality.

This module handles terminal output and paging for long content.
"""

import sys
import shutil
from typing import Optional
import logging

from .colors import Colors, print_colored

logger = logging.getLogger(__name__)


def get_terminal_size() -> tuple[int, int]:
    """Get terminal size (columns, lines).

    Returns:
        Tuple of (columns, lines).
    """
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception as e:
        logger.debug(f"Error getting terminal size: {e}, using defaults")
        return 80, 24  # fallback


def display_with_pager(content: str, title: str = "") -> None:
    """Display content with less-like paging behavior.

    Args:
        content: The content to display.
        title: Optional title to show before content.
    """
    lines = content.split('\n')
    _, page_height = get_terminal_size()
    page_height = page_height - 2  # Reserve 2 lines for status and input

    if len(lines) <= page_height:
        # Content fits on screen, display directly
        if title:
            print_colored(title, Colors.BLUE)
            print("=" * 60)
            print()
        print(content)
        return

    current_line = 0

    if title:
        print_colored(title, Colors.BLUE)
        print("=" * 60)
        print()

    while current_line < len(lines):
        # Calculate how many lines to show
        end_line = min(current_line + page_height, len(lines))

        # Display the current page
        for i in range(current_line, end_line):
            print(lines[i])

        # Show status line
        if end_line >= len(lines):
            status = f"{Colors.BLUE}(END) - Press 'q' to quit, 'b' for back{Colors.NC}"
        else:
            percent = int((end_line / len(lines)) * 100)
            remaining = len(lines) - end_line
            status = f"{Colors.BLUE}-- More -- ({percent}%, {remaining} lines remaining) [Space/Enter: next, 'b': back, 'q': quit]{Colors.NC}"

        print(status, end='', flush=True)

        # Get user input
        try:
            # Try to read single character without Enter
            ch = _read_char()

            # Clear the status line
            status_len = len(status.replace(Colors.BLUE, '').replace(Colors.NC, ''))
            print('\r' + ' ' * status_len + '\r', end='')

            if ch.lower() == 'q':
                break
            elif ch.lower() == 'b':
                # Go back one page
                current_line = max(0, current_line - page_height)
            elif ch == ' ':
                # Space bar - next page
                current_line = end_line
            elif ch == '\r' or ch == '\n':
                # Enter - next line
                current_line = min(current_line + 1, len(lines) - page_height)
            elif ch == 'j':
                # j - next line (vim-like)
                current_line = min(current_line + 1, len(lines) - page_height)
            elif ch == 'k':
                # k - previous line (vim-like)
                current_line = max(0, current_line - 1)
            elif ch == 'd':
                # d - half page down
                current_line = min(current_line + page_height // 2, len(lines) - page_height)
            elif ch == 'u':
                # u - half page up
                current_line = max(0, current_line - page_height // 2)
            elif ch == 'g':
                # g - go to top
                current_line = 0
            elif ch.upper() == 'G':
                # G - go to bottom
                current_line = max(0, len(lines) - page_height)
            else:
                # Any other key - next page
                current_line = end_line

        except (ImportError, OSError):
            # Fallback for systems without termios (Windows)
            input()  # Just wait for Enter
            current_line = end_line


def _read_char() -> str:
    """Read a single character from stdin without waiting for Enter.

    Returns:
        Single character string.

    Raises:
        ImportError: On Windows where termios is not available.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

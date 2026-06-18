"""CLI utility helpers shared between the entry-point script and tests.

Keeping these here (rather than inline in claude-chat-manager.py) allows
tests to import and exercise the *production* logic instead of duplicating it.
"""

from typing import Optional

from .models import ChatSource


# Ordered tuple for argparse choices= — single canonical source of truth.
SOURCE_CHOICES: tuple[str, ...] = ('claude', 'kiro', 'codex', 'cline-vscode', 'cline', 'all')

# Derived set for O(1) membership tests (env var validation, is_chat_source_set).
VALID_SOURCE_VALUES: frozenset[str] = frozenset(SOURCE_CHOICES)


def parse_source_filter(source_str: Optional[str]) -> Optional[ChatSource]:
    """Convert a --source CLI string or CHAT_SOURCE env value to a ChatSource enum.

    Args:
        source_str: Value of the --source argument or CHAT_SOURCE env var,
            or None when omitted (means auto-detect / all sources).

    Returns:
        Corresponding ChatSource, or None when all sources should be used
        (i.e. source_str is None or 'all').

    Raises:
        ValueError: If source_str is a non-empty string that is not a
            recognised source value. This ensures typos and unsupported
            values are rejected loudly rather than silently falling back
            to auto-detect.
    """
    if source_str is None:
        return None
    # Normalise: strip whitespace and lowercase so CHAT_SOURCE=" Cline " works.
    normalised = source_str.strip().lower()
    if not normalised:
        return None  # Empty / whitespace-only → treat as unset (all sources)
    if normalised == 'claude':
        return ChatSource.CLAUDE_DESKTOP
    if normalised == 'kiro':
        return ChatSource.KIRO_IDE
    if normalised == 'codex':
        return ChatSource.CODEX
    if normalised in ('cline-vscode', 'cline'):
        # 'cline' is the back-compat alias for the VS Code extension source.
        return ChatSource.CLINE_VSCODE
    if normalised == 'all':
        return None  # None means all sources / auto-detect
    # Unknown non-empty value — reject loudly.
    raise ValueError(
        f"Unknown source value: {source_str!r}. "
        f"Valid values: {sorted(VALID_SOURCE_VALUES)}"
    )

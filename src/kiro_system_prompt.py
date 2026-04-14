"""Shared utility for detecting and stripping Kiro system prompt content.

Kiro IDE injects its full system prompt into the first user message in
execution logs. This module provides a single, conservative implementation
for detecting and removing that content, used by both the parser layer
(kiro_parser.py) and the filter layer (filters.py).

Detection requires a strong signature — at least 2 of the known Kiro
system tags must be present before any stripping occurs. This prevents
false positives on legitimate user content that happens to contain
XML-like tags.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Known Kiro system prompt XML tags. These are IDE internals injected
# into the first user message and should never appear in exports.
# Ordered from most specific (unique to Kiro) to most generic.
KIRO_SYSTEM_TAGS = [
    # Highly specific to Kiro — strong signature indicators
    'key_kiro_features',
    'autonomy_modes',
    'chat_context',
    'platform_specific_command_guidelines',
    'platform_specific_command_examples',
    'macos_linux_command_examples',
    'windows_command_examples',
    'subagents',
    'current_context',
    # Moderately specific
    'system_information',
    'current_date_and_time',
    'model_information',
    # Generic — only strip when signature is confirmed
    'identity',
    'capabilities',
    'response_style',
    'coding_questions',
    'rules',
    'goal',
    'spec',
    'hooks',
    'steering',
    'model_context_protocol',
    'internet_access',
]

# Tags that are strong Kiro signature indicators. If at least
# MIN_SIGNATURE_TAGS of these are found, we're confident this is
# a Kiro system prompt injection, not user content.
_SIGNATURE_TAGS = [
    'key_kiro_features',
    'autonomy_modes',
    'chat_context',
    'platform_specific_command_guidelines',
    'subagents',
    'current_context',
    'system_information',
    'current_date_and_time',
    'model_information',
]

# Minimum number of signature tags required to trigger stripping.
MIN_SIGNATURE_TAGS = 2


def has_kiro_system_prompt(text: str) -> bool:
    """Check whether text contains a Kiro system prompt injection.

    Uses conservative signature detection: at least MIN_SIGNATURE_TAGS
    of the known Kiro-specific tags must be present. This avoids false
    positives on legitimate user content.

    Args:
        text: Text to check.

    Returns:
        True if a Kiro system prompt signature is detected.
    """
    matches = sum(1 for tag in _SIGNATURE_TAGS if f'<{tag}>' in text)
    return matches >= MIN_SIGNATURE_TAGS


def strip_kiro_system_prompt(text: str) -> str:
    """Strip Kiro system prompt blocks from a user message.

    Only performs stripping when a strong Kiro signature is detected
    (at least MIN_SIGNATURE_TAGS known tags present). This prevents
    accidental removal of legitimate user content.

    Strips:
    - Leading Kiro system prompt XML blocks (preserves user content after them)
    - The assistant acknowledgment "I will follow these instructions."
    - Excessive whitespace left behind

    Args:
        text: User message text that may contain system prompt blocks.

    Returns:
        Cleaned text with system prompt blocks removed, or the original
        text unchanged if no Kiro signature was detected.
    """
    if not has_kiro_system_prompt(text):
        return text

    logger.debug("Kiro system prompt signature detected, stripping system blocks")

    # Build a combined pattern that matches any single system tag block
    # Uses a backreference to ensure opening and closing tags match
    tag_alts = '|'.join(re.escape(tag) for tag in KIRO_SYSTEM_TAGS)
    system_block_re = re.compile(
        rf'<\s*(?P<tag>{tag_alts})\s*>.*?</\s*(?P=tag)\s*>',
        flags=re.DOTALL
    )
    # Ack line: standalone line, must be followed by newline or end-of-string
    ack_re = re.compile(r'I will follow these instructions\.?[ \t]*(?:\n|$)')
    # Whitespace (including newlines) between blocks
    ws_re = re.compile(r'\s+')

    # Walk forward from the start, consuming contiguous system blocks,
    # inter-block whitespace, and the ack line. Stop at first non-system
    # content. The ack line is only consumed if at least one system block
    # was already consumed (to avoid stripping user content that happens
    # to start with that phrase).
    pos = 0
    consumed_system_block = False
    length = len(text)

    while pos < length:
        # Skip whitespace between blocks
        ws_match = ws_re.match(text, pos)
        if ws_match:
            pos = ws_match.end()
            if pos >= length:
                break

        # Try to match a system tag block at current position
        block_match = system_block_re.match(text, pos)
        if block_match:
            pos = block_match.end()
            consumed_system_block = True
            continue

        # Try to match the acknowledgment line, but only after
        # at least one real system block was consumed
        if consumed_system_block:
            ack_match = ack_re.match(text, pos)
            if ack_match:
                pos = ack_match.end()
                continue

        # Not a system block or ack — this is user content, stop
        break

    user_suffix = text[pos:]
    user_suffix = re.sub(r'\n{3,}', '\n\n', user_suffix)
    user_suffix = user_suffix.strip()

    return user_suffix

"""Shared Cline message-schema logic (host-agnostic).

Both the Cline VS Code extension and the Cline CLI store conversation
messages with the same ``say``/``ask`` schema:

    {"type": "say"|"ask", "say"/"ask": <subtype>, "text": "...", "ts": <ms>}

Only the *storage container* differs between hosts:
- VS Code extension: per-task JSON files (ui_messages.json)
- Cline CLI: a SQLite session database under ~/.cline/data/

This module centralizes the parts that depend only on the message
schema — the keep/skip subtype classification, the JSON-encoded ``ask``
text decoding, and content normalization — so each host adapter
(``cline_vscode_parser``, future ``cline_cli_parser``) can reuse them.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subtype classification sets (shared across hosts)
# ---------------------------------------------------------------------------

#: ``say`` subtypes that represent user-authored messages.
USER_SAY_SUBTYPES = frozenset({'task', 'user_feedback'})

#: ``say`` subtypes that represent assistant-authored messages.
ASSISTANT_SAY_SUBTYPES = frozenset({'text', 'completion_result'})

#: ``ask`` subtypes that represent assistant-authored messages.
#: Their ``text`` field is JSON-encoded — decode with :func:`decode_ask_text`.
ASSISTANT_ASK_SUBTYPES = frozenset(
    {'plan_mode_respond', 'followup', 'completion_result'}
)


def classify_say(subtype: str) -> str:
    """Classify a ``say`` subtype into a conversation role.

    Args:
        subtype: The ``say`` subtype value.

    Returns:
        ``"user"`` or ``"assistant"`` for kept subtypes, or ``""`` to skip.
    """
    if subtype in USER_SAY_SUBTYPES:
        return 'user'
    if subtype in ASSISTANT_SAY_SUBTYPES:
        return 'assistant'
    return ''


def classify_ask(subtype: str) -> str:
    """Classify an ``ask`` subtype into a conversation role.

    Args:
        subtype: The ``ask`` subtype value.

    Returns:
        ``"assistant"`` for kept subtypes, or ``""`` to skip.
    """
    if subtype in ASSISTANT_ASK_SUBTYPES:
        return 'assistant'
    return ''


def decode_ask_text(ask_subtype: str, raw_text: Any) -> str:
    """Decode the JSON-encoded text of an ``ask`` entry into display text.

    ``ask`` entries store their payload as a JSON string in ``text`` (e.g.
    ``{"response": "..."}`` for ``plan_mode_respond``). This decodes the
    relevant field defensively and always returns a string.

    Args:
        ask_subtype: The ask subtype (plan_mode_respond, followup, etc.).
        raw_text: Raw text field (JSON string or plain text).

    Returns:
        Decoded display text (always a string).
    """
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return _coerce_str(raw_text)

    if not isinstance(data, dict):
        return str(data)

    if ask_subtype == 'plan_mode_respond':
        return _coerce_str(data.get('response', ''))

    if ask_subtype == 'followup':
        question = _coerce_str(data.get('question', ''))
        options = data.get('options') or []
        if isinstance(options, list) and options:
            opts = '\n'.join(f'- {o}' for o in options if o is not None)
            if opts:
                return f'{question}\n\n{opts}' if question else opts
        return question

    if ask_subtype == 'completion_result':
        return _coerce_str(data.get('response', raw_text))

    return _coerce_str(raw_text)


def normalize_cline_content(content: Any) -> str:
    """Normalize Cline message content to plain text.

    Args:
        content: Message content — string or structured data.

    Returns:
        Normalized, stripped string content.
    """
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        # Handle content arrays (unlikely for Cline but defensive)
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get('type') == 'text':
                text_val = item.get('text', '')
                if isinstance(text_val, str):
                    text_parts.append(text_val)
                elif text_val is not None:
                    text_parts.append(str(text_val))
            elif item is not None and not isinstance(item, dict):
                text_parts.append(str(item))
        return '\n'.join(text_parts).strip()

    if content is None:
        return ''

    return str(content).strip()


def _coerce_str(value: Any) -> str:
    """Coerce a value to a string, mapping ``None`` to ``""``."""
    if isinstance(value, str):
        return value
    if value is None:
        return ''
    return str(value)

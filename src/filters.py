"""Shared filtering utilities for chat content.

This module provides reusable filtering logic for both wiki and book export modes,
including trivial chat detection, system tag removal, and content cleaning.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ChatFilter:
    """Shared filtering logic for chat content processing."""

    def __init__(
        self,
        skip_trivial: bool = True,
        min_messages: int = 3,
        min_words: int = 75,
        skip_keywords: List[str] = None,
        require_content: bool = False,
        filter_system_tags: bool = True
    ) -> None:
        """Initialize chat filter with configuration.

        Args:
            skip_trivial: Whether to filter out trivial chats.
            min_messages: Minimum number of messages required.
            min_words: Minimum total word count required.
            skip_keywords: Keywords indicating trivial chats.
            require_content: Require code blocks or file references.
            filter_system_tags: Whether to strip system tags from user messages.
        """
        self.skip_trivial = skip_trivial
        self.min_messages = min_messages
        self.min_words = min_words
        self.skip_keywords = skip_keywords or ['warmup', 'test', 'hello', 'hi', 'ready']
        self.require_content = require_content
        self.filter_system_tags = filter_system_tags

    def is_pointless_chat(self, chat_data: List[Dict[str, Any]]) -> bool:
        """Check if a chat is trivial/pointless and should be filtered out.

        Uses hybrid filtering approach:
        1. Message count threshold
        2. Word count threshold
        3. Keyword detection in first user message
        4. Content requirement (optional)

        Args:
            chat_data: Parsed chat data.

        Returns:
            True if chat should be filtered out, False otherwise.
        """
        # Skip filtering if disabled
        if not self.skip_trivial:
            return False

        # Extract conversation messages (exclude system messages)
        # Support both Claude ('user'/'assistant') and Kiro ('human'/'bot') role names
        messages = [
            entry for entry in chat_data
            if entry.get('message', {}).get('role') in ('user', 'assistant', 'human', 'bot')
        ]

        # Check 1: Message count threshold
        if len(messages) < self.min_messages:
            logger.debug(f"Chat filtered: too few messages ({len(messages)} < {self.min_messages})")
            return True

        # Check 2: Word count threshold
        total_words = 0
        for entry in messages:
            text = self.extract_text_only(entry.get('message', {}).get('content', ''))
            total_words += len(text.split())

        if total_words < self.min_words:
            logger.debug(f"Chat filtered: too few words ({total_words} < {self.min_words})")
            return True

        # Check 3: Keyword detection in first user message
        # Support both Claude ('user') and Kiro ('human') role names
        first_user_text = None
        for entry in messages:
            if entry.get('message', {}).get('role') in ('user', 'human'):
                first_user_text = self.extract_text_only(
                    entry.get('message', {}).get('content', '')
                ).lower().strip()
                break

        if first_user_text:
            # Check if first message is a single keyword
            first_user_words = first_user_text.split()
            if len(first_user_words) <= 2:  # Very short first message
                for keyword in self.skip_keywords:
                    if keyword in first_user_text:
                        logger.debug(f"Chat filtered: keyword '{keyword}' in first message")
                        return True

        # Check 4: Content requirement (optional)
        if self.require_content:
            has_content = False
            for entry in messages:
                content = entry.get('message', {}).get('content', '')
                # Check for code blocks
                if isinstance(content, str) and ('```' in content):
                    has_content = True
                    break
                # Check for file references in tool use
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get('type') == 'tool_use':
                                tool_input = item.get('input', {})
                                if 'file_path' in tool_input:
                                    has_content = True
                                    break
                            elif item.get('type') == 'text' and '```' in item.get('text', ''):
                                has_content = True
                                break
                if has_content:
                    break

            if not has_content:
                logger.debug("Chat filtered: no code blocks or file references")
                return True

        # Chat passes all filters
        return False

    def strip_system_tags(self, text: str) -> str:
        """Remove system notification tags from user message.

        Args:
            text: User message text that may contain system tags.

        Returns:
            Text with system tags removed.
        """
        if not self.filter_system_tags:
            return text

        # Known system tag patterns
        system_patterns = [
            r'<ide_opened_file>.*?</ide_opened_file>',
            r'<system-reminder>.*?</system-reminder>',
            r'<user-prompt-submit-hook>.*?</user-prompt-submit-hook>',
            r'<command-message>.*?</command-message>',
        ]

        # Remove each pattern
        cleaned = text
        for pattern in system_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL)

        # Clean up extra whitespace
        cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)  # Max 2 newlines
        cleaned = cleaned.strip()

        return cleaned

    def clean_user_message(self, text: str) -> Optional[str]:
        """Clean user message by removing system notifications.

        Uses smart detection:
        - If message is only system tags → Returns None (skip message)
        - If message has system tags + user text → Returns cleaned text
        - If no system tags → Returns original text

        Args:
            text: User message text.

        Returns:
            Cleaned text or None if message is purely system notification.
        """
        if not self.filter_system_tags:
            return text

        # Strip system tags
        cleaned = self.strip_system_tags(text)

        # If nothing meaningful left after stripping, skip this message
        # Consider message meaningless if < 5 chars or only whitespace
        if not cleaned or len(cleaned.strip()) < 5:
            logger.debug("Filtered system-only user message")
            return None

        return cleaned

    def extract_clean_content(
        self,
        content: Any,
        include_tool_use: bool = False
    ) -> Tuple[str, List[str]]:
        """Extract clean text and file references from content.

        Filters out tool use/result messages unless include_tool_use is True.

        Args:
            content: Message content (string, list, or dict).
            include_tool_use: Whether to include tool use information.

        Returns:
            Tuple of (clean_text, list_of_files).
        """
        text_parts = []
        files = []

        if isinstance(content, str):
            return content.strip(), []

        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    if isinstance(item, str) and item.strip():
                        text_parts.append(item.strip())
                    continue

                item_type = item.get('type', '')

                if item_type == 'text':
                    # Regular text content
                    text = item.get('text', '').strip()
                    if text:
                        # Preserve code blocks (fenced format)
                        text_parts.append(text)

                elif item_type == 'tool_use':
                    # Extract file reference from tool use
                    tool_input = item.get('input', {})
                    if 'file_path' in tool_input:
                        files.append(tool_input['file_path'])
                    # Skip the tool use message itself unless requested
                    if include_tool_use:
                        tool_name = item.get('name', 'unknown')
                        text_parts.append(f'[Tool: {tool_name}]')

                # Skip tool_result, image, etc.

        elif isinstance(content, dict):
            if 'text' in content:
                return content['text'].strip(), []
            elif 'content' in content:
                return self.extract_clean_content(content['content'], include_tool_use)

        clean_text = '\n\n'.join(text_parts)
        return clean_text, files

    def extract_text_only(self, content: Any) -> str:
        """Extract only text content, ignoring everything else.

        Args:
            content: Message content.

        Returns:
            Plain text string.
        """
        text, _ = self.extract_clean_content(content, include_tool_use=False)
        return text

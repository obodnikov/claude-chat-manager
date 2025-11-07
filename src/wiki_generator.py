"""Wiki generation functionality.

This module generates clean, readable wiki-style documentation from
Claude chat files by filtering noise and organizing content.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .llm_client import OpenRouterClient, OpenRouterError
from .parser import parse_jsonl_file
from .formatters import format_timestamp, clean_project_name
from .wiki_parser import WikiParser, WikiChatSection
from .config import config

logger = logging.getLogger(__name__)


@dataclass
class WikiGenerationStats:
    """Statistics from wiki generation process."""

    total_chats: int
    existing_chats: int
    new_chats: int
    titles_from_cache: int
    titles_generated: int
    strategy_used: str  # 'new', 'append', 'rebuild'
    filtered_chats: int  # Number of chats filtered out as trivial


class WikiGenerator:
    """Generate wiki-style documentation from chat files."""

    def __init__(self, llm_client: Optional[OpenRouterClient] = None) -> None:
        """Initialize wiki generator.

        Args:
            llm_client: Optional OpenRouter client for title generation.
                       If None, will use fallback title generation.
        """
        self.llm_client = llm_client
        logger.debug(f"WikiGenerator initialized (LLM: {llm_client is not None})")

    def _is_pointless_chat(self, chat_data: List[Dict[str, Any]]) -> bool:
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
        if not config.wiki_skip_trivial:
            return False

        # Extract conversation messages (exclude system messages)
        messages = [
            entry for entry in chat_data
            if entry.get('message', {}).get('role') in ('user', 'assistant')
        ]

        # Check 1: Message count threshold
        if len(messages) < config.wiki_min_messages:
            logger.debug(f"Chat filtered: too few messages ({len(messages)} < {config.wiki_min_messages})")
            return True

        # Check 2: Word count threshold
        total_words = 0
        for entry in messages:
            text = self._extract_text_only(entry.get('message', {}).get('content', ''))
            total_words += len(text.split())

        if total_words < config.wiki_min_words:
            logger.debug(f"Chat filtered: too few words ({total_words} < {config.wiki_min_words})")
            return True

        # Check 3: Keyword detection in first user message
        first_user_text = None
        for entry in messages:
            if entry.get('message', {}).get('role') == 'user':
                first_user_text = self._extract_text_only(
                    entry.get('message', {}).get('content', '')
                ).lower().strip()
                break

        if first_user_text:
            # Check if first message is a single keyword
            first_user_words = first_user_text.split()
            if len(first_user_words) <= 2:  # Very short first message
                for keyword in config.wiki_skip_keywords:
                    if keyword in first_user_text:
                        logger.debug(f"Chat filtered: keyword '{keyword}' in first message")
                        return True

        # Check 4: Content requirement (optional)
        if config.wiki_require_content:
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

    def generate_wiki(
        self,
        chat_files: List[Path],
        project_name: str,
        use_llm_titles: bool = True,
        existing_wiki: Optional[Path] = None,
        update_mode: str = 'new'
    ) -> Tuple[str, WikiGenerationStats]:
        """Generate complete wiki from multiple chat files.

        Args:
            chat_files: List of JSONL chat file paths.
            project_name: Name of the project.
            use_llm_titles: Whether to use LLM for title generation.
            existing_wiki: Optional path to existing wiki file to update.
            update_mode: Mode: 'new', 'update', or 'rebuild'.

        Returns:
            Tuple of (wiki_content, generation_stats).
        """
        logger.info(f"Generating wiki for {len(chat_files)} chats (mode: {update_mode})")

        # Initialize stats tracking
        titles_from_cache = 0
        titles_generated = 0
        filtered_chats = 0
        strategy_used = update_mode

        # Handle existing wiki for update/rebuild modes
        existing_sections = {}
        cached_titles = {}

        if update_mode in ['update', 'rebuild'] and existing_wiki and existing_wiki.exists():
            try:
                parser = WikiParser(existing_wiki)
                existing_sections = parser.parse()
                # Cache titles from existing wiki
                cached_titles = {
                    chat_id: section.title
                    for chat_id, section in existing_sections.items()
                }
                logger.info(f"Loaded {len(existing_sections)} existing sections from wiki")
            except Exception as e:
                logger.warning(f"Could not parse existing wiki: {e}")
                logger.info("Proceeding with full generation")
                existing_sections = {}

        # Collect all chat sections with metadata
        chat_sections = []

        # Create a map of chat file to chat ID for comparison
        chat_file_ids = {self._get_chat_id(f): f for f in chat_files}

        # Determine which chats are new
        existing_chat_ids = set(existing_sections.keys())
        current_chat_ids = set(chat_file_ids.keys())
        new_chat_ids = current_chat_ids - existing_chat_ids

        logger.info(f"Found {len(existing_chat_ids)} existing chats, "
                   f"{len(new_chat_ids)} new chats")

        # For update mode, check if we can do append-only
        can_append = False
        if update_mode == 'update' and existing_sections:
            # Get timestamps that are greater than 0
            valid_timestamps = [
                s.timestamp for s in existing_sections.values() if s.timestamp > 0
            ]
            latest_existing_timestamp = max(valid_timestamps) if valid_timestamps else 0

            # Check if all new chats are newer than the latest existing chat
            new_chat_timestamps = []
            for chat_id in new_chat_ids:
                chat_file = chat_file_ids[chat_id]
                try:
                    chat_data = parse_jsonl_file(chat_file)
                    if chat_data:
                        ts = self._extract_timestamp(chat_data)
                        if ts > 0:
                            new_chat_timestamps.append(ts)
                except Exception:
                    pass

            # Only use append-only if we have valid timestamps for both existing and new chats
            if new_chat_timestamps and latest_existing_timestamp > 0:
                min_new_timestamp = min(new_chat_timestamps)
                can_append = min_new_timestamp > latest_existing_timestamp

            if can_append:
                logger.info("All new chats are newer - using append-only strategy")
                strategy_used = 'append'
            elif latest_existing_timestamp == 0:
                logger.info("No timestamps in existing wiki - using full rebuild strategy")
                strategy_used = 'rebuild'
            else:
                logger.info("New chats require insertion - using full rebuild strategy")
                strategy_used = 'rebuild'

        for chat_file in chat_files:
            try:
                chat_data = parse_jsonl_file(chat_file)
                if not chat_data:
                    logger.warning(f"Empty chat file: {chat_file.name}")
                    continue

                # Filter out pointless chats
                if self._is_pointless_chat(chat_data):
                    logger.info(f"Filtering out trivial chat: {chat_file.name}")
                    filtered_chats += 1
                    continue

                # Get chat ID from filename
                chat_id = self._get_chat_id(chat_file)

                # Check if we have a cached title (for update/rebuild modes)
                title = None
                if chat_id in cached_titles and update_mode != 'rebuild':
                    title = cached_titles[chat_id]
                    titles_from_cache += 1
                    logger.debug(f"Using cached title for {chat_id}: {title}")

                # Generate title if not cached
                if not title:
                    if use_llm_titles and self.llm_client:
                        title = self._generate_title_with_llm(chat_data)
                    else:
                        title = self._generate_fallback_title(chat_data, chat_file)
                    titles_generated += 1

                # Get chat date
                date_str = self._extract_chat_date(chat_data)

                # Store chat data for content generation later (with section numbers)
                chat_sections.append({
                    'title': title,
                    'date': date_str,
                    'chat_id': chat_id,
                    'chat_data': chat_data,  # Store raw data
                    'timestamp': self._extract_timestamp(chat_data)
                })

            except Exception as e:
                logger.error(f"Error processing {chat_file.name}: {e}")
                continue

        # Sort by timestamp (chronological)
        chat_sections.sort(key=lambda x: x['timestamp'] if x['timestamp'] else 0)

        # Generate final wiki
        wiki = self._build_wiki_document(project_name, chat_sections)

        # Create stats object
        stats = WikiGenerationStats(
            total_chats=len(chat_sections),
            existing_chats=len(existing_chat_ids),
            new_chats=len(new_chat_ids),
            titles_from_cache=titles_from_cache,
            titles_generated=titles_generated,
            strategy_used=strategy_used,
            filtered_chats=filtered_chats
        )

        logger.info(f"Wiki generated successfully with {len(chat_sections)} sections")
        return wiki, stats

    def _generate_title_with_llm(self, chat_data: List[Dict[str, Any]]) -> str:
        """Generate title using LLM.

        Args:
            chat_data: Parsed chat data.

        Returns:
            Generated title or fallback.
        """
        try:
            # Extract conversation excerpt (first ~2000 tokens)
            excerpt = self._extract_conversation_excerpt(chat_data, max_tokens=2000)

            if not excerpt:
                logger.warning("No conversation excerpt to generate title from")
                return "Untitled Chat"

            # Generate title via LLM
            title = self.llm_client.generate_chat_title(excerpt, max_words=10)

            if title:
                return title
            else:
                logger.warning("LLM title generation failed, using fallback")
                return self._generate_fallback_title(chat_data, None)

        except OpenRouterError as e:
            logger.error(f"OpenRouter error: {e}")
            return self._generate_fallback_title(chat_data, None)

    def _generate_fallback_title(
        self,
        chat_data: List[Dict[str, Any]],
        chat_file: Optional[Path]
    ) -> str:
        """Generate title without LLM (fallback).

        Uses first user question as title.

        Args:
            chat_data: Parsed chat data.
            chat_file: Optional chat file path.

        Returns:
            Fallback title string.
        """
        # Try to find first user question
        for entry in chat_data:
            message = entry.get('message', {})
            role = message.get('role', '')
            content = message.get('content', '')

            if role == 'user':
                # Extract text from content
                text = self._extract_text_only(content)
                if text:
                    # Use first line or first 60 chars
                    first_line = text.split('\n')[0]
                    title = first_line[:60].strip()
                    if len(first_line) > 60:
                        title += "..."
                    return title

        # Last resort: use filename or generic title
        if chat_file:
            return f"Chat {chat_file.stem[:8]}"
        else:
            return "Untitled Chat"

    def _extract_conversation_excerpt(
        self,
        chat_data: List[Dict[str, Any]],
        max_tokens: int = 2000
    ) -> str:
        """Extract first portion of conversation for title generation.

        Args:
            chat_data: Parsed chat data.
            max_tokens: Approximate max tokens (chars/4).

        Returns:
            Conversation excerpt as string.
        """
        max_chars = max_tokens * 4  # Rough estimate
        excerpt_parts = []
        total_chars = 0

        for entry in chat_data[:20]:  # First 20 messages max
            message = entry.get('message', {})
            role = message.get('role', '')
            content = message.get('content', '')

            # Extract text only (no tool noise)
            text = self._extract_text_only(content)
            if not text:
                continue

            # Add role prefix
            prefix = "User: " if role == 'user' else "Assistant: "
            message_text = f"{prefix}{text}\n\n"

            # Check if we exceed limit
            if total_chars + len(message_text) > max_chars:
                break

            excerpt_parts.append(message_text)
            total_chars += len(message_text)

        return ''.join(excerpt_parts)

    def _generate_chat_content(
        self,
        chat_data: List[Dict[str, Any]],
        chat_section_num: int = 0
    ) -> Tuple[str, List[str]]:
        """Generate clean wiki content from chat data.

        Filters out tool use/result noise, keeps only conversation.

        Args:
            chat_data: Parsed chat data.
            chat_section_num: Section number for anchor generation.

        Returns:
            Tuple of (clean_markdown_content, list_of_user_questions).
        """
        content_parts = []
        files_modified = set()
        user_questions = []
        user_question_count = 0

        for entry in chat_data:
            message = entry.get('message', {})
            role = message.get('role', '')
            content = message.get('content', '')

            if not role or role == 'system':
                continue

            # Extract clean text and any file references
            text, files = self._extract_clean_content(content)

            if not text:
                continue

            # Add files to tracking
            files_modified.update(files)

            # Format based on role
            if role == 'user':
                user_question_count += 1

                # Extract first line or truncate for TOC
                first_line = text.split('\n')[0].strip()
                if len(first_line) > 80:
                    first_line = first_line[:77] + '...'

                # Store user question for TOC
                user_questions.append(first_line)

                # Create anchor for this user question
                anchor_id = f"chat{chat_section_num}-user-q{user_question_count}"

                # Add visual separator and marker for user input
                content_parts.append("---\n")
                content_parts.append(f'<a id="{anchor_id}"></a>\n')
                content_parts.append("👤 **USER:**\n")
                content_parts.append(f"> {text}\n")

            elif role == 'assistant':
                # Assistant response
                content_parts.append(f"{text}\n")

                # Add file references if any
                if files:
                    files_list = ', '.join(f'`{f}`' for f in sorted(files))
                    content_parts.append(f"\n*Files: {files_list}*\n")

        return '\n'.join(content_parts), user_questions

    def _extract_clean_content(self, content: Any) -> Tuple[str, List[str]]:
        """Extract clean text and file references from content.

        Filters out tool use/result messages.

        Args:
            content: Message content (string, list, or dict).

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
                    # Skip the tool use message itself

                # Skip tool_result, image, etc.

        elif isinstance(content, dict):
            if 'text' in content:
                return content['text'].strip(), []
            elif 'content' in content:
                return self._extract_clean_content(content['content'])

        clean_text = '\n\n'.join(text_parts)
        return clean_text, files

    def _extract_text_only(self, content: Any) -> str:
        """Extract only text content, ignoring everything else.

        Args:
            content: Message content.

        Returns:
            Plain text string.
        """
        text, _ = self._extract_clean_content(content)
        return text

    def _extract_chat_date(self, chat_data: List[Dict[str, Any]]) -> str:
        """Extract date from first message in chat.

        Args:
            chat_data: Parsed chat data.

        Returns:
            Formatted date string (e.g., "Oct 15, 2025").
        """
        if not chat_data:
            return "Unknown"

        first_entry = chat_data[0]
        timestamp = first_entry.get('timestamp')

        if not timestamp:
            return "Unknown"

        formatted = format_timestamp(timestamp)
        if formatted == 'No timestamp' or formatted == 'Invalid timestamp':
            return "Unknown"

        try:
            # Parse and reformat to "Oct 15, 2025"
            dt = datetime.strptime(formatted, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%b %d, %Y')
        except:
            return formatted.split()[0]  # Just the date part

    def _extract_timestamp(self, chat_data: List[Dict[str, Any]]) -> float:
        """Extract unix timestamp from first message for sorting.

        Args:
            chat_data: Parsed chat data.

        Returns:
            Unix timestamp or 0 if not found.
        """
        if not chat_data:
            return 0

        first_entry = chat_data[0]
        timestamp = first_entry.get('timestamp')

        if not timestamp:
            return 0

        if isinstance(timestamp, (int, float)):
            # Already numeric
            return timestamp if timestamp < 10000000000 else timestamp / 1000

        # Try to parse ISO format
        if isinstance(timestamp, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.timestamp()
            except:
                return 0

        return 0

    def _build_wiki_document(
        self,
        project_name: str,
        chat_sections: List[Dict[str, Any]]
    ) -> str:
        """Build complete wiki document with hierarchical TOC.

        Args:
            project_name: Project name.
            chat_sections: List of chat section dicts with chat_data.

        Returns:
            Complete wiki markdown.
        """
        lines = []

        # Header
        lines.append(f"# Project Wiki: {project_name}\n")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        lines.append(f"**Total Chats:** {len(chat_sections)}  ")

        if chat_sections:
            dates = [s['date'] for s in chat_sections if s['date'] != 'Unknown']
            if dates:
                lines.append(f"**Date Range:** {dates[0]} to {dates[-1]}  ")

        lines.append("\n---\n")

        # Generate content for each section to extract user questions
        sections_with_content = []
        for i, section in enumerate(chat_sections, 1):
            chat_data = section.get('chat_data', [])
            content, user_questions = self._generate_chat_content(chat_data, i)

            sections_with_content.append({
                'section_num': i,
                'title': section['title'],
                'date': section['date'],
                'chat_id': section['chat_id'],
                'timestamp': section['timestamp'],
                'content': content,
                'user_questions': user_questions
            })

        # Table of Contents (Hierarchical with user questions)
        lines.append("## 📑 Table of Contents\n")
        for section in sections_with_content:
            i = section['section_num']
            title = section['title']
            date = section['date']
            chat_id = section['chat_id']
            user_questions = section['user_questions']

            anchor = self._create_anchor(i, title)
            lines.append(f"### {i}. [{title}](#{anchor})")
            lines.append(f"*{date} | Chat ID: {chat_id}*\n")

            # Add user questions as sub-items if any
            if user_questions:
                lines.append("**Key Topics:**")
                for q_num, question in enumerate(user_questions, 1):
                    q_anchor = f"chat{i}-user-q{q_num}"
                    lines.append(f"- 🗣️ [{question}](#{q_anchor})")

            lines.append("")  # Blank line after each section

        lines.append("---\n")

        # Chat sections with content
        for section in sections_with_content:
            i = section['section_num']
            title = section['title']
            date = section['date']
            chat_id = section['chat_id']
            content = section['content']
            timestamp = section['timestamp']

            # Section header
            lines.append(f"## {i}. {title}")
            # Add invisible metadata cache for future updates
            lines.append(f"<!-- wiki-meta: chat_id={chat_id}, timestamp={timestamp} -->")
            lines.append(f"*Date: {date} | Chat ID: {chat_id}*\n")

            # Content (already includes user markers and anchors)
            lines.append(content)

            # Separator between chats
            if i < len(sections_with_content):
                lines.append("\n---\n")

        return '\n'.join(lines)

    def _create_anchor(self, number: int, title: str) -> str:
        """Create markdown anchor from section number and title.

        Args:
            number: Section number.
            title: Section title.

        Returns:
            Anchor string.

        Example:
            >>> _create_anchor(1, "My Cool Title")
            '1-my-cool-title'
        """
        # GitHub markdown anchor format
        # Lowercase, replace spaces with hyphens, remove special chars
        anchor = f"{number}-{title.lower()}"
        anchor = re.sub(r'[^\w\s-]', '', anchor)
        anchor = re.sub(r'[-\s]+', '-', anchor)
        return anchor.strip('-')

    def _get_chat_id(self, chat_file: Path) -> str:
        """Extract chat ID from chat filename.

        Args:
            chat_file: Path to chat file.

        Returns:
            Chat ID (first 8 chars of UUID).
        """
        return chat_file.stem[:8]

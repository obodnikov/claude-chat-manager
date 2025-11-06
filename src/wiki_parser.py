"""Wiki markdown parser for extracting metadata from existing wiki files.

This module parses existing wiki files to extract chat IDs, titles, and
timestamps to enable smart wiki updates.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WikiChatSection:
    """Represents a chat section extracted from an existing wiki."""

    chat_id: str
    title: str
    date: str
    timestamp: float
    section_number: int
    content: str


class WikiParser:
    """Parse existing wiki files to extract chat metadata."""

    def __init__(self, wiki_file: Path) -> None:
        """Initialize wiki parser.

        Args:
            wiki_file: Path to existing wiki markdown file.
        """
        self.wiki_file = wiki_file
        self.sections: List[WikiChatSection] = []
        logger.debug(f"WikiParser initialized for: {wiki_file}")

    def parse(self) -> Dict[str, WikiChatSection]:
        """Parse wiki file and extract all chat sections.

        Returns:
            Dictionary mapping chat_id to WikiChatSection.

        Raises:
            FileNotFoundError: If wiki file doesn't exist.
            ValueError: If wiki format is invalid.
        """
        if not self.wiki_file.exists():
            raise FileNotFoundError(f"Wiki file not found: {self.wiki_file}")

        try:
            with open(self.wiki_file, 'r', encoding='utf-8') as f:
                content = f.read()

            sections_dict = self._extract_sections(content)

            logger.info(f"Parsed {len(sections_dict)} sections from wiki")
            return sections_dict

        except Exception as e:
            logger.error(f"Error parsing wiki file: {e}")
            raise ValueError(f"Failed to parse wiki file: {e}")

    def _extract_sections(self, content: str) -> Dict[str, WikiChatSection]:
        """Extract all chat sections from wiki content.

        Args:
            content: Raw wiki markdown content.

        Returns:
            Dictionary mapping chat_id to WikiChatSection.
        """
        sections_dict = {}

        # Split content by section headers (## 1. Title, ## 2. Title, etc.)
        section_pattern = r'^## (\d+)\.\s+(.+?)$'

        # Find all section headers
        lines = content.split('\n')
        section_starts = []

        for i, line in enumerate(lines):
            match = re.match(section_pattern, line)
            if match:
                section_num = int(match.group(1))
                title = match.group(2).strip()
                section_starts.append((i, section_num, title))

        # Extract each section
        for idx, (line_num, section_num, title) in enumerate(section_starts):
            # Determine section end (next section or end of file)
            end_line = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(lines)

            # Extract section content
            section_lines = lines[line_num:end_line]
            section_content = '\n'.join(section_lines)

            # Parse metadata from next few lines
            # Format: line after header might be HTML comment or metadata line
            # ## 1. Title
            # <!-- wiki-meta: chat_id=abc12345, timestamp=1704412800 -->
            # *Date: Jan 10, 2025 | Chat ID: abc12345*
            chat_id = None
            date = "Unknown"
            timestamp = 0.0

            # Check first few lines after the header for both HTML comment and metadata
            for check_line in section_lines[:5]:
                # Try to extract timestamp from HTML comment
                meta_match = re.search(
                    r'<!-- wiki-meta: chat_id=([a-f0-9]+), timestamp=([\d.]+) -->',
                    check_line
                )
                if meta_match and not chat_id:
                    chat_id = meta_match.group(1)
                    timestamp = float(meta_match.group(2))

                # Try to extract from metadata line *Date: ... | Chat ID: ...*
                if re.match(r'^\s*\*Date:', check_line):
                    # Extract chat ID
                    chat_id_match = re.search(r'Chat ID:\s*([a-f0-9]+)', check_line)
                    if chat_id_match and not chat_id:
                        chat_id = chat_id_match.group(1)

                    # Extract date
                    date_match = re.search(r'Date:\s*([^|]+)', check_line)
                    if date_match:
                        date = date_match.group(1).strip()

            if not chat_id:
                logger.warning(f"Could not extract chat ID from section {section_num}")
                continue

            # Create WikiChatSection
            section = WikiChatSection(
                chat_id=chat_id,
                title=title,
                date=date,
                timestamp=timestamp,
                section_number=section_num,
                content=section_content
            )

            sections_dict[chat_id] = section

        return sections_dict

    def get_latest_timestamp(self, sections: Dict[str, WikiChatSection]) -> float:
        """Get the latest timestamp from all sections.

        Args:
            sections: Dictionary of wiki chat sections.

        Returns:
            Latest timestamp, or 0 if no valid timestamps found.
        """
        if not sections:
            return 0.0

        timestamps = [s.timestamp for s in sections.values() if s.timestamp > 0]
        return max(timestamps) if timestamps else 0.0

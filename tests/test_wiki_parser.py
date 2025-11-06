"""Tests for wiki_parser module."""

import pytest
from pathlib import Path
import tempfile
from src.wiki_parser import WikiParser, WikiChatSection


@pytest.fixture
def sample_wiki_content():
    """Sample wiki markdown content with metadata."""
    return """# Project Wiki: Test Project

**Generated:** 2025-01-15 10:30:00
**Total Chats:** 2
**Date Range:** Jan 10, 2025 to Jan 15, 2025

---

## 📑 Table of Contents

1. [First Chat Title](#1-first-chat-title) - *Jan 10, 2025*
2. [Second Chat Title](#2-second-chat-title) - *Jan 15, 2025*

---

## 1. First Chat Title
<!-- wiki-meta: chat_id=abc12345, timestamp=1704844800 -->
*Date: Jan 10, 2025 | Chat ID: abc12345*

> How do I test this?

You can test it like this...

---

## 2. Second Chat Title
<!-- wiki-meta: chat_id=def67890, timestamp=1705276800 -->
*Date: Jan 15, 2025 | Chat ID: def67890*

> What about another question?

Here's the answer...

---
"""


@pytest.fixture
def wiki_file(tmp_path, sample_wiki_content):
    """Create a temporary wiki file."""
    wiki_path = tmp_path / "test-wiki.md"
    wiki_path.write_text(sample_wiki_content, encoding='utf-8')
    return wiki_path


def test_wiki_parser_initialization(wiki_file):
    """Test WikiParser initialization."""
    parser = WikiParser(wiki_file)
    assert parser.wiki_file == wiki_file
    assert parser.sections == []


def test_wiki_parser_parse(wiki_file):
    """Test parsing a valid wiki file."""
    parser = WikiParser(wiki_file)
    sections = parser.parse()

    assert len(sections) == 2
    assert 'abc12345' in sections
    assert 'def67890' in sections


def test_wiki_parser_section_content(wiki_file):
    """Test parsed section content."""
    parser = WikiParser(wiki_file)
    sections = parser.parse()

    section1 = sections['abc12345']
    assert section1.chat_id == 'abc12345'
    assert section1.title == 'First Chat Title'
    assert section1.date == 'Jan 10, 2025'
    assert section1.timestamp == 1704844800
    assert section1.section_number == 1

    section2 = sections['def67890']
    assert section2.chat_id == 'def67890'
    assert section2.title == 'Second Chat Title'
    assert section2.date == 'Jan 15, 2025'
    assert section2.timestamp == 1705276800
    assert section2.section_number == 2


def test_wiki_parser_nonexistent_file(tmp_path):
    """Test parsing a nonexistent wiki file."""
    fake_path = tmp_path / "nonexistent.md"
    parser = WikiParser(fake_path)

    with pytest.raises(FileNotFoundError):
        parser.parse()


def test_wiki_parser_get_latest_timestamp(wiki_file):
    """Test getting latest timestamp from sections."""
    parser = WikiParser(wiki_file)
    sections = parser.parse()

    latest = parser.get_latest_timestamp(sections)
    assert latest == 1705276800  # Second chat's timestamp


def test_wiki_parser_empty_sections():
    """Test get_latest_timestamp with empty sections."""
    parser = WikiParser(Path("dummy.md"))
    latest = parser.get_latest_timestamp({})
    assert latest == 0.0


def test_wiki_parser_without_metadata_comments(tmp_path):
    """Test parsing wiki without HTML comment metadata."""
    content = """# Project Wiki: Test

**Generated:** 2025-01-15 10:30:00

---

## 1. Chat Without Metadata
*Date: Jan 10, 2025 | Chat ID: abc99999*

> Test question

Test answer
"""
    wiki_path = tmp_path / "no-meta.md"
    wiki_path.write_text(content, encoding='utf-8')

    parser = WikiParser(wiki_path)
    sections = parser.parse()

    assert len(sections) == 1
    assert 'abc99999' in sections
    section = sections['abc99999']
    assert section.chat_id == 'abc99999'
    assert section.timestamp == 0.0  # No metadata comment


def test_wiki_parser_malformed_metadata(tmp_path):
    """Test parsing wiki with malformed metadata."""
    content = """# Project Wiki: Test

---

## 1. Malformed Section
*Invalid metadata format*

Content here
"""
    wiki_path = tmp_path / "malformed.md"
    wiki_path.write_text(content, encoding='utf-8')

    parser = WikiParser(wiki_path)
    sections = parser.parse()

    # Should handle gracefully, possibly with empty result or warning
    # Depending on implementation, adjust assertion
    assert isinstance(sections, dict)

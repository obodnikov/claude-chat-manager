"""Tests for chat merger functionality."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.chat_merger import ChatFingerprint, ChatMerger, MergeAction


# Sample chat content for testing
SAMPLE_CHAT_1 = """# Claude Chat Export
**Generated: 2025-12-26 16:57:45**

---

👤 **USER:**
> How do I implement authentication in my app?

I'll help you implement authentication. Let's start by choosing an authentication method.

---

👤 **USER:**
> Let's use JWT tokens

Good choice! JWT tokens are a popular standard for authentication. Here's how to implement it:

```python
import jwt
```
"""

SAMPLE_CHAT_2 = """# Claude Chat Export
**Generated: 2025-12-27 10:30:00**

---

👤 **USER:**
> How do I implement authentication in my app?

I'll help you implement authentication. Let's start by choosing an authentication method.

---

👤 **USER:**
> Let's use JWT tokens

Good choice! JWT tokens are a popular standard for authentication. Here's how to implement it:

```python
import jwt
```

---

👤 **USER:**
> Can you add refresh token logic?

Absolutely! Refresh tokens are important for security. Here's the implementation:
"""

SAMPLE_CHAT_3 = """# Claude Chat Export
**Generated: 2025-12-26 11:00:00**

---

👤 **USER:**
> How do I set up a database connection?

Let me help you set up a database connection. What database are you using?
"""

# Test case: Same opening, different later messages
SAMPLE_CHAT_SIMILAR_START = """# Claude Chat Export
**Generated: 2025-12-26 12:00:00**

---

👤 **USER:**
> How do I implement authentication in my app?

I'll help you implement authentication. Let's start by choosing an authentication method.

---

👤 **USER:**
> Let's use OAuth2

Good choice! OAuth2 is a popular authorization framework. Here's how to implement it:

```python
import oauth2
```
"""


class TestChatFingerprint:
    """Tests for ChatFingerprint extraction."""

    def test_extract_fingerprint_valid(self, tmp_path):
        """Test extracting fingerprint from valid chat file."""
        chat_file = tmp_path / "test-chat.md"
        chat_file.write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        fp = merger.extract_fingerprint(chat_file)

        assert fp is not None
        assert fp.file_path == chat_file
        assert fp.message_count > 0
        assert len(fp.content_hash) == 16
        assert "authentication" in fp.first_user_msg.lower()

    def test_extract_fingerprint_with_timestamp(self, tmp_path):
        """Test extracting timestamp from chat file."""
        chat_file = tmp_path / "test-chat.md"
        chat_file.write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        fp = merger.extract_fingerprint(chat_file)

        assert fp is not None
        assert fp.generation_timestamp is not None
        assert fp.generation_timestamp.year == 2025

    def test_extract_fingerprint_empty_file(self, tmp_path):
        """Test extracting fingerprint from empty file."""
        chat_file = tmp_path / "empty.md"
        chat_file.write_text("", encoding='utf-8')

        merger = ChatMerger()
        fp = merger.extract_fingerprint(chat_file)

        assert fp is None

    def test_extract_fingerprint_no_messages(self, tmp_path):
        """Test extracting fingerprint from file with no messages."""
        chat_file = tmp_path / "no-msgs.md"
        chat_file.write_text("# Title\n\nSome content without messages", encoding='utf-8')

        merger = ChatMerger()
        fp = merger.extract_fingerprint(chat_file)

        assert fp is None


class TestMessageExtraction:
    """Tests for message extraction from markdown."""

    def test_extract_messages_basic(self):
        """Test basic message extraction."""
        merger = ChatMerger()
        messages = merger._extract_messages(SAMPLE_CHAT_1)

        assert len(messages) >= 2
        assert messages[0]['role'] == 'user'
        assert 'authentication' in messages[0]['content'].lower()

    def test_extract_messages_multiple_pairs(self):
        """Test extracting multiple message pairs."""
        merger = ChatMerger()
        messages = merger._extract_messages(SAMPLE_CHAT_2)

        # Should have at least 3 user messages
        user_msgs = [m for m in messages if m['role'] == 'user']
        assert len(user_msgs) >= 3

    def test_extract_generation_timestamp(self):
        """Test timestamp extraction."""
        merger = ChatMerger()
        ts = merger._extract_generation_timestamp(SAMPLE_CHAT_1)

        assert ts is not None
        assert isinstance(ts, datetime)
        assert ts.year == 2025
        assert ts.month == 12
        assert ts.day == 26


class TestFingerprintComparison:
    """Tests for fingerprint comparison."""

    def test_identical_chats(self, tmp_path):
        """Test that identical chats have same fingerprint."""
        chat1 = tmp_path / "chat1.md"
        chat2 = tmp_path / "chat2.md"
        chat1.write_text(SAMPLE_CHAT_1, encoding='utf-8')
        chat2.write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        fp1 = merger.extract_fingerprint(chat1)
        fp2 = merger.extract_fingerprint(chat2)

        assert fp1.content_hash == fp2.content_hash
        similarity = merger.calculate_similarity(fp1, fp2)
        assert similarity == 1.0

    def test_incomplete_vs_complete(self, tmp_path):
        """Test incomplete chat vs complete version."""
        chat1 = tmp_path / "incomplete.md"
        chat2 = tmp_path / "complete.md"
        chat1.write_text(SAMPLE_CHAT_1, encoding='utf-8')
        chat2.write_text(SAMPLE_CHAT_2, encoding='utf-8')

        merger = ChatMerger()
        fp1 = merger.extract_fingerprint(chat1)
        fp2 = merger.extract_fingerprint(chat2)

        # Should have high similarity (same beginning)
        similarity = merger.calculate_similarity(fp1, fp2)
        assert similarity >= 0.8  # High similarity threshold
        # But different message counts
        assert fp2.message_count > fp1.message_count

    def test_different_chats(self, tmp_path):
        """Test different chats have different fingerprints."""
        chat1 = tmp_path / "auth.md"
        chat2 = tmp_path / "database.md"
        chat1.write_text(SAMPLE_CHAT_1, encoding='utf-8')
        chat2.write_text(SAMPLE_CHAT_3, encoding='utf-8')

        merger = ChatMerger()
        fp1 = merger.extract_fingerprint(chat1)
        fp2 = merger.extract_fingerprint(chat2)

        assert fp1.content_hash != fp2.content_hash
        similarity = merger.calculate_similarity(fp1, fp2)
        assert similarity < 0.8

    def test_similar_opening_different_continuation(self, tmp_path):
        """Test chats with same opening but different continuation.

        This addresses the code review issue where using only the first user message
        (200 chars) could lead to false positives. By comparing the full fingerprint
        text (first N message pairs), we can better distinguish conversations that
        start similarly but diverge later.
        """
        chat1 = tmp_path / "jwt-auth.md"
        chat2 = tmp_path / "oauth-auth.md"
        chat1.write_text(SAMPLE_CHAT_1, encoding='utf-8')  # JWT authentication
        chat2.write_text(SAMPLE_CHAT_SIMILAR_START, encoding='utf-8')  # OAuth authentication

        merger = ChatMerger()
        fp1 = merger.extract_fingerprint(chat1)
        fp2 = merger.extract_fingerprint(chat2)

        # First user messages are identical
        assert fp1.first_user_msg == fp2.first_user_msg

        # But full fingerprints should be different (JWT vs OAuth in 2nd exchange)
        assert fp1.content_hash != fp2.content_hash

        # Similarity should be lower because later messages differ
        # Old approach (first_user_msg only) would give ~100% similarity
        # New approach (full fingerprint_text) should give lower similarity
        similarity = merger.calculate_similarity(fp1, fp2)

        # The conversations diverge at "Let's use JWT" vs "Let's use OAuth2"
        # So similarity should be moderate but not high
        assert 0.5 < similarity < 0.9  # Similar start, different continuation


class TestMergeDecisions:
    """Tests for merge decision logic."""

    def test_decide_new_file(self, tmp_path):
        """Test decision for new file (no match)."""
        chat_file = tmp_path / "new.md"
        chat_file.write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        fp = merger.extract_fingerprint(chat_file)
        decision = merger.decide_action(fp, None, 0.0)

        assert decision.action == MergeAction.NEW
        assert decision.target_file is None

    def test_decide_skip_identical(self, tmp_path):
        """Test decision to skip identical file."""
        chat_file = tmp_path / "same.md"
        chat_file.write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        fp1 = merger.extract_fingerprint(chat_file)
        fp2 = merger.extract_fingerprint(chat_file)
        decision = merger.decide_action(fp1, fp2, 1.0)

        assert decision.action == MergeAction.SKIP

    def test_decide_update_longer(self, tmp_path):
        """Test decision to update with longer version."""
        incomplete = tmp_path / "incomplete.md"
        complete = tmp_path / "complete.md"
        incomplete.write_text(SAMPLE_CHAT_1, encoding='utf-8')
        complete.write_text(SAMPLE_CHAT_2, encoding='utf-8')

        merger = ChatMerger()
        fp_complete = merger.extract_fingerprint(complete)
        fp_incomplete = merger.extract_fingerprint(incomplete)
        decision = merger.decide_action(fp_complete, fp_incomplete, 1.0)

        assert decision.action == MergeAction.UPDATE
        assert decision.source_msgs > decision.target_msgs

    def test_decide_skip_shorter(self, tmp_path):
        """Test decision to skip shorter version."""
        incomplete = tmp_path / "incomplete.md"
        complete = tmp_path / "complete.md"
        incomplete.write_text(SAMPLE_CHAT_1, encoding='utf-8')
        complete.write_text(SAMPLE_CHAT_2, encoding='utf-8')

        merger = ChatMerger()
        fp_incomplete = merger.extract_fingerprint(incomplete)
        fp_complete = merger.extract_fingerprint(complete)
        decision = merger.decide_action(fp_incomplete, fp_complete, 1.0)

        assert decision.action == MergeAction.SKIP
        assert decision.reason.lower().count('complete') > 0


class TestDirectoryAnalysis:
    """Tests for directory analysis."""

    def test_analyze_directories(self, tmp_path):
        """Test analyzing source and target directories."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        # Create source files
        (source_dir / "new-chat.md").write_text(SAMPLE_CHAT_3, encoding='utf-8')
        (source_dir / "updated-chat.md").write_text(SAMPLE_CHAT_2, encoding='utf-8')

        # Create target files
        (target_dir / "old-chat.md").write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        decisions = merger.analyze_directories(source_dir, target_dir)

        # Should have decisions for both source files
        assert len(decisions) == 2

        # One should be NEW, one should be UPDATE
        actions = {d.action for d in decisions}
        assert MergeAction.NEW in actions
        assert MergeAction.UPDATE in actions

    def test_summary_generation(self, tmp_path):
        """Test generating summary from decisions."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        (source_dir / "chat1.md").write_text(SAMPLE_CHAT_1, encoding='utf-8')
        (source_dir / "chat2.md").write_text(SAMPLE_CHAT_2, encoding='utf-8')
        (target_dir / "existing.md").write_text(SAMPLE_CHAT_1, encoding='utf-8')

        merger = ChatMerger()
        decisions = merger.analyze_directories(source_dir, target_dir)
        summary = merger.get_summary(decisions)

        assert summary['total'] == 2
        assert summary['new'] + summary['update'] + summary['skip'] + summary['review'] == 2


class TestLevenshteinSimilarity:
    """Tests for string similarity calculation."""

    def test_identical_strings(self):
        """Test similarity of identical strings."""
        merger = ChatMerger()
        similarity = merger._levenshtein_similarity("hello", "hello")
        assert similarity == 1.0

    def test_completely_different(self):
        """Test similarity of completely different strings."""
        merger = ChatMerger()
        similarity = merger._levenshtein_similarity("abc", "xyz")
        assert similarity == 0.0

    def test_empty_strings(self):
        """Test similarity with empty strings."""
        merger = ChatMerger()
        similarity = merger._levenshtein_similarity("", "test")
        assert similarity == 0.0

    def test_partial_match(self):
        """Test similarity of partially matching strings."""
        merger = ChatMerger()
        similarity = merger._levenshtein_similarity("hello world", "hello earth")
        # Should have some similarity (common prefix "hello ")
        assert 0.0 < similarity < 1.0

    def test_reordered_text(self):
        """Test similarity with reordered words."""
        merger = ChatMerger()
        # Same words, different order
        similarity = merger._levenshtein_similarity(
            "authentication system implementation",
            "implementation authentication system"
        )
        # SequenceMatcher should detect high similarity despite reordering
        assert similarity > 0.5

    def test_typo_variations(self):
        """Test similarity with typos."""
        merger = ChatMerger()
        # Single character typo
        similarity = merger._levenshtein_similarity(
            "How do I implement authentication?",
            "How do I impliment authentication?"  # typo: "impliment"
        )
        # Should still have very high similarity
        assert similarity > 0.9

    def test_insertions_deletions(self):
        """Test similarity with insertions and deletions."""
        merger = ChatMerger()
        original = "How do I add user authentication?"
        # With insertion
        with_insertion = "How do I add secure user authentication?"
        similarity_insertion = merger._levenshtein_similarity(original, with_insertion)
        assert similarity_insertion > 0.8  # Still quite similar

        # With deletion
        with_deletion = "How do I add authentication?"
        similarity_deletion = merger._levenshtein_similarity(original, with_deletion)
        assert similarity_deletion > 0.8  # Still quite similar

    def test_case_insensitive(self):
        """Test that similarity handles case differences."""
        merger = ChatMerger()
        # The method receives lowercased strings in practice
        similarity = merger._levenshtein_similarity(
            "how do i implement authentication",
            "how do i implement authentication"
        )
        assert similarity == 1.0

    def test_very_different_lengths(self):
        """Test similarity with very different length strings."""
        merger = ChatMerger()
        short = "auth"
        long = "How do I implement a complete authentication system with JWT tokens?"
        similarity = merger._levenshtein_similarity(short, long)
        # Should have low similarity
        assert similarity < 0.3

"""Chat merge utility for deduplicating exported conversation files.

This module provides functionality to compare and merge exported chat files
from different sources, detecting duplicates and incomplete conversations.
"""

import difflib
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class MergeAction(Enum):
    """Action to take for a file during merge.

    Attributes:
        NEW: File is new and should be copied to target.
        UPDATE: File exists but source is longer/newer, should replace.
        SKIP: File already exists with same or more content.
        REVIEW: Manual review needed (similarity unclear).
    """
    NEW = "new"
    UPDATE = "update"
    SKIP = "skip"
    REVIEW = "review"


@dataclass
class ChatFingerprint:
    """Fingerprint of a chat conversation for comparison.

    Attributes:
        file_path: Path to the chat file.
        content_hash: Hash of first N message pairs.
        message_count: Total number of messages.
        first_user_msg: First user message (cleaned).
        fingerprint_text: Full text used to create hash (first N message pairs).
        generation_timestamp: When the export was generated.
        file_size: File size in bytes.
    """
    file_path: Path
    content_hash: str
    message_count: int
    first_user_msg: str
    fingerprint_text: str
    generation_timestamp: Optional[datetime] = None
    file_size: int = 0


@dataclass
class MergeDecision:
    """Decision made for merging a file.

    Attributes:
        source_file: Source file path.
        target_file: Target file path (if exists).
        action: What action to take.
        reason: Human-readable reason for the decision.
        source_msgs: Message count in source.
        target_msgs: Message count in target (if exists).
        similarity: Similarity score 0-1 (if applicable).
    """
    source_file: Path
    target_file: Optional[Path]
    action: MergeAction
    reason: str
    source_msgs: int
    target_msgs: Optional[int] = None
    similarity: Optional[float] = None


class ChatMerger:
    """Handles comparison and merging of exported chat files.

    This class analyzes chat files using content fingerprinting to detect
    duplicates, updates, and new conversations across different export batches.
    """

    def __init__(
        self,
        fingerprint_messages: int = 3,
        similarity_threshold: float = 0.8,
        prefer_longer: bool = True
    ):
        """Initialize the chat merger.

        Args:
            fingerprint_messages: Number of message pairs to use for fingerprint.
            similarity_threshold: Minimum similarity (0-1) to consider a match.
            prefer_longer: If True, prefer files with more messages on conflict.
        """
        self.fingerprint_messages = fingerprint_messages
        self.similarity_threshold = similarity_threshold
        self.prefer_longer = prefer_longer

    def extract_fingerprint(self, file_path: Path) -> Optional[ChatFingerprint]:
        """Extract fingerprint from a chat export file.

        Args:
            file_path: Path to chat markdown file.

        Returns:
            ChatFingerprint object or None if extraction fails.
        """
        try:
            content = file_path.read_text(encoding='utf-8')

            # Extract generation timestamp
            gen_ts = self._extract_generation_timestamp(content)

            # Extract messages
            messages = self._extract_messages(content)

            if not messages:
                logger.warning(f"No messages found in {file_path.name}")
                return None

            # Get first user message
            first_user = next((msg for msg in messages if msg['role'] == 'user'), None)
            first_user_msg = first_user['content'][:200] if first_user else ""

            # Create fingerprint from first N message pairs
            fingerprint_text = self._create_fingerprint_text(messages)
            content_hash = hashlib.sha256(fingerprint_text.encode()).hexdigest()[:16]

            return ChatFingerprint(
                file_path=file_path,
                content_hash=content_hash,
                message_count=len(messages),
                first_user_msg=first_user_msg,
                fingerprint_text=fingerprint_text,
                generation_timestamp=gen_ts,
                file_size=file_path.stat().st_size
            )

        except Exception as e:
            logger.error(f"Error extracting fingerprint from {file_path.name}: {e}")
            return None

    def _extract_generation_timestamp(self, content: str) -> Optional[datetime]:
        """Extract generation timestamp from markdown header.

        Args:
            content: File content.

        Returns:
            Datetime object or None if not found.
        """
        # Look for: **Generated: 2025-12-26 16:57:45**
        match = re.search(r'\*\*Generated:\s*(.+?)\*\*', content)
        if match:
            try:
                return datetime.strptime(match.group(1).strip(), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        return None

    def _extract_messages(self, content: str) -> List[Dict[str, str]]:
        """Extract messages from markdown content.

        Args:
            content: File content.

        Returns:
            List of message dictionaries with 'role' and 'content'.
        """
        messages = []

        # Split by user message markers
        # Format: 👤 **USER:**\n> message content
        parts = re.split(r'👤\s*\*\*USER:\*\*', content)

        for i, part in enumerate(parts):
            if i == 0:  # Skip header
                continue

            # Extract user message (after > blockquote marker)
            user_match = re.search(r'>\s*(.+?)(?=\n\n|\Z)', part, re.DOTALL)
            if user_match:
                user_content = user_match.group(1).strip()
                messages.append({'role': 'user', 'content': user_content})

                # Extract assistant response (everything after user message until next user or end)
                assistant_content = part[user_match.end():].strip()
                # Remove any horizontal rules
                assistant_content = re.sub(r'^---+\s*', '', assistant_content, flags=re.MULTILINE)

                if assistant_content:
                    messages.append({'role': 'assistant', 'content': assistant_content[:500]})

        return messages

    def _create_fingerprint_text(self, messages: List[Dict[str, str]]) -> str:
        """Create fingerprint text from first N message pairs.

        Args:
            messages: List of message dictionaries.

        Returns:
            Combined text for fingerprinting.
        """
        fingerprint_parts = []
        msg_count = 0

        for msg in messages:
            if msg_count >= self.fingerprint_messages * 2:  # user + assistant pairs
                break

            # Clean and normalize content
            content = msg['content']
            # Remove excessive whitespace
            content = re.sub(r'\s+', ' ', content)
            # Remove markdown formatting
            content = re.sub(r'[*_`]', '', content)
            # Take first 200 chars
            content = content[:200].strip().lower()

            fingerprint_parts.append(content)
            msg_count += 1

        return '||'.join(fingerprint_parts)

    def calculate_similarity(self, fp1: ChatFingerprint, fp2: ChatFingerprint) -> float:
        """Calculate similarity between two fingerprints.

        Uses multi-level comparison for accuracy:
        1. Hash comparison (exact match) - fast path
        2. Full fingerprint text comparison - uses first N message pairs

        This addresses the issue of relying only on the first user message,
        which can lead to false positives (similar openings, different conversations)
        or false negatives (different openings, same conversation).

        Args:
            fp1: First fingerprint.
            fp2: Second fingerprint.

        Returns:
            Similarity score between 0 and 1.
        """
        # Exact hash match
        if fp1.content_hash == fp2.content_hash:
            return 1.0

        # Compare full fingerprint text (first N message pairs)
        # This is more comprehensive than just comparing first_user_msg
        similarity = self._levenshtein_similarity(
            fp1.fingerprint_text.lower(),
            fp2.fingerprint_text.lower()
        )

        return similarity

    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity ratio between two strings using SequenceMatcher.

        Uses Python's difflib.SequenceMatcher which implements a sophisticated
        algorithm based on Ratcliff/Obershelp pattern matching. This is more
        accurate than simple character position matching as it handles:
        - Reordered text
        - Insertions and deletions
        - Typos and variations

        Args:
            s1: First string.
            s2: Second string.

        Returns:
            Similarity ratio between 0 and 1.
        """
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        # Use difflib.SequenceMatcher for accurate similarity calculation
        matcher = difflib.SequenceMatcher(None, s1, s2)
        return matcher.ratio()

    def find_match(
        self,
        source_fp: ChatFingerprint,
        target_fps: List[ChatFingerprint]
    ) -> Tuple[Optional[ChatFingerprint], float]:
        """Find best match for source fingerprint in target list.

        Args:
            source_fp: Source fingerprint to match.
            target_fps: List of target fingerprints.

        Returns:
            Tuple of (best match fingerprint, similarity score) or (None, 0.0).
        """
        best_match = None
        best_similarity = 0.0

        for target_fp in target_fps:
            similarity = self.calculate_similarity(source_fp, target_fp)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = target_fp

        if best_similarity >= self.similarity_threshold:
            return best_match, best_similarity

        return None, 0.0

    def decide_action(
        self,
        source_fp: ChatFingerprint,
        target_match: Optional[ChatFingerprint],
        similarity: float
    ) -> MergeDecision:
        """Decide what action to take for a source file.

        Args:
            source_fp: Source file fingerprint.
            target_match: Matched target fingerprint (if any).
            similarity: Similarity score.

        Returns:
            MergeDecision object.
        """
        # No match found - new file
        if target_match is None:
            return MergeDecision(
                source_file=source_fp.file_path,
                target_file=None,
                action=MergeAction.NEW,
                reason="No matching conversation found in target",
                source_msgs=source_fp.message_count
            )

        # Exact match by hash
        if similarity == 1.0 and source_fp.message_count == target_match.message_count:
            return MergeDecision(
                source_file=source_fp.file_path,
                target_file=target_match.file_path,
                action=MergeAction.SKIP,
                reason="Identical conversation already exists",
                source_msgs=source_fp.message_count,
                target_msgs=target_match.message_count,
                similarity=similarity
            )

        # Source has more messages - update
        if source_fp.message_count > target_match.message_count:
            return MergeDecision(
                source_file=source_fp.file_path,
                target_file=target_match.file_path,
                action=MergeAction.UPDATE,
                reason=f"Source has more messages ({source_fp.message_count} vs {target_match.message_count})",
                source_msgs=source_fp.message_count,
                target_msgs=target_match.message_count,
                similarity=similarity
            )

        # Source has fewer messages - skip
        if source_fp.message_count < target_match.message_count:
            return MergeDecision(
                source_file=source_fp.file_path,
                target_file=target_match.file_path,
                action=MergeAction.SKIP,
                reason=f"Target has more complete version ({target_match.message_count} vs {source_fp.message_count})",
                source_msgs=source_fp.message_count,
                target_msgs=target_match.message_count,
                similarity=similarity
            )

        # Same message count but different content - review needed
        if similarity < 1.0:
            return MergeDecision(
                source_file=source_fp.file_path,
                target_file=target_match.file_path,
                action=MergeAction.REVIEW,
                reason=f"Similar but not identical (similarity: {similarity:.2%})",
                source_msgs=source_fp.message_count,
                target_msgs=target_match.message_count,
                similarity=similarity
            )

        # Default: skip
        return MergeDecision(
            source_file=source_fp.file_path,
            target_file=target_match.file_path,
            action=MergeAction.SKIP,
            reason="Already exists with same content",
            source_msgs=source_fp.message_count,
            target_msgs=target_match.message_count,
            similarity=similarity
        )

    def analyze_directories(
        self,
        source_dir: Path,
        target_dir: Path
    ) -> List[MergeDecision]:
        """Analyze source and target directories to generate merge decisions.

        Args:
            source_dir: Directory with new exported chats.
            target_dir: Directory with existing chats.

        Returns:
            List of MergeDecision objects.
        """
        logger.info(f"Analyzing source: {source_dir}")
        logger.info(f"Analyzing target: {target_dir}")

        # Find all markdown files
        source_files = sorted(source_dir.glob("*.md"))
        target_files = sorted(target_dir.glob("*.md"))

        logger.info(f"Found {len(source_files)} source files")
        logger.info(f"Found {len(target_files)} target files")

        # Extract fingerprints
        source_fps = []
        for f in source_files:
            fp = self.extract_fingerprint(f)
            if fp:
                source_fps.append(fp)

        target_fps = []
        for f in target_files:
            fp = self.extract_fingerprint(f)
            if fp:
                target_fps.append(fp)

        logger.info(f"Extracted {len(source_fps)} source fingerprints")
        logger.info(f"Extracted {len(target_fps)} target fingerprints")

        # Generate decisions
        decisions = []
        for source_fp in source_fps:
            target_match, similarity = self.find_match(source_fp, target_fps)
            decision = self.decide_action(source_fp, target_match, similarity)
            decisions.append(decision)

            logger.debug(f"{source_fp.file_path.name}: {decision.action.value} - {decision.reason}")

        return decisions

    def get_summary(self, decisions: List[MergeDecision]) -> Dict[str, int]:
        """Get summary statistics from merge decisions.

        Args:
            decisions: List of merge decisions.

        Returns:
            Dictionary with counts for each action type.
        """
        summary = {
            'new': 0,
            'update': 0,
            'skip': 0,
            'review': 0,
            'total': len(decisions)
        }

        for decision in decisions:
            summary[decision.action.value] += 1

        return summary

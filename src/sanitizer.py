"""Sensitive data sanitization for chat exports.

This module provides pattern-based detection and redaction of sensitive
information including API keys, tokens, passwords, and environment variables.
"""

import re
import hashlib
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SanitizationLevel(Enum):
    """Sanitization detection levels."""
    MINIMAL = 'minimal'
    BALANCED = 'balanced'
    AGGRESSIVE = 'aggressive'
    CUSTOM = 'custom'


class RedactionStyle(Enum):
    """Redaction replacement styles."""
    SIMPLE = 'simple'       # REDACTED
    STARS = 'stars'         # ***
    LABELED = 'labeled'     # [API_KEY]
    PARTIAL = 'partial'     # sk-ab***xyz
    HASH = 'hash'           # [a3f4d8c2]


@dataclass
class SanitizationMatch:
    """Represents a detected sensitive pattern.

    Attributes:
        pattern_type: Type of pattern matched (e.g., 'api_key', 'password_context').
        original_value: The matched sensitive text.
        redacted_value: The replacement text.
        position: Character position in text where match starts.
        line_number: Line number where match occurs (1-indexed).
        confidence: Detection confidence score (0.0-1.0).
    """
    pattern_type: str
    original_value: str
    redacted_value: str
    position: int
    line_number: int
    confidence: float = 1.0


@dataclass
class SanitizationReport:
    """Report of sanitization operations.

    Attributes:
        total_matches: Total number of matches found.
        by_category: Dictionary mapping pattern types to count.
        matches: List of all sanitization matches.
    """
    matches: List[SanitizationMatch]

    @property
    def total_matches(self) -> int:
        """Get total number of matches."""
        return len(self.matches)

    @property
    def by_category(self) -> Dict[str, int]:
        """Get match counts by category."""
        counts = {}
        for match in self.matches:
            counts[match.pattern_type] = counts.get(match.pattern_type, 0) + 1
        return counts

    def to_text(self) -> str:
        """Generate text report of sanitization.

        Returns:
            Formatted text report.
        """
        lines = []
        lines.append("=" * 60)
        lines.append("SANITIZATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Total matches: {self.total_matches}")
        lines.append("")

        if self.by_category:
            lines.append("By category:")
            for ptype, count in sorted(self.by_category.items()):
                lines.append(f"  - {count} {ptype.replace('_', ' ').title()}")
            lines.append("")

        if self.matches:
            lines.append("Detailed matches:")
            for i, match in enumerate(self.matches, 1):
                lines.append(f"\n{i}. {match.pattern_type.replace('_', ' ').title()}")
                lines.append(f"   Line: {match.line_number}")
                lines.append(f"   Original: {match.original_value}")
                lines.append(f"   Redacted: {match.redacted_value}")
                lines.append(f"   Confidence: {match.confidence:.0%}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


class Sanitizer:
    """Core sanitization engine for detecting and redacting sensitive data."""

    # Pattern library organized by priority
    PATTERNS = {
        'api_key': [
            r'sk-[a-zA-Z0-9]{20,}',                      # Generic Anthropic/OpenAI
            r'sk-proj-[a-zA-Z0-9_-]{20,}',               # OpenAI project keys
            r'sk-or-v1-[a-zA-Z0-9_-]{20,}',              # OpenRouter
            r'ghp_[a-zA-Z0-9]{36}',                      # GitHub personal token
            r'gho_[a-zA-Z0-9]{36}',                      # GitHub OAuth
            r'ghs_[a-zA-Z0-9]{36}',                      # GitHub server token
            r'ghr_[a-zA-Z0-9]{36}',                      # GitHub refresh token
            r'github_pat_[a-zA-Z0-9_]{22,}',             # GitHub fine-grained PAT
            r'AKIA[0-9A-Z]{16}',                         # AWS access key
            r'AIza[0-9A-Za-z_-]{35}',                    # Google API key
        ],
        'token': [
            r'Bearer\s+[A-Za-z0-9._-]{20,}',             # Bearer tokens
            r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*',  # JWT
            r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}', # Slack
        ],
        'password_context': [
            # Context-aware: "password = xyz", "pwd: abc", etc.
            r'(?i)password\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?',
            r'(?i)passwd\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?',
            r'(?i)pwd\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?',
            r'(?i)secret\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?',
        ],
        'env_var': [
            # Environment variable assignments with secrets
            r'(?i)(API_KEY|OPENROUTER_API_KEY|SECRET_KEY|AUTH_TOKEN|PASSWORD|TOKEN)\s*=\s*["\']?([^"\'\s]{8,})["\']?',
            r'export\s+([A-Z_]+)\s*=\s*["\']?([^"\'\s]{8,})["\']?',
        ],
    }

    # Default allowlist - patterns that should never be redacted
    DEFAULT_ALLOWLIST = [
        r'example\.com',
        r'localhost',
        r'127\.0\.0\.1',
        r'0\.0\.0\.0',
        r'sk-[x]{20,}',           # Placeholder keys (sk-xxxx...)
        r'xxx+',                   # Generic xxx placeholders
        r'\*\*\*+',                # Already redacted
        r'your-api-key-here',
        r'insert-key-here',
        r'replace-with-',
        r'add-your-',
    ]

    def __init__(
        self,
        enabled: bool = False,
        level: str = 'balanced',
        style: str = 'partial',
        sanitize_paths: bool = False,
        custom_patterns: Optional[List[str]] = None,
        allowlist: Optional[List[str]] = None
    ) -> None:
        """Initialize sanitizer with configuration.

        Args:
            enabled: Whether sanitization is enabled.
            level: Detection level ('minimal', 'balanced', 'aggressive', 'custom').
            style: Redaction style ('simple', 'stars', 'labeled', 'partial', 'hash').
            sanitize_paths: Whether to sanitize file paths.
            custom_patterns: Additional regex patterns to detect.
            allowlist: Regex patterns to exclude from sanitization.
        """
        self.enabled = enabled
        self.level = SanitizationLevel(level)
        self.style = RedactionStyle(style)
        self.sanitize_paths = sanitize_paths
        self.custom_patterns = custom_patterns or []
        self.allowlist_patterns = self.DEFAULT_ALLOWLIST + (allowlist or [])

        # Compile patterns for performance
        self._compiled_patterns = self._compile_patterns()
        self._compiled_allowlist = self._compile_allowlist()

        logger.debug(
            f"Sanitizer initialized: enabled={enabled}, level={level}, style={style}"
        )

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns based on level.

        Returns:
            Dictionary mapping pattern types to compiled regex objects.
        """
        compiled = {}

        if self.level == SanitizationLevel.CUSTOM:
            # Only use custom patterns
            if self.custom_patterns:
                compiled['custom'] = self._compile_pattern_list(self.custom_patterns, 'custom')
        else:
            # Use built-in patterns based on level
            patterns_to_use = self._select_patterns_by_level()

            for pattern_type, pattern_list in patterns_to_use.items():
                compiled[pattern_type] = self._compile_pattern_list(pattern_list, pattern_type)

            # Add custom patterns to all levels except custom
            if self.custom_patterns:
                compiled['custom'] = self._compile_pattern_list(self.custom_patterns, 'custom')

        return compiled

    def _compile_pattern_list(self, patterns: List[str], pattern_type: str) -> List[re.Pattern]:
        """Compile a list of regex patterns with error handling.

        Args:
            patterns: List of regex pattern strings.
            pattern_type: Type of pattern for logging.

        Returns:
            List of successfully compiled regex Pattern objects.
        """
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern))
            except re.error as e:
                logger.warning(
                    f"Invalid regex pattern for {pattern_type}: '{pattern}' - {e}. Skipping."
                )
        return compiled

    def _select_patterns_by_level(self) -> Dict[str, List[str]]:
        """Select patterns based on sanitization level.

        Returns:
            Dictionary of pattern types to pattern strings.
        """
        patterns = {}

        if self.level == SanitizationLevel.MINIMAL:
            # Only obvious API keys
            patterns['api_key'] = self.PATTERNS['api_key']

        elif self.level == SanitizationLevel.BALANCED:
            # All priority patterns
            patterns['api_key'] = self.PATTERNS['api_key']
            patterns['token'] = self.PATTERNS['token']
            patterns['password_context'] = self.PATTERNS['password_context']
            patterns['env_var'] = self.PATTERNS['env_var']

        elif self.level == SanitizationLevel.AGGRESSIVE:
            # All patterns plus additional aggressive ones
            patterns['api_key'] = self.PATTERNS['api_key']
            patterns['token'] = self.PATTERNS['token']
            patterns['password_context'] = self.PATTERNS['password_context']
            patterns['env_var'] = self.PATTERNS['env_var']
            # Could add more aggressive patterns here in the future

        return patterns

    def _compile_allowlist(self) -> List[re.Pattern]:
        """Compile allowlist patterns with error handling.

        Returns:
            List of compiled regex patterns.
        """
        return self._compile_pattern_list(self.allowlist_patterns, 'allowlist')

    def _is_allowlisted(self, value: str) -> bool:
        """Check if value matches allowlist patterns.

        Args:
            value: Text to check against allowlist.

        Returns:
            True if value should not be redacted.
        """
        for pattern in self._compiled_allowlist:
            if pattern.search(value):
                logger.debug(f"Value allowlisted: {value[:20]}...")
                return True
        return False

    def _apply_redaction(self, value: str, pattern_type: str) -> str:
        """Apply redaction based on configured style.

        Args:
            value: Original sensitive value.
            pattern_type: Type of pattern matched.

        Returns:
            Redacted replacement string.
        """
        if self.style == RedactionStyle.SIMPLE:
            return 'REDACTED'

        elif self.style == RedactionStyle.STARS:
            return '*' * min(len(value), 10)

        elif self.style == RedactionStyle.LABELED:
            labels = {
                'api_key': '[API_KEY]',
                'token': '[TOKEN]',
                'password_context': '[PASSWORD]',
                'env_var': '[SECRET]',
                'custom': '[REDACTED]',
            }
            return labels.get(pattern_type, '[REDACTED]')

        elif self.style == RedactionStyle.PARTIAL:
            # Keep first 5 and last 3 chars
            if len(value) <= 10:
                return '*' * len(value)
            return f"{value[:5]}***{value[-3:]}"

        elif self.style == RedactionStyle.HASH:
            # Consistent hash for same value
            hash_obj = hashlib.sha256(value.encode())
            return f"[{hash_obj.hexdigest()[:8]}]"

        return 'REDACTED'

    def _get_line_number(self, text: str, position: int) -> int:
        """Get line number for a character position.

        Args:
            text: Full text content.
            position: Character position.

        Returns:
            Line number (1-indexed).
        """
        return text[:position].count('\n') + 1

    def preview_sanitization(self, text: str) -> List[SanitizationMatch]:
        """Preview what would be sanitized without applying changes.

        Args:
            text: Text to analyze.

        Returns:
            List of matches that would be redacted.
        """
        if not self.enabled:
            return []

        matches = []
        seen_positions = set()  # Track positions to avoid duplicates

        # Search for each pattern type
        for pattern_type, compiled_list in self._compiled_patterns.items():
            for pattern in compiled_list:
                for match in pattern.finditer(text):
                    # Extract the matched value and position
                    if match.groups():
                        # For patterns with capture groups, use last group
                        value = match.group(match.lastindex)
                        # Find the position of the captured group value
                        value_start = match.start(match.lastindex)
                    else:
                        # For patterns without groups, use entire match
                        value = match.group(0)
                        value_start = match.start()

                    # Skip if we've already matched this position
                    if value_start in seen_positions:
                        continue

                    # Check allowlist
                    if self._is_allowlisted(value):
                        continue

                    # Mark position as seen
                    seen_positions.add(value_start)

                    # Create match record
                    redacted = self._apply_redaction(value, pattern_type)
                    line_num = self._get_line_number(text, value_start)

                    matches.append(SanitizationMatch(
                        pattern_type=pattern_type,
                        original_value=value,
                        redacted_value=redacted,
                        position=value_start,
                        line_number=line_num,
                        confidence=1.0
                    ))

        # Sort by position
        matches.sort(key=lambda m: m.position)

        logger.info(f"Preview found {len(matches)} potential secrets")
        return matches

    def sanitize_text(
        self,
        text: str,
        track_changes: bool = False,
        approved_matches: Optional[List[SanitizationMatch]] = None
    ) -> Tuple[str, Optional[List[SanitizationMatch]]]:
        """Sanitize text content by redacting sensitive patterns.

        Args:
            text: Text to sanitize.
            track_changes: Whether to track what was changed.
            approved_matches: If provided, only apply these specific matches.

        Returns:
            Tuple of (sanitized_text, matches_applied).
            If track_changes is False, matches_applied will be None.
        """
        if not self.enabled:
            return text, [] if track_changes else None

        # Get all matches
        if approved_matches is not None:
            # Use pre-approved matches
            matches = approved_matches
        else:
            # Find all matches
            matches = self.preview_sanitization(text)

        if not matches:
            return text, [] if track_changes else None

        # Apply redactions in reverse order to preserve positions
        sanitized = text
        matches_sorted = sorted(matches, key=lambda m: m.position, reverse=True)

        for match in matches_sorted:
            # Find the actual position of the original value in text
            # (it might be part of a larger match)
            start_pos = sanitized.find(match.original_value, max(0, match.position - 50))
            if start_pos == -1:
                logger.warning(f"Could not find match to redact: {match.original_value[:20]}")
                continue

            end_pos = start_pos + len(match.original_value)
            sanitized = sanitized[:start_pos] + match.redacted_value + sanitized[end_pos:]

        logger.info(f"Sanitized {len(matches)} sensitive values")

        return sanitized, matches if track_changes else None

    def sanitize_chat_data(
        self,
        chat_data: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], SanitizationReport]:
        """Sanitize entire chat data structure.

        Args:
            chat_data: List of chat message dictionaries.

        Returns:
            Tuple of (sanitized_chat_data, report).
        """
        if not self.enabled:
            return chat_data, SanitizationReport(matches=[])

        all_matches = []
        sanitized_data = []

        for entry in chat_data:
            sanitized_entry = entry.copy()

            # Sanitize message content
            if 'message' in entry and 'content' in entry['message']:
                content = entry['message']['content']

                if isinstance(content, str):
                    sanitized_content, matches = self.sanitize_text(
                        content,
                        track_changes=True
                    )
                    sanitized_entry['message'] = entry['message'].copy()
                    sanitized_entry['message']['content'] = sanitized_content

                    if matches:
                        all_matches.extend(matches)

                elif isinstance(content, list):
                    # Handle structured content (list of dicts)
                    sanitized_content_list = []
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text = item.get('text', '')
                            sanitized_text, matches = self.sanitize_text(
                                text,
                                track_changes=True
                            )
                            item_copy = item.copy()
                            item_copy['text'] = sanitized_text
                            sanitized_content_list.append(item_copy)

                            if matches:
                                all_matches.extend(matches)
                        else:
                            sanitized_content_list.append(item)

                    sanitized_entry['message'] = entry['message'].copy()
                    sanitized_entry['message']['content'] = sanitized_content_list

            sanitized_data.append(sanitized_entry)

        report = SanitizationReport(matches=all_matches)
        logger.info(f"Sanitized chat data: {report.total_matches} total matches")

        return sanitized_data, report

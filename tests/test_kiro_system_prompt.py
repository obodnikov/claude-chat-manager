"""Tests for Kiro system prompt detection and stripping.

Covers the shared utility in src/kiro_system_prompt.py and its integration
with both kiro_parser.py and filters.py.
"""

import pytest

from src.kiro_system_prompt import (
    has_kiro_system_prompt,
    strip_kiro_system_prompt,
    KIRO_SYSTEM_TAGS,
    MIN_SIGNATURE_TAGS,
)
from src.filters import ChatFilter
from src.kiro_parser import extract_messages_from_execution_log


# ---------------------------------------------------------------------------
# Fixtures: realistic Kiro system prompt content
# ---------------------------------------------------------------------------

FULL_KIRO_PROMPT = (
    "<key_kiro_features>\n"
    "<autonomy_modes>\n- Autopilot mode allows Kiro modify files.\n</autonomy_modes>\n"
    "<chat_context>\n- Tell Kiro to use #File or #Folder.\n</chat_context>\n"
    "</key_kiro_features>\n\n"
    "<system_information>\nOperating System: macOS\nPlatform: darwin\n</system_information>\n\n"
    "<current_date_and_time>\nDate: April 10, 2026\n</current_date_and_time>\n\n"
    "<model_information>\nName: Claude Opus 4.6\n</model_information>\n\n"
    "<goal>\n- Execute the user goal.\n</goal>\n\n"
    "<subagents>\n- You have access to sub-agents.\n</subagents>\n\n"
    "<current_context>\nMachine ID: abc123\n</current_context>\n\n"
    "I will follow these instructions.\n\n"
)

USER_QUESTION = "find to me all JIRA epics where I am assignee"


class TestHasKiroSystemPrompt:
    """Tests for signature detection."""

    def test_full_prompt_detected(self):
        """Full Kiro system prompt is detected."""
        assert has_kiro_system_prompt(FULL_KIRO_PROMPT) is True

    def test_two_signature_tags_detected(self):
        """Two signature tags are enough to trigger detection."""
        text = "<system_information>OS: macOS</system_information>\n<current_context>id</current_context>"
        assert has_kiro_system_prompt(text) is True

    def test_single_tag_not_detected(self):
        """A single tag is NOT enough — avoids false positives."""
        text = "<system_information>OS: macOS</system_information>\nSome user text"
        assert has_kiro_system_prompt(text) is False

    def test_no_tags_not_detected(self):
        """Plain user text is not detected."""
        assert has_kiro_system_prompt("How do I use Python?") is False

    def test_legitimate_xml_not_detected(self):
        """User content with XML-like tags that aren't Kiro tags."""
        text = "<goal>My personal goal is to learn Rust</goal>\nHow do I start?"
        # Only 1 match (goal is not in _SIGNATURE_TAGS), so not detected
        assert has_kiro_system_prompt(text) is False

    def test_variant_without_key_kiro_features(self):
        """Prompt variant that omits key_kiro_features but has other tags."""
        text = (
            "<system_information>OS: Linux</system_information>\n"
            "<current_date_and_time>Date: 2026-04-14</current_date_and_time>\n"
            "<model_information>Claude</model_information>\n"
            "What is Python?"
        )
        assert has_kiro_system_prompt(text) is True


class TestStripKiroSystemPrompt:
    """Tests for the stripping function."""

    def test_pure_prompt_returns_empty(self):
        """A message that is purely system prompt returns empty string."""
        result = strip_kiro_system_prompt(FULL_KIRO_PROMPT)
        assert result == ""

    def test_prompt_plus_user_text_preserves_user_text(self):
        """System prompt + user question → only user question remains."""
        text = FULL_KIRO_PROMPT + USER_QUESTION
        result = strip_kiro_system_prompt(text)
        assert result == USER_QUESTION

    def test_legitimate_user_xml_unchanged(self):
        """User content with a single generic XML tag is NOT stripped."""
        text = "Please parse this: <rules>my custom rules</rules>"
        result = strip_kiro_system_prompt(text)
        # No signature detected → text returned unchanged
        assert result == text

    def test_no_signature_returns_original(self):
        """Text without Kiro signature is returned unchanged."""
        text = "Just a normal question about Python"
        result = strip_kiro_system_prompt(text)
        assert result == text

    def test_ack_line_stripped(self):
        """The 'I will follow these instructions.' line is stripped."""
        text = FULL_KIRO_PROMPT + "I will follow these instructions.\n\n" + USER_QUESTION
        result = strip_kiro_system_prompt(text)
        assert "I will follow these instructions" not in result
        assert USER_QUESTION in result

    def test_variant_without_key_kiro_features(self):
        """Prompt variant without key_kiro_features is still stripped."""
        text = (
            "<system_information>OS: Linux</system_information>\n"
            "<current_date_and_time>Date: 2026-04-14</current_date_and_time>\n"
            "<model_information>Claude</model_information>\n"
            "What is Python?"
        )
        result = strip_kiro_system_prompt(text)
        assert result == "What is Python?"

    def test_whitespace_cleanup(self):
        """Excessive whitespace after stripping is cleaned up."""
        text = FULL_KIRO_PROMPT + "\n\n\n\n\n" + USER_QUESTION
        result = strip_kiro_system_prompt(text)
        assert "\n\n\n" not in result
        assert USER_QUESTION in result

    def test_all_known_tags_stripped(self):
        """Every tag in KIRO_SYSTEM_TAGS is stripped when signature present."""
        # Build text with all tags + 2 signature tags to trigger detection
        parts = []
        for tag in KIRO_SYSTEM_TAGS:
            parts.append(f"<{tag}>content for {tag}</{tag}>")
        parts.append("Actual user question")
        text = "\n".join(parts)

        result = strip_kiro_system_prompt(text)
        for tag in KIRO_SYSTEM_TAGS:
            assert f"<{tag}>" not in result
            assert f"</{tag}>" not in result
        assert "Actual user question" in result


class TestChatFilterIntegration:
    """Tests for ChatFilter using the shared utility."""

    def test_strip_system_tags_handles_kiro_prompt(self):
        """strip_system_tags removes Kiro system prompt blocks."""
        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        text = FULL_KIRO_PROMPT + USER_QUESTION
        result = f.strip_system_tags(text)
        assert "<key_kiro_features>" not in result
        assert "<system_information>" not in result
        assert USER_QUESTION in result

    def test_clean_user_message_prompt_plus_question(self):
        """clean_user_message preserves user question after stripping prompt."""
        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        text = FULL_KIRO_PROMPT + USER_QUESTION
        result = f.clean_user_message(text)
        assert result is not None
        assert USER_QUESTION in result

    def test_clean_user_message_pure_prompt_returns_none(self):
        """clean_user_message returns None for pure system prompt."""
        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        result = f.clean_user_message(FULL_KIRO_PROMPT)
        assert result is None

    def test_keep_steering_preserves_kiro_prompt(self):
        """keep_steering=True preserves Kiro system prompt blocks."""
        f = ChatFilter(filter_system_tags=True, keep_steering=True)
        text = FULL_KIRO_PROMPT + USER_QUESTION
        result = f.strip_system_tags(text)
        assert "<key_kiro_features>" in result

    def test_legitimate_user_xml_not_stripped(self):
        """User content with XML-like tags is not falsely stripped."""
        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        text = "Please parse this: <rules>my custom rules</rules>"
        result = f.clean_user_message(text)
        assert result == text


class TestParserIntegration:
    """Tests for extract_messages_from_execution_log with system prompt."""

    def test_system_prompt_stripped_from_execution_log(self):
        """Kiro system prompt in execution log is stripped, user text preserved."""
        execution_log = {
            "context": {
                "messages": [
                    {
                        "role": "human",
                        "entries": [
                            {"type": "text", "text": FULL_KIRO_PROMPT + USER_QUESTION}
                        ]
                    },
                    {
                        "role": "bot",
                        "entries": [
                            {"type": "text", "text": "Here are the JIRA epics..."}
                        ]
                    },
                ]
            }
        }
        result = extract_messages_from_execution_log(execution_log)
        assert len(result) == 2
        # User message should have system prompt stripped
        assert "<key_kiro_features>" not in result[0]["content"]
        assert USER_QUESTION in result[0]["content"]
        # Bot message unchanged
        assert result[1]["content"] == "Here are the JIRA epics..."

    def test_pure_system_prompt_message_dropped(self):
        """A message that is purely system prompt produces no content."""
        execution_log = {
            "context": {
                "messages": [
                    {
                        "role": "human",
                        "entries": [
                            {"type": "text", "text": FULL_KIRO_PROMPT}
                        ]
                    },
                    {
                        "role": "human",
                        "entries": [
                            {"type": "text", "text": USER_QUESTION}
                        ]
                    },
                    {
                        "role": "bot",
                        "entries": [
                            {"type": "text", "text": "Answer"}
                        ]
                    },
                ]
            }
        }
        result = extract_messages_from_execution_log(execution_log)
        # Pure system prompt message should be dropped (empty after strip)
        assert len(result) == 2
        assert result[0]["content"] == USER_QUESTION
        assert result[1]["content"] == "Answer"

    def test_variant_prompt_without_key_kiro_features(self):
        """Prompt variant without key_kiro_features is still detected and stripped."""
        variant_prompt = (
            "<system_information>OS: Linux</system_information>\n"
            "<current_date_and_time>Date: 2026-04-14</current_date_and_time>\n"
            "<model_information>Claude</model_information>\n"
        )
        execution_log = {
            "context": {
                "messages": [
                    {
                        "role": "human",
                        "entries": [
                            {"type": "text", "text": variant_prompt + USER_QUESTION}
                        ]
                    },
                    {
                        "role": "bot",
                        "entries": [
                            {"type": "text", "text": "Answer"}
                        ]
                    },
                ]
            }
        }
        result = extract_messages_from_execution_log(execution_log)
        assert len(result) == 2
        assert "<system_information>" not in result[0]["content"]
        assert USER_QUESTION in result[0]["content"]

    def test_legitimate_user_xml_preserved_in_execution_log(self):
        """User content with XML-like tags is not falsely stripped."""
        execution_log = {
            "context": {
                "messages": [
                    {
                        "role": "human",
                        "entries": [
                            {"type": "text", "text": "Parse this: <rules>my rules</rules>"}
                        ]
                    },
                    {
                        "role": "bot",
                        "entries": [
                            {"type": "text", "text": "Sure, here are your rules."}
                        ]
                    },
                ]
            }
        }
        result = extract_messages_from_execution_log(execution_log)
        assert len(result) == 2
        assert "<rules>my rules</rules>" in result[0]["content"]

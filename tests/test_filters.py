"""Tests for the filters module."""

import pytest
from src.filters import ChatFilter


class TestSummarizeSteeringReminders:
    """Tests for _summarize_steering_reminders method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = ChatFilter(filter_system_tags=True)

    def test_no_steering_blocks_passthrough(self):
        """Text without steering blocks should pass through unchanged."""
        text = "This is a normal user message without any steering content."
        result = self.filter._summarize_steering_reminders(text)
        assert result == text

    def test_single_steering_block_with_file_names(self):
        """Single steering block should be replaced with summary."""
        text = """<steering-reminder>

confirm-before-action.md:
# Confirm Before Action
Some content here...

jira-safety.md:
# JIRA Safety Rules
More content...
</steering-reminder>

What is the status of ticket ABC-123?"""

        result = self.filter._summarize_steering_reminders(text)
        
        # Should contain summary
        assert "*[Steering files included:" in result
        assert "confirm-before-action.md" in result
        assert "jira-safety.md" in result
        # Should not contain original content
        assert "<steering-reminder>" not in result
        assert "# Confirm Before Action" not in result
        # Should preserve user question
        assert "What is the status of ticket ABC-123?" in result

    def test_multiple_steering_blocks_deduplicated(self):
        """Multiple steering blocks should be merged and deduplicated."""
        text = """<steering-reminder>
confirm-before-action.md:
Content 1
</steering-reminder>

User message here

<steering-reminder>
confirm-before-action.md:
Content 1 again

jira-safety.md:
Content 2
</steering-reminder>

Another user message"""

        result = self.filter._summarize_steering_reminders(text)
        
        # Should have single summary with deduplicated files
        assert result.count("*[Steering files included:") == 1
        # Both file names should appear once
        assert "confirm-before-action.md" in result
        assert "jira-safety.md" in result
        # Should preserve user messages
        assert "User message here" in result
        assert "Another user message" in result

    def test_empty_steering_block(self):
        """Empty steering block should be removed without adding summary."""
        text = """<steering-reminder></steering-reminder>

User question here"""

        result = self.filter._summarize_steering_reminders(text)
        
        # Should not have summary (no file names found)
        assert "*[Steering files included:" not in result
        # Should not have steering tags
        assert "<steering-reminder>" not in result
        # Should preserve user content
        assert "User question here" in result

    def test_steering_block_no_recognizable_file_names(self):
        """Steering block without .md file names should be removed without summary."""
        text = """<steering-reminder>
Some random content without file name patterns
Just text here
</steering-reminder>

User message"""

        result = self.filter._summarize_steering_reminders(text)
        
        # Should not have summary
        assert "*[Steering files included:" not in result
        # Should not have steering tags
        assert "<steering-reminder>" not in result
        # Should preserve user content
        assert "User message" in result

    def test_file_names_sorted_alphabetically(self):
        """File names in summary should be sorted alphabetically."""
        text = """<steering-reminder>
zebra-rules.md:
Content

alpha-config.md:
Content

middle-file.md:
Content
</steering-reminder>"""

        result = self.filter._summarize_steering_reminders(text)
        
        # Find the summary line
        assert "alpha-config.md, middle-file.md, zebra-rules.md" in result

    def test_strip_system_tags_includes_steering_summary(self):
        """strip_system_tags should process steering reminders."""
        text = """<steering-reminder>
my-rules.md:
# Rules
Content here
</steering-reminder>

<system-reminder>Some system stuff</system-reminder>

User question"""

        result = self.filter.strip_system_tags(text)
        
        # Steering should be summarized
        assert "*[Steering files included: my-rules.md]*" in result
        # System reminder should be removed
        assert "<system-reminder>" not in result
        # User content preserved
        assert "User question" in result


class TestStripSystemTags:
    """Tests for strip_system_tags method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = ChatFilter(filter_system_tags=True)

    def test_removes_ide_opened_file(self):
        """Should remove ide_opened_file tags."""
        text = "<ide_opened_file>some/path.py</ide_opened_file>Check this file"
        result = self.filter.strip_system_tags(text)
        assert "<ide_opened_file>" not in result
        assert "Check this file" in result

    def test_removes_system_reminder(self):
        """Should remove system-reminder tags."""
        text = "<system-reminder>Remember to do X</system-reminder>User message"
        result = self.filter.strip_system_tags(text)
        assert "<system-reminder>" not in result
        assert "User message" in result

    def test_removes_command_message(self):
        """Should remove command-message tags."""
        text = "<command-message>npm run build</command-message>Build failed"
        result = self.filter.strip_system_tags(text)
        assert "<command-message>" not in result
        assert "Build failed" in result

    def test_disabled_filter_passthrough(self):
        """When disabled, should pass through unchanged."""
        filter_disabled = ChatFilter(filter_system_tags=False)
        text = "<system-reminder>Content</system-reminder>Message"
        result = filter_disabled.strip_system_tags(text)
        assert result == text

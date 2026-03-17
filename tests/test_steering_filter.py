"""Tests for steering/included rules filtering in ChatFilter."""

import pytest
from src.filters import ChatFilter


class TestStripIncludedRules:
    """Tests for _strip_included_rules method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = ChatFilter(filter_system_tags=True, keep_steering=False)

    def test_no_included_rules_passthrough(self):
        """Text without Included Rules blocks should pass through unchanged."""
        text = "This is a normal user message."
        result = self.filter._strip_included_rules(text)
        assert result == text

    def test_single_included_rules_block(self):
        """Single Included Rules block should be replaced with summary."""
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
These rules govern all interactions with JIRA.
```
</user-rule>

What is the status of ticket ABC-123?"""

        result = self.filter._strip_included_rules(text)

        assert "*[Steering files included: Global/jira-safety.md]*" in result
        assert "What is the status of ticket ABC-123?" in result
        assert "<user-rule" not in result
        assert "JIRA Safety Rules" not in result

    def test_multiple_included_rules_blocks(self):
        """Multiple Included Rules blocks should be merged into one summary."""
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
Content here
```
</user-rule>

## Included Rules (ericsson/EEA_JIRA.md) [Workspace]
  I am providing you some additional guidance...
<user-rule id=ericsson/EEA_JIRA.md>
```
# EEA JIRA Knowledge
More content
```
</user-rule>

My actual question here."""

        result = self.filter._strip_included_rules(text)

        assert "*[Steering files included:" in result
        assert "Global/jira-safety.md" in result
        assert "ericsson/EEA_JIRA.md" in result
        assert result.count("*[Steering files included:") == 1
        assert "My actual question here." in result
        assert "<user-rule" not in result

    def test_rule_names_sorted_alphabetically(self):
        """Rule names in summary should be sorted."""
        text = """## Included Rules (zebra.md) [Global]
  Guidance...
<user-rule id=zebra.md>
```
content
```
</user-rule>

## Included Rules (alpha.md) [Workspace]
  Guidance...
<user-rule id=alpha.md>
```
content
```
</user-rule>

Question"""

        result = self.filter._strip_included_rules(text)
        assert "alpha.md, zebra.md" in result

    def test_duplicate_rule_names_deduplicated(self):
        """Duplicate rule names should appear only once."""
        text = """## Included Rules (same-rule.md) [Global]
  Guidance...
<user-rule id=same-rule.md>
```
content
```
</user-rule>

## Included Rules (same-rule.md) [Workspace]
  Guidance...
<user-rule id=same-rule.md>
```
content again
```
</user-rule>

Question"""

        result = self.filter._strip_included_rules(text)
        # Should appear exactly once in the summary
        assert result.count("same-rule.md") == 1

    def test_keep_steering_preserves_content(self):
        """When keep_steering=True, Included Rules blocks should be preserved."""
        filter_keep = ChatFilter(filter_system_tags=True, keep_steering=True)
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
Content
```
</user-rule>

Question"""

        result = filter_keep._strip_included_rules(text)
        assert result == text

    def test_incomplete_block_no_closing_tag(self):
        """Incomplete block without closing tag should not be matched."""
        text = """## Included Rules (broken.md) [Global]
  Some guidance...
<user-rule id=broken.md>
```
Content without closing tag

My question here."""

        result = self.filter._strip_included_rules(text)
        # Should pass through unchanged since pattern doesn't match
        assert result == text

    def test_path_style_rule_names(self):
        """Rule names with path separators should be handled."""
        text = """## Included Rules (Global/confluence-mcp.md) [Global]
  Guidance...
<user-rule id=Global/confluence-mcp.md>
```
# Confluence Rules
Content
```
</user-rule>

Question"""

        result = self.filter._strip_included_rules(text)
        assert "Global/confluence-mcp.md" in result
        assert "Question" in result

    def test_bare_name_references_stripped(self):
        """Bare steering file names left after blocks should be removed."""
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
Content
```
</user-rule>

## Included Rules (ericsson/EEA_JIRA.md) [Workspace]
  I am providing you some additional guidance...
<user-rule id=ericsson/EEA_JIRA.md>
```
# EEA JIRA Knowledge
Content
```
</user-rule>

## Included Rules (Global/confluence-mcp.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/confluence-mcp.md>
```
# Confluence Rules
Content
```
</user-rule>

Global/jira-safety.mdericsson/EEA_JIRA.mdGlobal/confluence-mcp.md
talk with me about JIRA ticket EEAEPP-115211"""

        result = self.filter._strip_included_rules(text)

        # Summary should be present
        assert "*[Steering files included:" in result
        assert "Global/jira-safety.md" in result
        # Bare name references should be gone
        assert "Global/jira-safety.mdericsson" not in result
        # Actual user question should be preserved
        assert "talk with me about JIRA ticket EEAEPP-115211" in result

    def test_legitimate_filename_reference_preserved(self):
        """User text that legitimately references a rule filename should be preserved."""
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
Content
```
</user-rule>

Can you compare Global/jira-safety.md with our old policy document?"""

        result = self.filter._strip_included_rules(text)

        # Summary should be present
        assert "*[Steering files included: Global/jira-safety.md]*" in result
        # The legitimate user reference must be preserved
        assert "compare Global/jira-safety.md with our old policy document?" in result

    def test_filename_as_substring_not_altered(self):
        """Filenames appearing as substrings inside larger tokens should not be altered."""
        text = """## Included Rules (safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=safety.md>
```
Content
```
</user-rule>

Check the file my-safety.md-backup for the old version."""

        result = self.filter._strip_included_rules(text)

        # The substring occurrence inside a larger token must survive
        assert "my-safety.md-backup" in result


class TestStripEnvironmentContext:
    """Tests for _strip_environment_context method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = ChatFilter(filter_system_tags=True, keep_steering=False)

    def test_no_environment_context_passthrough(self):
        """Text without EnvironmentContext should pass through unchanged."""
        text = "Normal message without context."
        result = self.filter._strip_environment_context(text)
        assert result == text

    def test_strips_environment_context(self):
        """EnvironmentContext block should be removed."""
        text = """My question here.

<EnvironmentContext>
This information is provided as context about user environment.
<OPEN-EDITOR-FILES>
<file name=".gitignore" />
<file name="src/main.py" />
</OPEN-EDITOR-FILES>
<ACTIVE-EDITOR-FILE>
<file name=".gitignore" />
</ACTIVE-EDITOR-FILE>
</EnvironmentContext>"""

        result = self.filter._strip_environment_context(text)
        assert "<EnvironmentContext>" not in result
        assert "OPEN-EDITOR-FILES" not in result
        assert "My question here." in result

    def test_keep_steering_preserves_environment_context(self):
        """When keep_steering=True, EnvironmentContext should be preserved."""
        filter_keep = ChatFilter(filter_system_tags=True, keep_steering=True)
        text = """Question

<EnvironmentContext>
<OPEN-EDITOR-FILES>
<file name="test.py" />
</OPEN-EDITOR-FILES>
</EnvironmentContext>"""

        result = filter_keep._strip_environment_context(text)
        assert result == text

    def test_multiple_environment_contexts(self):
        """Multiple EnvironmentContext blocks should all be removed."""
        text = """First message.

<EnvironmentContext>
<OPEN-EDITOR-FILES><file name="a.py" /></OPEN-EDITOR-FILES>
</EnvironmentContext>

Second message.

<EnvironmentContext>
<OPEN-EDITOR-FILES><file name="b.py" /></OPEN-EDITOR-FILES>
</EnvironmentContext>"""

        result = self.filter._strip_environment_context(text)
        assert "<EnvironmentContext>" not in result
        assert "First message." in result
        assert "Second message." in result


class TestStripSystemTagsIntegration:
    """Integration tests for strip_system_tags with all filtering combined."""

    def test_all_kiro_noise_stripped(self):
        """Full Kiro message with all noise types should be cleaned."""
        text = """## Included Rules (confirm-before-action.md) [Global]
  I am providing you some additional guidance...
<user-rule id=confirm-before-action.md>
```
# Confirm Before Action
Rule content here
```
</user-rule>

<steering-reminder>
start.md:
Some steering content
</steering-reminder>

<EnvironmentContext>
<OPEN-EDITOR-FILES>
<file name="test.py" />
</OPEN-EDITOR-FILES>
</EnvironmentContext>

My actual question about the code."""

        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        result = f.strip_system_tags(text)

        # All noise removed
        assert "<user-rule" not in result
        assert "<steering-reminder>" not in result
        assert "<EnvironmentContext>" not in result
        # Summaries present
        assert "*[Steering files included:" in result
        # User content preserved
        assert "My actual question about the code." in result

    def test_keep_steering_flag_preserves_all(self):
        """With keep_steering=True, steering and env context are preserved."""
        text = """## Included Rules (rule.md) [Global]
  Guidance...
<user-rule id=rule.md>
```
Content
```
</user-rule>

<EnvironmentContext>
<OPEN-EDITOR-FILES><file name="a.py" /></OPEN-EDITOR-FILES>
</EnvironmentContext>

<system-reminder>System stuff</system-reminder>

Question"""

        f = ChatFilter(filter_system_tags=True, keep_steering=True)
        result = f.strip_system_tags(text)

        # Steering and env context preserved
        assert "<user-rule" in result
        assert "<EnvironmentContext>" in result
        # System tags still stripped (keep_steering only affects steering/env)
        assert "<system-reminder>" not in result
        assert "Question" in result

    def test_keep_steering_preserves_steering_reminders(self):
        """With keep_steering=True, steering-reminder blocks are preserved verbatim."""
        text = """<steering-reminder>
confirm-before-action.md:
# Confirm Before Action
Rule content here

start.md:
Some steering content
</steering-reminder>

My actual question about the code."""

        f = ChatFilter(filter_system_tags=True, keep_steering=True)
        result = f.strip_system_tags(text)

        # Steering-reminder block should be fully preserved
        assert "<steering-reminder>" in result
        assert "confirm-before-action.md:" in result
        assert "# Confirm Before Action" in result
        assert "start.md:" in result
        # No summary replacement should appear
        assert "*[Steering files included:" not in result
        # User content preserved
        assert "My actual question about the code." in result

    def test_clean_user_message_with_only_steering(self):
        """Message that is only steering content should return None."""
        text = """## Included Rules (rule.md) [Global]
  Guidance...
<user-rule id=rule.md>
```
Content
```
</user-rule>"""

        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        result = f.clean_user_message(text)

        # After stripping, only summary remains — should still be returned
        # since the summary is meaningful (> 5 chars)
        assert result is not None
        assert "*[Steering files included: rule.md]*" in result

    def test_clean_user_message_steering_plus_question(self):
        """Message with steering + real question should return cleaned question."""
        text = """## Included Rules (rule.md) [Global]
  Guidance...
<user-rule id=rule.md>
```
Content
```
</user-rule>

How do I fix the login bug?"""

        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        result = f.clean_user_message(text)

        assert result is not None
        assert "How do I fix the login bug?" in result
        assert "<user-rule" not in result


class TestExtractTitleFromUserContent:
    """Tests for _extract_title_from_user_content helper."""

    def test_plain_text_returns_first_line(self):
        """Plain text should return the first line as title."""
        from src.exporters import _extract_title_from_user_content
        result = _extract_title_from_user_content("How do I fix the login bug?")
        assert result == "How do I fix the login bug?"

    def test_steering_content_returns_actual_question(self):
        """Text with steering blocks should return the actual user question."""
        from src.exporters import _extract_title_from_user_content
        text = """## Included Rules (Global/jira-safety.md) [Global]
  I am providing you some additional guidance...
<user-rule id=Global/jira-safety.md>
```
# JIRA Safety Rules
Content
```
</user-rule>

Global/jira-safety.mdtalk with me about JIRA ticket EEAEPP-115211"""

        result = _extract_title_from_user_content(text)
        assert result is not None
        assert "talk with me about JIRA ticket" in result
        assert "Included Rules" not in result

    def test_empty_text_returns_none(self):
        """Empty or whitespace-only text should return None."""
        from src.exporters import _extract_title_from_user_content
        assert _extract_title_from_user_content("") is None
        assert _extract_title_from_user_content("   ") is None
        assert _extract_title_from_user_content(None) is None

    def test_only_steering_returns_none(self):
        """Text that is only a short system tag should return None."""
        from src.exporters import _extract_title_from_user_content
        text = "<system-reminder>x</system-reminder>"
        result = _extract_title_from_user_content(text)
        assert result is None

    def test_truncation_at_max_length(self):
        """Long lines should be truncated with ellipsis."""
        from src.exporters import _extract_title_from_user_content
        long_text = "A" * 100
        result = _extract_title_from_user_content(long_text, max_length=60)
        assert len(result) == 63  # 60 + "..."
        assert result.endswith("...")

    def test_with_chat_filter_provided(self):
        """Should use the provided ChatFilter instance."""
        from src.exporters import _extract_title_from_user_content
        from src.filters import ChatFilter
        f = ChatFilter(filter_system_tags=True, keep_steering=False)
        text = """<system-reminder>stuff</system-reminder>

My actual question here"""
        result = _extract_title_from_user_content(text, chat_filter=f)
        assert result == "My actual question here"


class TestFilenameGenerationWithSteering:
    """Tests for filename generation functions with steering content."""

    def test_generate_filename_skips_steering(self):
        """_generate_filename_from_content should use actual question, not steering."""
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource

        chat_data = [{
            'message': {
                'role': 'user',
                'content': """## Included Rules (Global/jira-safety.md) [Global]
  Guidance...
<user-rule id=Global/jira-safety.md>
```
Content
```
</user-rule>

talk with me about JIRA ticket EEAEPP-115211"""
            }
        }]

        result = _generate_filename_from_content(chat_data, 'fallback', ChatSource.KIRO_IDE)
        assert 'jira-safety' not in result
        assert 'included-rules' not in result
        assert 'talk-with-me-about-jira-ticket' in result

    def test_generate_filename_fallback_when_only_steering(self):
        """Should use fallback when message is only steering with no real content."""
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource

        chat_data = [{
            'message': {
                'role': 'user',
                'content': "<system-reminder>x</system-reminder>"
            }
        }]

        result = _generate_filename_from_content(chat_data, 'my-fallback', ChatSource.KIRO_IDE)
        assert result == 'my-fallback'

    def test_generate_filename_no_steering_works_normally(self):
        """Without steering, should work as before."""
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource

        chat_data = [{
            'message': {
                'role': 'user',
                'content': 'How do I fix the login bug?'
            }
        }]

        result = _generate_filename_from_content(chat_data, 'fallback', ChatSource.KIRO_IDE)
        assert 'how-do-i-fix-the-login-bug' in result

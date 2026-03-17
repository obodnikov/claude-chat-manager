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

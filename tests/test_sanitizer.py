"""Tests for sanitizer module."""

import pytest
from src.sanitizer import Sanitizer, SanitizationMatch, SanitizationReport, SanitizationLevel, RedactionStyle


class TestSanitizer:
    """Test suite for Sanitizer class."""

    def test_initialization(self):
        """Test sanitizer initialization."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        assert sanitizer.enabled is True
        assert sanitizer.level == SanitizationLevel.BALANCED
        assert sanitizer.style == RedactionStyle.PARTIAL

    def test_disabled_sanitizer(self):
        """Test that disabled sanitizer doesn't modify text."""
        sanitizer = Sanitizer(enabled=False)

        text = "My API key is sk-proj-abc123xyz789 for testing"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert sanitized == text
        assert matches == []

    def test_api_key_detection_openai(self):
        """Test OpenAI API key detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        # Use realistic 20+ char key
        text = "My API key is sk-proj-abc123xyz789ABCDEFGH for testing"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 1
        assert matches[0].pattern_type == 'api_key'
        assert 'sk-proj-abc123xyz789ABCDEFGH' not in sanitized
        assert 'sk-pr***FGH' in sanitized

    def test_api_key_detection_openrouter(self):
        """Test OpenRouter API key detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        text = "export OPENROUTER_API_KEY=sk-or-v1-1234567890abcdef"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1
        assert 'sk-or-v1-1234567890abcdef' not in sanitized

    def test_api_key_detection_github(self):
        """Test GitHub personal access token detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "My GitHub token: ghp_" + "a" * 36
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 1
        assert matches[0].pattern_type == 'api_key'
        assert 'ghp_' + 'a' * 36 not in sanitized

    def test_bearer_token_detection(self):
        """Test Bearer token detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1
        # Should match either Bearer token or JWT
        assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in sanitized or 'Bearer eyJ' not in sanitized

    def test_jwt_token_detection(self):
        """Test JWT token detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1
        assert '[TOKEN]' in sanitized

    def test_password_context_detection(self):
        """Test contextual password detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = 'password = "MySecretPass123"'
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 1
        assert matches[0].pattern_type == 'password_context'
        assert 'MySecretPass123' not in sanitized

    def test_password_variations(self):
        """Test various password assignment patterns."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        test_cases = [
            'password: secretpass',
            'passwd = "mypassword123"',
            "pwd: 'testing123'",
            'secret = verysecretvalue'
        ]

        for text in test_cases:
            sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)
            assert len(matches) >= 1, f"Failed to detect password in: {text}"

    def test_env_var_detection(self):
        """Test environment variable detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "API_KEY=sk-proj-1234567890abcdef"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should match either env_var or api_key pattern
        assert len(matches) >= 1
        assert 'sk-proj-1234567890abcdef' not in sanitized

    def test_export_statement(self):
        """Test export statement detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        text = "export SECRET_KEY=mysecretvalue123"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1
        assert 'mysecretvalue123' not in sanitized

    def test_allowlist_prevents_sanitization(self):
        """Test that allowlist prevents sanitization."""
        sanitizer = Sanitizer(
            enabled=True,
            level='balanced',
            style='partial',
            allowlist=[r'sk-xxx+']
        )

        text = "Use sk-xxxxxxxxxxxx as placeholder"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 0
        assert 'sk-xxxxxxxxxxxx' in sanitized

    def test_allowlist_example_domain(self):
        """Test that example.com is allowlisted by default."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "Visit https://api.example.com for docs"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should not match allowlisted domains
        assert sanitized == text

    def test_custom_patterns(self):
        """Test custom pattern sanitization."""
        sanitizer = Sanitizer(
            enabled=True,
            level='custom',
            style='labeled',
            custom_patterns=[r'mycompany-[0-9]+']
        )

        text = "Token: mycompany-12345"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 1
        assert 'mycompany-12345' not in sanitized
        assert '[REDACTED]' in sanitized

    def test_multiple_matches(self):
        """Test multiple matches in same text."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        text = """
        API_KEY=sk-proj-abc123
        PASSWORD=secretpass
        Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature
        """
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should find at least 2 different types of secrets
        assert len(matches) >= 2
        pattern_types = set(m.pattern_type for m in matches)
        assert len(pattern_types) >= 2

    def test_redaction_style_simple(self):
        """Test simple redaction style."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='simple')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert 'REDACTED' in sanitized
        assert 'sk-proj' not in sanitized

    def test_redaction_style_stars(self):
        """Test stars redaction style."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='stars')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert '*' in sanitized
        assert 'sk-proj' not in sanitized

    def test_redaction_style_labeled(self):
        """Test labeled redaction style."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert '[API_KEY]' in sanitized
        assert 'sk-proj' not in sanitized

    def test_redaction_style_partial(self):
        """Test partial redaction style."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should keep first 5 and last 3 chars
        assert len(matches) == 1
        assert matches[0].redacted_value.startswith('sk-pr')
        assert matches[0].redacted_value.endswith('FGH')
        assert '***' in matches[0].redacted_value

    def test_redaction_style_hash(self):
        """Test hash redaction style."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='hash')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should create consistent hash
        assert len(matches) == 1
        assert matches[0].redacted_value.startswith('[')
        assert matches[0].redacted_value.endswith(']')
        assert len(matches[0].redacted_value) == 10  # [8chars]

    def test_hash_consistency(self):
        """Test that hash redaction is consistent for same value."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='hash')

        text = "Key1: sk-proj-abc123 and Key2: sk-proj-abc123"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Same value should produce same hash
        if len(matches) >= 2:
            assert matches[0].redacted_value == matches[1].redacted_value

    def test_sanitization_level_minimal(self):
        """Test minimal sanitization level."""
        sanitizer = Sanitizer(enabled=True, level='minimal', style='labeled')

        # Should detect obvious API keys
        text1 = "API key: sk-proj-abc123xyz789ABCDEFGH"
        sanitized1, matches1 = sanitizer.sanitize_text(text1, track_changes=True)
        assert len(matches1) == 1

    def test_sanitization_level_balanced(self):
        """Test balanced sanitization level."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        # Should detect API keys, tokens, and contextual passwords
        text = """
        API_KEY=sk-proj-abc123xyz789ABCDEFGH
        password: mypass123
        """
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)
        assert len(matches) >= 1

    def test_line_number_tracking(self):
        """Test line number tracking in matches."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = """Line 1
Line 2
API key: sk-proj-abc123xyz789ABCDEFGH
Line 4"""
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 1
        assert matches[0].line_number == 3

    def test_preview_mode(self):
        """Test preview sanitization without applying changes."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "API key: sk-proj-abc123xyz789ABCDEFGH"
        matches = sanitizer.preview_sanitization(text)

        # Preview should not modify text
        assert len(matches) == 1
        assert matches[0].pattern_type == 'api_key'

    def test_sanitization_report(self):
        """Test sanitization report generation."""
        matches = [
            SanitizationMatch(
                pattern_type='api_key',
                original_value='sk-proj-abc123',
                redacted_value='sk-pr***123',
                position=0,
                line_number=1
            ),
            SanitizationMatch(
                pattern_type='api_key',
                original_value='ghp_xyz789',
                redacted_value='ghp_x***789',
                position=20,
                line_number=2
            ),
            SanitizationMatch(
                pattern_type='password_context',
                original_value='mypassword',
                redacted_value='mypas***ord',
                position=40,
                line_number=3
            )
        ]

        report = SanitizationReport(matches=matches)

        assert report.total_matches == 3
        assert report.by_category['api_key'] == 2
        assert report.by_category['password_context'] == 1

        # Test text report generation
        text_report = report.to_text()
        assert 'Total matches: 3' in text_report
        assert '2 Api Key' in text_report
        assert '1 Password Context' in text_report

    def test_chat_data_sanitization(self):
        """Test sanitization of chat data structure."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': 'My API key is sk-proj-abc123xyz789ABCDEFGH'
                },
                'timestamp': '2025-01-01T10:00:00Z'
            },
            {
                'message': {
                    'role': 'assistant',
                    'content': 'I see your key. Let me help.'
                },
                'timestamp': '2025-01-01T10:00:05Z'
            }
        ]

        sanitized_data, report = sanitizer.sanitize_chat_data(chat_data)

        assert len(sanitized_data) == 2
        assert report.total_matches == 1
        assert 'sk-proj-abc123xyz789ABCDEFGH' not in sanitized_data[0]['message']['content']
        assert 'sk-pr***FGH' in sanitized_data[0]['message']['content']

    def test_chat_data_with_structured_content(self):
        """Test sanitization of chat data with structured content list."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='labeled')

        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': 'Here is my key: sk-proj-abc123xyz789ABCDEFGH'
                        }
                    ]
                }
            }
        ]

        sanitized_data, report = sanitizer.sanitize_chat_data(chat_data)

        assert report.total_matches == 1
        assert 'sk-proj-abc123xyz789' not in str(sanitized_data)
        assert '[API_KEY]' in sanitized_data[0]['message']['content'][0]['text']

    def test_no_false_positives_on_short_strings(self):
        """Test that short strings don't trigger false positives."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        # These should NOT be detected as secrets
        text = "use sk for sk key"  # Too short
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) == 0

    def test_aws_access_key_detection(self):
        """Test AWS access key detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1
        assert 'AKIAIOSFODNN7EXAMPLE' not in sanitized

    def test_google_api_key_detection(self):
        """Test Google API key detection."""
        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')

        text = "GOOGLE_API_KEY=AIzaSyD" + "a" * 28  # 35 chars total after AIza
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert len(matches) >= 1

    def test_invalid_custom_regex_handling(self):
        """Test that invalid custom regex patterns are handled gracefully."""
        # Invalid regex pattern with unmatched bracket
        sanitizer = Sanitizer(
            enabled=True,
            level='custom',
            style='labeled',
            custom_patterns=[r'[invalid(']  # Invalid regex
        )

        # Should not crash, just log warning and skip invalid pattern
        text = "Some text with no matches"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        assert sanitized == text
        assert len(matches) == 0

    def test_invalid_allowlist_regex_handling(self):
        """Test that invalid allowlist regex patterns are handled gracefully."""
        # Invalid regex in allowlist
        sanitizer = Sanitizer(
            enabled=True,
            level='balanced',
            style='partial',
            allowlist=[r'[invalid(', r'valid\.com']  # One invalid, one valid
        )

        # Should still work with valid patterns
        text = "Visit valid.com or api.valid.com"
        sanitized, matches = sanitizer.sanitize_text(text, track_changes=True)

        # Should not crash
        assert sanitized == text


class TestSanitizationMatch:
    """Test SanitizationMatch dataclass."""

    def test_match_creation(self):
        """Test creating a sanitization match."""
        match = SanitizationMatch(
            pattern_type='api_key',
            original_value='sk-proj-abc123',
            redacted_value='sk-pr***123',
            position=10,
            line_number=2,
            confidence=1.0
        )

        assert match.pattern_type == 'api_key'
        assert match.original_value == 'sk-proj-abc123'
        assert match.redacted_value == 'sk-pr***123'
        assert match.position == 10
        assert match.line_number == 2
        assert match.confidence == 1.0


class TestSanitizationReport:
    """Test SanitizationReport dataclass."""

    def test_empty_report(self):
        """Test empty sanitization report."""
        report = SanitizationReport(matches=[])

        assert report.total_matches == 0
        assert report.by_category == {}

    def test_report_with_matches(self):
        """Test report with multiple matches."""
        matches = [
            SanitizationMatch('api_key', 'val1', 'red1', 0, 1),
            SanitizationMatch('api_key', 'val2', 'red2', 10, 2),
            SanitizationMatch('token', 'val3', 'red3', 20, 3)
        ]

        report = SanitizationReport(matches=matches)

        assert report.total_matches == 3
        assert report.by_category['api_key'] == 2
        assert report.by_category['token'] == 1


class TestBookExportIntegration:
    """Test integration with book export functionality."""

    def test_book_export_with_sanitization(self):
        """Test that book export correctly sanitizes sensitive data."""
        from src.exporters import export_chat_book

        # Create sample chat data with API key
        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': 'How do I use my API key sk-proj-abc123xyz789ABCDEFGH?'
                },
                'timestamp': '2025-12-26T10:00:00Z'
            },
            {
                'message': {
                    'role': 'assistant',
                    'content': 'You can use it like this: export API_KEY=sk-proj-abc123xyz789ABCDEFGH'
                },
                'timestamp': '2025-12-26T10:00:01Z'
            }
        ]

        # Export with sanitization enabled
        output = export_chat_book(chat_data, sanitize=True)

        # Verify API key was redacted
        assert 'sk-proj-abc123xyz789ABCDEFGH' not in output
        # Should contain partial redaction (default style is partial)
        assert 'sk-pr***FGH' in output or '[API_KEY]' in output or 'REDACTED' in output

    def test_book_export_without_sanitization(self):
        """Test that book export preserves data when sanitization is disabled."""
        from src.exporters import export_chat_book

        chat_data = [
            {
                'message': {
                    'role': 'user',
                    'content': 'My key is sk-proj-abc123xyz789ABCDEFGH'
                },
                'timestamp': '2025-12-26T10:00:00Z'
            }
        ]

        # Export with sanitization disabled
        output = export_chat_book(chat_data, sanitize=False)

        # Original key should be preserved
        assert 'sk-proj-abc123xyz789ABCDEFGH' in output

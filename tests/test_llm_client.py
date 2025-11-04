"""Tests for LLM client module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from urllib.error import HTTPError, URLError

from src.llm_client import OpenRouterClient, OpenRouterError


class TestOpenRouterClient:
    """Test cases for OpenRouterClient class."""

    def test_initialization(self):
        """Test client initialization with default values."""
        client = OpenRouterClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.model == "anthropic/claude-3-haiku"
        assert client.base_url == "https://openrouter.ai/api/v1"
        assert client.timeout == 30

    def test_initialization_custom_values(self):
        """Test client initialization with custom values."""
        client = OpenRouterClient(
            api_key="custom-key",
            model="openai/gpt-4",
            base_url="https://custom.api.com",
            timeout=60
        )
        assert client.api_key == "custom-key"
        assert client.model == "openai/gpt-4"
        assert client.base_url == "https://custom.api.com"
        assert client.timeout == 60

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_success(self, mock_urlopen):
        """Test successful title generation."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": "Implementing Custom Exception Handling"
                    }
                }
            ]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("How do I add custom exceptions?")

        assert title == "Implementing Custom Exception Handling"
        assert mock_urlopen.called

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_with_quotes(self, mock_urlopen):
        """Test title generation strips quotes."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": '"Adding Test Suite"'
                    }
                }
            ]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Let's add tests")

        assert title == "Adding Test Suite"
        assert '"' not in title

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_truncates_long_titles(self, mock_urlopen):
        """Test that overly long titles are truncated."""
        long_title = "This Is An Extremely Long Title That Exceeds The Maximum Word Count Limit"
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": long_title
                    }
                }
            ]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test", max_words=5)

        # Should be truncated to 5 words
        assert len(title.split()) == 5
        assert title.startswith("This Is An Extremely Long")

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_http_error_401(self, mock_urlopen):
        """Test handling of 401 authentication error."""
        mock_urlopen.side_effect = HTTPError(
            url="test",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error": "Invalid API key"}')
        )

        client = OpenRouterClient(api_key="invalid-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_http_error_429(self, mock_urlopen):
        """Test handling of 429 rate limit error."""
        mock_urlopen.side_effect = HTTPError(
            url="test",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error": "Rate limit exceeded"}')
        )

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_http_error_500(self, mock_urlopen):
        """Test handling of 500 server error."""
        mock_urlopen.side_effect = HTTPError(
            url="test",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error": "Server error"}')
        )

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_network_error(self, mock_urlopen):
        """Test handling of network errors."""
        mock_urlopen.side_effect = URLError("Network unreachable")

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_invalid_json(self, mock_urlopen):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"Invalid JSON response"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_generate_chat_title_empty_choices(self, mock_urlopen):
        """Test handling of empty choices in response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": []
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key")
        title = client.generate_chat_title("Test conversation")

        assert title is None

    @patch('src.llm_client.request.urlopen')
    def test_call_api_includes_headers(self, mock_urlopen):
        """Test that API calls include required headers."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Test Title"}}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key-123")
        client.generate_chat_title("Test")

        # Verify the request was made with proper headers
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]

        assert request_obj.get_header('Authorization') == "Bearer test-key-123"
        assert request_obj.get_header('Content-type') == "application/json"
        assert request_obj.get_header('Http-referer') == "https://github.com/claude-chat-manager"
        assert request_obj.get_header('X-title') == "Claude Chat Manager"

    @patch('src.llm_client.request.urlopen')
    def test_call_api_timeout_applied(self, mock_urlopen):
        """Test that timeout is applied to API calls."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Test Title"}}]
        }).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = OpenRouterClient(api_key="test-key", timeout=45)
        client.generate_chat_title("Test")

        # Verify timeout was passed
        call_args = mock_urlopen.call_args
        assert call_args[1]['timeout'] == 45

"""OpenRouter API client for LLM-powered features.

This module provides integration with OpenRouter.ai for generating
chat titles and other LLM-powered functionality.
"""

import json
import logging
from typing import Optional
from urllib import request, error
from urllib.parse import urljoin

from .exceptions import ClaudeReaderError

logger = logging.getLogger(__name__)


class OpenRouterError(ClaudeReaderError):
    """Raised when OpenRouter API encounters an error."""

    pass


class OpenRouterClient:
    """Client for OpenRouter API to generate chat titles and summaries.

    This client uses the standard library's urllib instead of external
    dependencies to maintain the project's zero-dependency philosophy.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-3-haiku",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 30
    ) -> None:
        """Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key.
            model: Model identifier (default: claude-3-haiku for speed/cost).
            base_url: OpenRouter API base URL.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

        logger.debug(f"Initialized OpenRouter client with model: {model}")

    def generate_chat_title(
        self,
        conversation_excerpt: str,
        max_words: int = 10
    ) -> Optional[str]:
        """Generate a descriptive title from conversation excerpt.

        Args:
            conversation_excerpt: First portion of the conversation.
            max_words: Maximum words in generated title.

        Returns:
            Generated title string, or None if generation fails.

        Example:
            >>> client = OpenRouterClient(api_key="...")
            >>> title = client.generate_chat_title("How do I add tests?...")
            >>> print(title)
            'Implementing Pytest Test Suite'
        """
        prompt = f"""Based on this conversation excerpt, generate a concise, descriptive title ({max_words} words or less) that captures the main topic.

Conversation:
{conversation_excerpt}

Return ONLY the title, nothing else. No quotes, no punctuation at the end.
Example format: "Implementing Custom Exception Handling in Python"
"""

        try:
            response = self._call_api(prompt, max_tokens=50)
            title = response.strip().strip('"').strip("'")

            # Validate title length
            word_count = len(title.split())
            if word_count > max_words + 2:  # Allow slight overflow
                logger.warning(f"Generated title too long ({word_count} words): {title}")
                # Truncate to max_words
                title = ' '.join(title.split()[:max_words])

            logger.info(f"Generated title: {title}")
            return title

        except OpenRouterError as e:
            logger.error(f"Failed to generate title: {e}")
            return None

    def _call_api(self, prompt: str, max_tokens: int = 100) -> str:
        """Make API request to OpenRouter.

        Args:
            prompt: The prompt to send to the LLM.
            max_tokens: Maximum tokens in response.

        Returns:
            Response text from the API.

        Raises:
            OpenRouterError: If API request fails.
        """
        url = urljoin(self.base_url, "chat/completions")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3  # Lower temperature for more focused output
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/claude-chat-manager",
            "X-Title": "Claude Chat Manager"
        }

        try:
            req = request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )

            logger.debug(f"Calling OpenRouter API: {self.model}")

            with request.urlopen(req, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode('utf-8'))

            # Extract response text
            if 'choices' in response_data and len(response_data['choices']) > 0:
                content = response_data['choices'][0]['message']['content']
                logger.debug(f"API response: {content[:100]}...")
                return content
            else:
                raise OpenRouterError("No response from API")

        except error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else "No error details"
            logger.error(f"HTTP error {e.code}: {error_body}")

            if e.code == 401:
                raise OpenRouterError("Invalid API key")
            elif e.code == 429:
                raise OpenRouterError("Rate limit exceeded")
            elif e.code >= 500:
                raise OpenRouterError(f"Server error: {e.code}")
            else:
                raise OpenRouterError(f"HTTP error: {e.code}")

        except error.URLError as e:
            logger.error(f"Network error: {e.reason}")
            raise OpenRouterError(f"Network error: {e.reason}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise OpenRouterError("Invalid API response format")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise OpenRouterError(f"Unexpected error: {e}")

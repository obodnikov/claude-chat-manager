"""Property-based tests for kiro_parser module.

These tests use Hypothesis to verify universal properties across many generated inputs.
Each test runs a minimum of 100 iterations to ensure comprehensive coverage.
"""

import json
import pytest
from pathlib import Path
from hypothesis import given, strategies as st, settings

from src.kiro_parser import (
    parse_kiro_chat_file,
    extract_kiro_messages,
    normalize_kiro_content
)


# Hypothesis strategies for generating test data

@st.composite
def kiro_message(draw):
    """Generate a valid Kiro message."""
    role = draw(st.sampled_from(['human', 'bot', 'tool']))
    
    # Generate either string content or array content
    content_type = draw(st.sampled_from(['string', 'array']))
    
    if content_type == 'string':
        content = draw(st.text(min_size=1, max_size=200))
    else:
        # Generate array of content blocks
        num_blocks = draw(st.integers(min_value=1, max_value=5))
        blocks = []
        for _ in range(num_blocks):
            block_type = draw(st.sampled_from(['text', 'tool_use', 'image_url', 'image']))
            if block_type == 'text':
                blocks.append({
                    'type': 'text',
                    'text': draw(st.text(min_size=1, max_size=100))
                })
            elif block_type == 'tool_use':
                blocks.append({
                    'type': 'tool_use',
                    'name': draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
                    'input': {}
                })
            elif block_type == 'image_url':
                blocks.append({
                    'type': 'image_url',
                    'image_url': {'url': 'http://example.com/image.png'}
                })
            else:  # image
                blocks.append({
                    'type': 'image',
                    'source': {'data': 'base64data'}
                })
        content = blocks
    
    return {'role': role, 'content': content}


@st.composite
def kiro_chat_data(draw):
    """Generate valid Kiro chat data structure."""
    num_messages = draw(st.integers(min_value=1, max_value=50))
    messages = [draw(kiro_message()) for _ in range(num_messages)]
    
    return {
        'executionId': draw(st.uuids()).hex,
        'context': [],
        'chat': messages
    }


class TestProperty1MessageCountPreservation:
    """Property 1: Kiro Chat Parsing Preserves Message Structure.
    
    Feature: kiro-chat-support, Property 1: Kiro Chat Parsing Preserves Message Structure
    Validates: Requirements 1.1, 1.2
    
    For any valid Kiro .chat file containing N messages, parsing the file and 
    extracting messages SHALL produce exactly N ChatMessage objects, each with 
    role and content fields populated.
    """

    @settings(max_examples=100)
    @given(chat_data=kiro_chat_data())
    def test_message_count_preserved(self, chat_data):
        """Property test: Message count is preserved through parsing."""
        # Feature: kiro-chat-support, Property 1: Kiro Chat Parsing Preserves Message Structure
        
        # Arrange: Write chat data to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.chat', delete=False, encoding='utf-8') as f:
            json.dump(chat_data, f)
            file_path = Path(f.name)
        
        try:
            # Act: Parse file and extract messages
            session = parse_kiro_chat_file(file_path)
            messages = extract_kiro_messages(chat_data)
            
            # Assert: Message count is preserved
            expected_count = len(chat_data['chat'])
            assert len(session.messages) == expected_count, \
                f"Session should have {expected_count} messages, got {len(session.messages)}"
            assert len(messages) == expected_count, \
                f"Extracted messages should have {expected_count} items, got {len(messages)}"
            
            # Assert: Each message has role and content
            for msg in messages:
                assert msg.role is not None and msg.role != '', \
                    "Each message must have a non-empty role"
                assert msg.content is not None, \
                    "Each message must have content (even if empty string)"
        finally:
            # Cleanup
            file_path.unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(chat_data=kiro_chat_data())
    def test_role_preservation(self, chat_data):
        """Property test: Message roles are preserved."""
        # Feature: kiro-chat-support, Property 1: Kiro Chat Parsing Preserves Message Structure
        
        # Act: Extract messages
        messages = extract_kiro_messages(chat_data)
        
        # Assert: Roles match original data
        for i, msg in enumerate(messages):
            expected_role = chat_data['chat'][i].get('role', 'unknown')
            assert msg.role == expected_role, \
                f"Message {i} role should be '{expected_role}', got '{msg.role}'"

    @settings(max_examples=100)
    @given(chat_data=kiro_chat_data())
    def test_content_populated(self, chat_data):
        """Property test: All messages have content populated."""
        # Feature: kiro-chat-support, Property 1: Kiro Chat Parsing Preserves Message Structure
        
        # Act: Extract messages
        messages = extract_kiro_messages(chat_data)
        
        # Assert: All messages have content
        for i, msg in enumerate(messages):
            assert msg.content is not None, \
                f"Message {i} must have content field populated"
            # Content should be a string after normalization
            assert isinstance(msg.content, str), \
                f"Message {i} content should be normalized to string, got {type(msg.content)}"



class TestProperty10ContentNormalizationTransparency:
    """Property 10: Content Normalization Transparency.
    
    Feature: kiro-chat-support, Property 10: Content Normalization Transparency
    Validates: Requirements 8.1, 8.4
    
    For any message content that is either a string or an array of content blocks,
    normalizing the content SHALL produce a non-empty string, and for string inputs,
    the output SHALL equal the input.
    """

    @settings(max_examples=100)
    @given(content=st.text(min_size=1, max_size=500))
    def test_string_content_passthrough(self, content):
        """Property test: String content passes through unchanged."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Act: Normalize string content
        result = normalize_kiro_content(content)
        
        # Assert: Output equals input for strings
        assert result == content, \
            f"String content should pass through unchanged"
        assert isinstance(result, str), \
            f"Result should be a string"

    @settings(max_examples=100)
    @given(
        num_blocks=st.integers(min_value=1, max_value=10),
        block_texts=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=10)
    )
    def test_array_content_produces_string(self, num_blocks, block_texts):
        """Property test: Array content produces non-empty string."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Arrange: Create array of text blocks
        content = []
        for i in range(min(num_blocks, len(block_texts))):
            content.append({
                'type': 'text',
                'text': block_texts[i]
            })
        
        # Act: Normalize array content
        result = normalize_kiro_content(content)
        
        # Assert: Result is a non-empty string
        assert isinstance(result, str), \
            f"Normalized array content should be a string"
        assert len(result) > 0, \
            f"Normalized array content should be non-empty when input has text blocks"

    @settings(max_examples=100)
    @given(
        content=st.one_of(
            st.text(min_size=1),
            st.lists(
                st.fixed_dictionaries({
                    'type': st.just('text'),
                    'text': st.text(min_size=1, max_size=100)
                }),
                min_size=1,
                max_size=5
            )
        )
    )
    def test_normalization_always_produces_string(self, content):
        """Property test: Normalization always produces a string."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Act: Normalize content
        result = normalize_kiro_content(content)
        
        # Assert: Result is always a string
        assert isinstance(result, str), \
            f"normalize_kiro_content should always return a string, got {type(result)}"

    @settings(max_examples=100)
    @given(
        text_blocks=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)
    )
    def test_text_blocks_concatenated(self, text_blocks):
        """Property test: Text blocks are concatenated with newlines."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Arrange: Create array of text blocks
        content = [{'type': 'text', 'text': text} for text in text_blocks]
        
        # Act: Normalize content
        result = normalize_kiro_content(content)
        
        # Assert: All text blocks appear in result
        for text in text_blocks:
            assert text in result, \
                f"Text block '{text}' should appear in normalized result"

    @settings(max_examples=100)
    @given(
        tool_names=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))),
            min_size=1,
            max_size=3
        )
    )
    def test_tool_blocks_formatted(self, tool_names):
        """Property test: Tool use blocks are formatted with markers."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Arrange: Create array with tool use blocks
        content = [{'type': 'tool_use', 'name': name} for name in tool_names]
        
        # Act: Normalize content
        result = normalize_kiro_content(content)
        
        # Assert: Tool markers appear in result
        for name in tool_names:
            assert f"[Tool: {name}]" in result, \
                f"Tool marker for '{name}' should appear in normalized result"

    @settings(max_examples=100)
    @given(num_images=st.integers(min_value=1, max_value=5))
    def test_image_blocks_indicated(self, num_images):
        """Property test: Image blocks are indicated with markers."""
        # Feature: kiro-chat-support, Property 10: Content Normalization Transparency
        
        # Arrange: Create array with image blocks
        content = [{'type': 'image_url', 'image_url': {'url': f'img{i}.png'}} for i in range(num_images)]
        
        # Act: Normalize content
        result = normalize_kiro_content(content)
        
        # Assert: Image markers appear in result
        image_count = result.count('[Image]')
        assert image_count == num_images, \
            f"Should have {num_images} image markers, found {image_count}"

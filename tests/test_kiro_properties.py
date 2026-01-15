"""Property-based tests for kiro_parser and kiro_projects modules.

These tests use Hypothesis to verify universal properties across many generated inputs.
Each test runs a minimum of 100 iterations to ensure comprehensive coverage.
"""

import base64
import json
import pytest
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings

from src.kiro_parser import (
    parse_kiro_chat_file,
    extract_kiro_messages,
    normalize_kiro_content
)
from src.kiro_projects import (
    decode_workspace_path,
    list_kiro_sessions
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



class TestProperty4Base64RoundTrip:
    """Property 4: Base64 Workspace Path Round-Trip.
    
    Feature: kiro-chat-support, Property 4: Base64 Workspace Path Round-Trip
    Validates: Requirements 2.2
    
    For any valid filesystem path string, encoding it to base64 and then decoding
    SHALL produce the original path string (accounting for URL-safe base64 encoding).
    """

    @settings(max_examples=100)
    @given(
        path=st.one_of(
            # Windows paths
            st.from_regex(r'[A-Z]:\\[A-Za-z0-9_\-\\]+', fullmatch=True),
            # Unix paths
            st.from_regex(r'/[a-z]+(/[a-z0-9_\-]+)+', fullmatch=True),
            # Simple paths
            st.text(min_size=1, max_size=100, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='_-/\\'
            ))
        )
    )
    def test_base64_round_trip(self, path):
        """Property test: Base64 encoding and decoding preserves path."""
        # Feature: kiro-chat-support, Property 4: Base64 Workspace Path Round-Trip
        
        # Act: Encode then decode
        encoded = base64.urlsafe_b64encode(path.encode('utf-8')).decode('utf-8')
        # Remove padding as Kiro does
        encoded = encoded.rstrip('=')
        decoded = decode_workspace_path(encoded)
        
        # Assert: Round trip preserves original path
        assert decoded == path, \
            f"Round trip should preserve path. Original: '{path}', Decoded: '{decoded}'"

    @settings(max_examples=100)
    @given(
        path=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                blacklist_categories=('Cc', 'Cs'),  # Exclude control chars
                blacklist_characters='\x00'  # Exclude null
            )
        )
    )
    def test_arbitrary_string_round_trip(self, path):
        """Property test: Any valid UTF-8 string survives round trip."""
        # Feature: kiro-chat-support, Property 4: Base64 Workspace Path Round-Trip
        
        # Act: Encode then decode
        encoded = base64.urlsafe_b64encode(path.encode('utf-8')).decode('utf-8')
        encoded = encoded.rstrip('=')
        decoded = decode_workspace_path(encoded)
        
        # Assert: Round trip preserves original string
        assert decoded == path, \
            f"Round trip should preserve string"

    @settings(max_examples=100)
    @given(
        components=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd')
            )),
            min_size=1,
            max_size=5
        )
    )
    def test_path_components_preserved(self, components):
        """Property test: Path components are preserved through encoding."""
        # Feature: kiro-chat-support, Property 4: Base64 Workspace Path Round-Trip
        
        # Arrange: Build path from components
        path = '\\'.join(components)  # Windows-style
        
        # Act: Encode then decode
        encoded = base64.urlsafe_b64encode(path.encode('utf-8')).decode('utf-8')
        encoded = encoded.rstrip('=')
        decoded = decode_workspace_path(encoded)
        
        # Assert: All components present in decoded path
        for component in components:
            assert component in decoded, \
                f"Component '{component}' should be in decoded path"

    @settings(max_examples=100)
    @given(
        # Generate paths with specific lengths to test all padding cases
        # len % 4 == 0 (no padding), == 1 (invalid), == 2 (== padding), == 3 (= padding)
        path_length=st.integers(min_value=1, max_value=100)
    )
    def test_padding_edge_cases(self, path_length):
        """Property test: Correct padding is applied for all path lengths."""
        # Feature: kiro-chat-support, Property 4: Base64 Workspace Path Round-Trip
        
        # Arrange: Create path of specific length
        path = 'x' * path_length
        
        # Act: Encode then decode
        encoded = base64.urlsafe_b64encode(path.encode('utf-8')).decode('utf-8')
        encoded_no_padding = encoded.rstrip('=')
        
        # Verify the encoded string length modulo 4 to ensure we test all cases
        remainder = len(encoded_no_padding) % 4
        
        # Decode
        decoded = decode_workspace_path(encoded_no_padding)
        
        # Assert: Round trip preserves original path regardless of padding needs
        assert decoded == path, \
            f"Path length {path_length} (encoded len % 4 = {remainder}) should round-trip correctly"


class TestProperty5SessionDiscoveryCompleteness:
    """Property 5: Session Discovery Completeness.
    
    Feature: kiro-chat-support, Property 5: Session Discovery Completeness
    Validates: Requirements 2.4, 2.5
    
    For any Kiro workspace directory containing a valid sessions.json with N session
    entries, discovering sessions SHALL return exactly N KiroSession objects, each
    with sessionId, title, and dateCreated populated.
    """

    @settings(max_examples=100)
    @given(
        num_sessions=st.integers(min_value=1, max_value=20),
        session_ids=st.lists(
            st.text(min_size=5, max_size=20, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='-'
            )),
            min_size=1,
            max_size=20,
            unique=True
        ),
        titles=st.lists(
            st.text(min_size=1, max_size=50),
            min_size=1,
            max_size=20
        ),
        timestamps=st.lists(
            st.integers(min_value=1000000000000, max_value=9999999999999),
            min_size=1,
            max_size=20
        )
    )
    def test_session_count_preserved(self, num_sessions, session_ids, titles, timestamps):
        """Property test: Session count is preserved through discovery."""
        # Feature: kiro-chat-support, Property 5: Session Discovery Completeness
        
        # Arrange: Create temporary workspace with sessions.json
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            # Build sessions data
            sessions_data = []
            actual_count = min(num_sessions, len(session_ids), len(titles), len(timestamps))
            for i in range(actual_count):
                sessions_data.append({
                    'sessionId': session_ids[i],
                    'title': titles[i],
                    'dateCreated': timestamps[i],
                    'workspaceDirectory': 'C:\\workspace'
                })
            
            # Write sessions.json
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            # Act: Discover sessions
            sessions = list_kiro_sessions(workspace_dir)
            
            # Assert: Count matches
            assert len(sessions) == actual_count, \
                f"Should discover {actual_count} sessions, found {len(sessions)}"

    @settings(max_examples=100)
    @given(
        sessions_data=st.lists(
            st.fixed_dictionaries({
                'sessionId': st.text(min_size=1, max_size=30, alphabet=st.characters(
                    whitelist_categories=('Lu', 'Ll', 'Nd'),
                    whitelist_characters='-_'
                )),
                'title': st.text(min_size=1, max_size=100),
                'dateCreated': st.integers(min_value=1000000000000, max_value=9999999999999),
                'workspaceDirectory': st.text(min_size=1, max_size=100)
            }),
            min_size=1,
            max_size=15,
            unique_by=lambda x: x['sessionId']
        )
    )
    def test_all_fields_populated(self, sessions_data):
        """Property test: All required fields are populated in discovered sessions."""
        # Feature: kiro-chat-support, Property 5: Session Discovery Completeness
        
        # Arrange: Create temporary workspace with sessions.json
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            # Act: Discover sessions
            sessions = list_kiro_sessions(workspace_dir)
            
            # Assert: All sessions have required fields populated
            assert len(sessions) == len(sessions_data), \
                f"Should discover all {len(sessions_data)} sessions"
            
            for i, session in enumerate(sessions):
                assert session.session_id is not None and session.session_id != '', \
                    f"Session {i} must have non-empty sessionId"
                assert session.title is not None and session.title != '', \
                    f"Session {i} must have non-empty title"
                assert session.date_created is not None and session.date_created != '', \
                    f"Session {i} must have non-empty dateCreated"

    @settings(max_examples=100)
    @given(
        sessions_data=st.lists(
            st.fixed_dictionaries({
                'sessionId': st.text(min_size=1, max_size=30, alphabet=st.characters(
                    whitelist_categories=('Lu', 'Ll', 'Nd'),
                    whitelist_characters='-_'
                )),
                'title': st.text(min_size=1, max_size=100),
                'dateCreated': st.integers(min_value=1000000000000, max_value=9999999999999),
                'workspaceDirectory': st.text(min_size=1, max_size=100)
            }),
            min_size=1,
            max_size=10,
            unique_by=lambda x: x['sessionId']
        )
    )
    def test_session_ids_match(self, sessions_data):
        """Property test: Discovered session IDs match input data."""
        # Feature: kiro-chat-support, Property 5: Session Discovery Completeness
        
        # Arrange: Create temporary workspace with sessions.json
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            # Act: Discover sessions
            sessions = list_kiro_sessions(workspace_dir)
            
            # Assert: Session IDs match
            discovered_ids = {s.session_id for s in sessions}
            expected_ids = {s['sessionId'] for s in sessions_data}
            
            assert discovered_ids == expected_ids, \
                f"Discovered session IDs should match input data"

    @settings(max_examples=100)
    @given(
        num_sessions=st.integers(min_value=0, max_value=50)
    )
    def test_empty_sessions_handled(self, num_sessions):
        """Property test: Empty or minimal sessions are handled correctly."""
        # Feature: kiro-chat-support, Property 5: Session Discovery Completeness
        
        # Arrange: Create sessions with minimal data
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            
            sessions_data = [
                {
                    'sessionId': f'session-{i}',
                    'title': f'Session {i}',
                    'dateCreated': 1234567890000 + i,
                    'workspaceDirectory': 'C:\\workspace'
                }
                for i in range(num_sessions)
            ]
            
            sessions_file = workspace_dir / 'sessions.json'
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f)
            
            # Act: Discover sessions
            sessions = list_kiro_sessions(workspace_dir)
            
            # Assert: Count matches (including zero)
            assert len(sessions) == num_sessions, \
                f"Should discover exactly {num_sessions} sessions"

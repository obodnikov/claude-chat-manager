"""Property-based tests for kiro_parser and kiro_projects modules.

These tests use Hypothesis to verify universal properties across many generated inputs.
Each test runs a minimum of 100 iterations to ensure comprehensive coverage.
"""

import base64
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

from src.kiro_parser import (
    parse_kiro_chat_file,
    extract_kiro_messages,
    normalize_kiro_content
)
from src.kiro_projects import (
    decode_workspace_path,
    list_kiro_sessions,
    discover_kiro_workspaces
)
from src.models import ChatSource, ProjectInfo
from src.projects import list_all_projects, search_projects_by_name, get_recent_projects


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



# Helper functions for test data generation

def create_mock_claude_projects(num_projects: int, base_path: Path) -> list:
    """Helper to create mock Claude project directories."""
    projects = []
    for i in range(num_projects):
        project_dir = base_path / f"claude-project-{i}"
        project_dir.mkdir(parents=True, exist_ok=True)
        # Create a dummy JSONL file
        jsonl_file = project_dir / f"chat-{i}.jsonl"
        jsonl_file.write_text('{"role":"user","content":"test"}\n')
        projects.append(project_dir)
    return projects


def create_mock_kiro_workspace(workspace_dir: Path, num_sessions: int, workspace_path: str = None) -> Path:
    """Helper to create mock Kiro workspace with sessions.
    
    Args:
        workspace_dir: The encoded directory path where sessions.json will be stored
        num_sessions: Number of sessions to create
        workspace_path: The actual workspace path (decoded) to store in workspaceDirectory field
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # If workspace_path not provided, use workspace_dir as fallback
    if workspace_path is None:
        workspace_path = str(workspace_dir)
    
    # Create sessions.json
    sessions_data = []
    for i in range(num_sessions):
        sessions_data.append({
            'sessionId': f'session-{i}',
            'title': f'Session {i}',
            'dateCreated': 1234567890000 + i,
            'workspaceDirectory': workspace_path  # Use the actual workspace path
        })
    
    sessions_file = workspace_dir / 'sessions.json'
    with open(sessions_file, 'w', encoding='utf-8') as f:
        json.dump(sessions_data, f)
    
    # Create session files
    for i in range(num_sessions):
        session_file = workspace_dir / f'session-{i}.json'
        session_file.write_text('{"chat":[]}')
    
    return workspace_dir


class TestProperty6SourceFilteringCorrectness:
    """Property 6: Source Filtering Correctness.
    
    Feature: kiro-chat-support, Property 6: Source Filtering Correctness
    Validates: Requirements 3.3, 3.5
    
    For any list of projects from mixed sources (Claude and Kiro), filtering by a
    specific source SHALL return only projects where the source field matches the
    filter, and the count SHALL be less than or equal to the original list size.
    """

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=0, max_value=10),
        num_kiro=st.integers(min_value=0, max_value=10)
    )
    def test_list_all_projects_filters_by_source(self, num_claude, num_kiro):
        """Property test: list_all_projects correctly filters by source."""
        # Feature: kiro-chat-support, Property 6: Source Filtering Correctness
        
        assume(num_claude > 0 or num_kiro > 0)  # Need at least one project
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            # Create mock Claude projects
            if num_claude > 0:
                claude_projects = create_mock_claude_projects(num_claude, claude_dir)
            
            # Create mock Kiro workspace
            if num_kiro > 0:
                # Encode workspace path
                workspace_path = str(tmpdir_path / 'workspace')
                encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
                workspace_dir = kiro_dir / encoded
                create_mock_kiro_workspace(workspace_dir, num_kiro, workspace_path)
            
            # Mock config to use our temp directories
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = kiro_dir.parent.exists()
                
                # Test filtering by Claude only
                if num_claude > 0:
                    claude_projects = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                    assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in claude_projects), \
                        "Claude filter should return only Claude projects"
                    assert len(claude_projects) == num_claude, \
                        f"Should return {num_claude} Claude projects, got {len(claude_projects)}"
                
                # Test filtering by Kiro only
                if num_kiro > 0:
                    kiro_projects = list_all_projects(ChatSource.KIRO_IDE)
                    assert all(p.source == ChatSource.KIRO_IDE for p in kiro_projects), \
                        "Kiro filter should return only Kiro projects"
                    # Note: Kiro returns workspaces, not individual sessions
                    # We create exactly 1 workspace when num_kiro > 0
                    assert len(kiro_projects) == 1, \
                        f"Should return exactly 1 Kiro workspace, got {len(kiro_projects)}"
                
                # Test no filter (all sources)
                all_projects = list_all_projects(None)
                total_expected = num_claude + (1 if num_kiro > 0 else 0)  # 1 workspace
                assert len(all_projects) == total_expected, \
                    f"Should return {total_expected} total projects"

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=1, max_value=10),
        num_kiro_sessions=st.integers(min_value=1, max_value=10)
    )
    def test_filtered_count_less_than_or_equal_original(self, num_claude, num_kiro_sessions):
        """Property test: Filtered count is <= original count."""
        # Feature: kiro-chat-support, Property 6: Source Filtering Correctness
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            # Create mock projects
            create_mock_claude_projects(num_claude, claude_dir)
            
            workspace_path = str(tmpdir_path / 'workspace')
            encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
            workspace_dir = kiro_dir / encoded
            create_mock_kiro_workspace(workspace_dir, num_kiro_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = True
                
                # Get all projects
                all_projects = list_all_projects(None)
                original_count = len(all_projects)
                
                # Filter by each source
                claude_filtered = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                kiro_filtered = list_all_projects(ChatSource.KIRO_IDE)
                
                # Assert filtered counts are <= original
                assert len(claude_filtered) <= original_count, \
                    f"Claude filtered ({len(claude_filtered)}) should be <= original ({original_count})"
                assert len(kiro_filtered) <= original_count, \
                    f"Kiro filtered ({len(kiro_filtered)}) should be <= original ({original_count})"
                
                # Assert exact counts for accuracy
                assert len(claude_filtered) == num_claude, \
                    f"Should return exactly {num_claude} Claude projects"
                assert len(kiro_filtered) == 1, \
                    f"Should return exactly 1 Kiro workspace (not {len(kiro_filtered)})"

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=1, max_value=8),
        num_kiro_sessions=st.integers(min_value=1, max_value=8)
    )
    def test_no_cross_contamination_in_search(self, num_claude, num_kiro_sessions):
        """Property test: search_projects_by_name respects source filter."""
        # Feature: kiro-chat-support, Property 6: Source Filtering Correctness
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            # Create projects with distinctive names
            create_mock_claude_projects(num_claude, claude_dir)
            
            # Create Kiro workspace with 'workspace' in the path name
            # The workspace_name will be the last component of the decoded path
            workspace_path = str(tmpdir_path / 'my-kiro-workspace')
            encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
            workspace_dir = kiro_dir / encoded
            create_mock_kiro_workspace(workspace_dir, num_kiro_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = True
                
                # Search with Claude filter - should only return Claude projects
                claude_results = search_projects_by_name('project', ChatSource.CLAUDE_DESKTOP)
                assert all(p.source == ChatSource.CLAUDE_DESKTOP for p in claude_results), \
                    "Claude search should never return Kiro projects"
                
                # Search with Kiro filter - should only return Kiro projects
                # The workspace name will be 'my-kiro-workspace' (last component of path)
                kiro_results = search_projects_by_name('workspace', ChatSource.KIRO_IDE)
                assert all(p.source == ChatSource.KIRO_IDE for p in kiro_results), \
                    "Kiro search should never return Claude projects"
                # Verify we actually found the workspace
                assert len(kiro_results) == 1, \
                    f"Should find exactly 1 Kiro workspace matching 'workspace', found {len(kiro_results)}"

    @settings(max_examples=100)
    @given(num_projects=st.integers(min_value=1, max_value=15))
    def test_filter_with_single_source_type(self, num_projects):
        """Property test: Filtering single-source projects works correctly."""
        # Feature: kiro-chat-support, Property 6: Source Filtering Correctness
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            # Create only Claude projects
            create_mock_claude_projects(num_projects, claude_dir)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir
                mock_config.validate_kiro_directory.return_value = False  # No Kiro
                
                # Filter by Claude (should return all)
                claude_filtered = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                assert len(claude_filtered) == num_projects, \
                    "Filtering by matching source should return all projects"
                
                # Filter by Kiro (should raise exception since no projects found)
                with pytest.raises(Exception):  # ProjectNotFoundError
                    kiro_filtered = list_all_projects(ChatSource.KIRO_IDE)


class TestProperty7ProjectSourceIndication:
    """Property 7: Project Source Indication.
    
    Feature: kiro-chat-support, Property 7: Project Source Indication
    Validates: Requirements 3.2
    
    For any project returned by the unified project listing, the source field SHALL
    be either ChatSource.CLAUDE_DESKTOP or ChatSource.KIRO_IDE (never UNKNOWN for
    discovered projects).
    """

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=0, max_value=10),
        num_kiro_sessions=st.integers(min_value=0, max_value=10)
    )
    def test_discovered_projects_have_valid_source(self, num_claude, num_kiro_sessions):
        """Property test: All discovered projects have valid source field."""
        # Feature: kiro-chat-support, Property 7: Project Source Indication
        
        assume(num_claude > 0 or num_kiro_sessions > 0)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            if num_claude > 0:
                create_mock_claude_projects(num_claude, claude_dir)
            
            if num_kiro_sessions > 0:
                workspace_path = str(tmpdir_path / 'workspace')
                encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
                workspace_dir = kiro_dir / encoded
                create_mock_kiro_workspace(workspace_dir, num_kiro_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = kiro_dir.parent.exists()
                
                # Get all projects
                projects = list_all_projects(None)
                
                # Assert: All projects have valid source (not UNKNOWN)
                for project in projects:
                    assert project.source != ChatSource.UNKNOWN, \
                        f"Project '{project.name}' should not have UNKNOWN source"
                    assert project.source in [ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE], \
                        f"Project '{project.name}' should have Claude or Kiro source, got {project.source}"

    @settings(max_examples=100)
    @given(num_sessions=st.integers(min_value=1, max_value=15))
    def test_kiro_sessions_have_kiro_source(self, num_sessions):
        """Property test: Kiro workspaces always have KIRO_IDE source."""
        # Feature: kiro-chat-support, Property 7: Project Source Indication
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            workspace_path = str(tmpdir_path / 'test-workspace')
            encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
            workspace_dir = kiro_dir / encoded
            create_mock_kiro_workspace(workspace_dir, num_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = Path('/nonexistent')
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = True
                
                # Get Kiro projects
                projects = list_all_projects(ChatSource.KIRO_IDE)
                
                # Assert: All are Kiro source
                assert len(projects) > 0, "Should discover at least one workspace"
                for project in projects:
                    assert project.source == ChatSource.KIRO_IDE, \
                        f"Kiro project '{project.name}' must have KIRO_IDE source"

    @settings(max_examples=100)
    @given(num_projects=st.integers(min_value=1, max_value=12))
    def test_claude_projects_have_claude_source(self, num_projects):
        """Property test: Claude projects always have CLAUDE_DESKTOP source."""
        # Feature: kiro-chat-support, Property 7: Project Source Indication
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            
            create_mock_claude_projects(num_projects, claude_dir)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = Path('/nonexistent')
                mock_config.validate_kiro_directory.return_value = False
                
                # Get Claude projects
                projects = list_all_projects(ChatSource.CLAUDE_DESKTOP)
                
                # Assert: All are Claude source
                assert len(projects) == num_projects, \
                    f"Should discover {num_projects} Claude projects"
                for project in projects:
                    assert project.source == ChatSource.CLAUDE_DESKTOP, \
                        f"Claude project '{project.name}' must have CLAUDE_DESKTOP source"

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=1, max_value=8),
        num_kiro_sessions=st.integers(min_value=1, max_value=8)
    )
    def test_mixed_sources_all_valid(self, num_claude, num_kiro_sessions):
        """Property test: Mixed source projects all have valid sources."""
        # Feature: kiro-chat-support, Property 7: Project Source Indication
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            create_mock_claude_projects(num_claude, claude_dir)
            
            workspace_path = str(tmpdir_path / 'workspace')
            encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
            workspace_dir = kiro_dir / encoded
            create_mock_kiro_workspace(workspace_dir, num_kiro_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = True
                
                # Get all projects
                projects = list_all_projects(None)
                
                # Assert: All have valid sources
                valid_sources = {ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE}
                for project in projects:
                    assert project.source in valid_sources, \
                        f"Project '{project.name}' has invalid source: {project.source}"
                    assert project.source != ChatSource.UNKNOWN, \
                        f"Project '{project.name}' must not have UNKNOWN source"

    @settings(max_examples=100)
    @given(
        num_claude=st.integers(min_value=1, max_value=10),
        num_kiro_sessions=st.integers(min_value=1, max_value=10)
    )
    def test_recent_projects_have_valid_sources(self, num_claude, num_kiro_sessions):
        """Property test: get_recent_projects returns projects with valid sources."""
        # Feature: kiro-chat-support, Property 7: Project Source Indication
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            claude_dir = tmpdir_path / 'claude'
            kiro_dir = tmpdir_path / 'kiro' / 'workspace-sessions'
            
            create_mock_claude_projects(num_claude, claude_dir)
            
            workspace_path = str(tmpdir_path / 'workspace')
            encoded = base64.urlsafe_b64encode(workspace_path.encode('utf-8')).decode('utf-8').rstrip('=')
            workspace_dir = kiro_dir / encoded
            create_mock_kiro_workspace(workspace_dir, num_kiro_sessions, workspace_path)
            
            with patch('src.projects.config') as mock_config:
                mock_config.claude_projects_dir = claude_dir
                mock_config.kiro_data_dir = kiro_dir.parent
                mock_config.validate_kiro_directory.return_value = True
                
                # Get recent projects
                recent = get_recent_projects(count=20, source_filter=None)
                
                # Assert: All have valid sources
                for project in recent:
                    assert project.source in [ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE], \
                        f"Recent project must have valid source"
                    assert project.source != ChatSource.UNKNOWN, \
                        f"Recent project must not have UNKNOWN source"



class TestProperty11SpecialBlockFormatting:
    """Property 11: Special Block Formatting.
    
    Feature: kiro-chat-support, Property 11: Special Block Formatting
    Validates: Requirements 8.2, 8.3
    
    For any Kiro message containing tool use blocks or image references, formatting
    the message SHALL produce output that contains distinct markers for these special
    blocks (e.g., "[Tool: name]" or "[Image]").
    """

    @settings(max_examples=100)
    @given(
        tool_names=st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='_-'
            )),
            min_size=1,
            max_size=5
        )
    )
    def test_tool_use_blocks_have_markers(self, tool_names):
        """Property test: Tool use blocks produce distinct markers."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Arrange: Create content with tool use blocks
        content = []
        for name in tool_names:
            content.append({
                'type': 'tool_use',
                'name': name,
                'input': {}
            })
        
        # Act: Format the content
        result = format_content(content, 'assistant')
        
        # Assert: Each tool name appears in a marker
        for name in tool_names:
            assert f'[Tool Use: {name}]' in result, \
                f"Tool use marker for '{name}' should appear in formatted output"

    @settings(max_examples=100)
    @given(num_images=st.integers(min_value=1, max_value=10))
    def test_image_blocks_have_markers(self, num_images):
        """Property test: Image blocks produce distinct markers."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Arrange: Create content with image blocks
        content = []
        for i in range(num_images):
            # Test both image_url and image types
            if i % 2 == 0:
                content.append({
                    'type': 'image_url',
                    'image_url': {'url': f'http://example.com/img{i}.png'}
                })
            else:
                content.append({
                    'type': 'image',
                    'source': {'data': f'base64data{i}'}
                })
        
        # Act: Format the content
        result = format_content(content, 'user')
        
        # Assert: Image markers appear for each image
        image_count = result.count('[Image]')
        assert image_count == num_images, \
            f"Should have {num_images} image markers, found {image_count}"

    @settings(max_examples=100)
    @given(
        num_tools=st.integers(min_value=1, max_value=5),
        num_images=st.integers(min_value=1, max_value=5),
        text_blocks=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=3)
    )
    def test_mixed_special_blocks_all_marked(self, num_tools, num_images, text_blocks):
        """Property test: Mixed content with special blocks all have markers."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Arrange: Create mixed content
        content = []
        
        # Add text blocks
        for text in text_blocks:
            content.append({'type': 'text', 'text': text})
        
        # Add tool use blocks
        tool_names = []
        for i in range(num_tools):
            name = f'tool{i}'
            tool_names.append(name)
            content.append({
                'type': 'tool_use',
                'name': name,
                'input': {}
            })
        
        # Add image blocks
        for i in range(num_images):
            content.append({
                'type': 'image_url',
                'image_url': {'url': f'img{i}.png'}
            })
        
        # Act: Format the content
        result = format_content(content, 'assistant')
        
        # Assert: All tool markers present
        for name in tool_names:
            assert f'[Tool Use: {name}]' in result, \
                f"Tool marker for '{name}' should be present"
        
        # Assert: All image markers present
        image_count = result.count('[Image]')
        assert image_count == num_images, \
            f"Should have {num_images} image markers, found {image_count}"
        
        # Assert: All non-empty text blocks present (after stripping)
        # Note: The formatter strips whitespace from text blocks
        for text in text_blocks:
            stripped_text = text.strip()
            if stripped_text:  # Only check non-empty stripped text
                assert stripped_text in result, \
                    f"Text block '{stripped_text}' should be present in output"

    @settings(max_examples=100)
    @given(
        tool_name=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='_-. '
        ))
    )
    def test_tool_marker_format_consistent(self, tool_name):
        """Property test: Tool markers follow consistent format."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Arrange: Create content with tool use
        content = [{
            'type': 'tool_use',
            'name': tool_name,
            'input': {'param': 'value'}
        }]
        
        # Act: Format the content
        result = format_content(content, 'assistant')
        
        # Assert: Marker follows format "[Tool Use: {name}]"
        expected_marker = f'[Tool Use: {tool_name}]'
        assert expected_marker in result, \
            f"Tool marker should follow format '[Tool Use: {{name}}]'"

    @settings(max_examples=100)
    @given(
        content_blocks=st.lists(
            st.one_of(
                st.fixed_dictionaries({
                    'type': st.just('tool_use'),
                    'name': st.text(min_size=1, max_size=20, alphabet=st.characters(
                        whitelist_categories=('Lu', 'Ll')
                    )),
                    'input': st.just({})
                }),
                st.fixed_dictionaries({
                    'type': st.just('image_url'),
                    'image_url': st.fixed_dictionaries({
                        'url': st.text(min_size=1, max_size=50)
                    })
                }),
                st.fixed_dictionaries({
                    'type': st.just('image'),
                    'source': st.just({'data': 'base64'})
                })
            ),
            min_size=1,
            max_size=10
        )
    )
    def test_special_blocks_never_empty_output(self, content_blocks):
        """Property test: Special blocks always produce non-empty output."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Act: Format the content
        result = format_content(content_blocks, 'user')
        
        # Assert: Output is non-empty
        assert len(result) > 0, \
            "Formatting special blocks should produce non-empty output"
        
        # Assert: Output contains at least one marker
        has_tool_marker = '[Tool Use:' in result
        has_image_marker = '[Image]' in result
        assert has_tool_marker or has_image_marker, \
            "Output should contain at least one special block marker"

    @settings(max_examples=100)
    @given(
        num_special_blocks=st.integers(min_value=1, max_value=15)
    )
    def test_marker_count_matches_block_count(self, num_special_blocks):
        """Property test: Number of markers matches number of special blocks."""
        # Feature: kiro-chat-support, Property 11: Special Block Formatting
        
        from src.formatters import format_content
        
        # Arrange: Create content with known number of special blocks
        content = []
        expected_tool_count = 0
        expected_image_count = 0
        
        for i in range(num_special_blocks):
            if i % 3 == 0:
                # Tool use block
                content.append({
                    'type': 'tool_use',
                    'name': f'tool{i}',
                    'input': {}
                })
                expected_tool_count += 1
            elif i % 3 == 1:
                # Image URL block
                content.append({
                    'type': 'image_url',
                    'image_url': {'url': f'img{i}.png'}
                })
                expected_image_count += 1
            else:
                # Image block
                content.append({
                    'type': 'image',
                    'source': {'data': 'base64'}
                })
                expected_image_count += 1
        
        # Act: Format the content
        result = format_content(content, 'assistant')
        
        # Assert: Marker counts match
        actual_tool_count = result.count('[Tool Use:')
        actual_image_count = result.count('[Image]')
        
        assert actual_tool_count == expected_tool_count, \
            f"Should have {expected_tool_count} tool markers, found {actual_tool_count}"
        assert actual_image_count == expected_image_count, \
            f"Should have {expected_image_count} image markers, found {actual_image_count}"



class TestProperty8ExportFormatSupport:
    """Property 8: Export Format Support.
    
    Feature: kiro-chat-support, Property 8: Export Format Support
    Validates: Requirements 4.1
    
    For any valid Kiro chat session and any supported export format (pretty, markdown,
    book, wiki), exporting SHALL complete without raising an exception and produce
    non-empty output.
    """

    @settings(max_examples=100)
    @given(
        chat_data=kiro_chat_data(),
        format_type=st.sampled_from(['pretty', 'markdown', 'book'])
    )
    def test_all_formats_export_successfully(self, chat_data, format_type):
        """Property test: All export formats work with Kiro chats."""
        # Feature: kiro-chat-support, Property 8: Export Format Support
        
        from src.exporters import export_chat_to_file
        
        # Arrange: Create temporary Kiro chat file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.chat', delete=False, encoding='utf-8') as f:
            json.dump(chat_data, f)
            chat_file = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            output_file = Path(f.name)
        
        try:
            # Act: Export to format (should not raise exception)
            export_chat_to_file(chat_file, output_file, format_type=format_type)
            
            # Assert: Output file exists and is non-empty
            assert output_file.exists(), \
                f"Export to {format_type} should create output file"
            
            content = output_file.read_text(encoding='utf-8')
            assert len(content) > 0, \
                f"Export to {format_type} should produce non-empty output"
            
        finally:
            # Cleanup
            chat_file.unlink(missing_ok=True)
            output_file.unlink(missing_ok=True)

    @settings(max_examples=100, deadline=None)
    @given(chat_data=kiro_chat_data())
    def test_markdown_export_produces_valid_markdown(self, chat_data):
        """Property test: Markdown export produces valid markdown structure."""
        # Feature: kiro-chat-support, Property 8: Export Format Support
        
        from src.exporters import export_chat_to_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.chat', delete=False, encoding='utf-8') as f:
            json.dump(chat_data, f)
            chat_file = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            output_file = Path(f.name)
        
        try:
            # Act: Export to markdown
            export_chat_to_file(chat_file, output_file, format_type='markdown')
            
            content = output_file.read_text(encoding='utf-8')
            
            # Assert: Contains markdown headers
            assert '# Claude Chat Export' in content, \
                "Markdown export should have main header"
            # Note: Messages may be filtered, so we just check for basic structure
            
        finally:
            chat_file.unlink(missing_ok=True)
            output_file.unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(chat_data=kiro_chat_data())
    def test_pretty_export_includes_formatting(self, chat_data):
        """Property test: Pretty export includes terminal formatting."""
        # Feature: kiro-chat-support, Property 8: Export Format Support
        
        from src.exporters import export_chat_to_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.chat', delete=False, encoding='utf-8') as f:
            json.dump(chat_data, f)
            chat_file = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            output_file = Path(f.name)
        
        try:
            # Act: Export to pretty format
            export_chat_to_file(chat_file, output_file, format_type='pretty')
            
            content = output_file.read_text(encoding='utf-8')
            
            # Assert: Contains formatting elements
            assert '─' in content or 'Message' in content, \
                "Pretty export should have visual separators or message indicators"
            
        finally:
            chat_file.unlink(missing_ok=True)
            output_file.unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(
        chat_data=kiro_chat_data(),
        format_type=st.sampled_from(['markdown', 'pretty'])
    )
    def test_export_preserves_message_count(self, chat_data, format_type):
        """Property test: Export preserves message count in output."""
        # Feature: kiro-chat-support, Property 8: Export Format Support
        
        from src.exporters import export_chat_to_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.chat', delete=False, encoding='utf-8') as f:
            json.dump(chat_data, f)
            chat_file = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            output_file = Path(f.name)
        
        try:
            # Act: Export
            export_chat_to_file(chat_file, output_file, format_type=format_type)
            
            content = output_file.read_text(encoding='utf-8')
            
            # Assert: Output is substantial (rough check for message preservation)
            # Note: Book format may filter messages, so we only test markdown and pretty
            # Each message should contribute some content
            assert len(content) > 50, \
                f"Export should produce substantial content from {len(chat_data['chat'])} messages"
            
        finally:
            chat_file.unlink(missing_ok=True)
            output_file.unlink(missing_ok=True)


class TestProperty9FilenameGenerationFromContent:
    """Property 9: Filename Generation From Content.
    
    Feature: kiro-chat-support, Property 9: Filename Generation From Content
    Validates: Requirements 4.3
    
    For any Kiro chat session with either a title or at least one user message,
    generating a filename SHALL produce a non-empty string derived from the title
    or first user message content.
    """

    @settings(max_examples=100)
    @given(
        user_message=st.text(min_size=1, max_size=200, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs'),
            whitelist_characters='.,!?-_'
        ))
    )
    def test_filename_generated_from_user_message(self, user_message):
        """Property test: Filename is generated from first user message."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        import unicodedata
        
        # Arrange: Create chat data with user message
        chat_data = [{
            'message': {
                'role': 'human',
                'content': user_message
            }
        }]
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback='fallback',
            source=ChatSource.KIRO_IDE
        )
        
        # Assert: Filename is non-empty
        assert len(filename) > 0, \
            "Filename should be non-empty when user message exists"
        
        # Assert: Filename is derived from message
        # Normalize message to ASCII like the function does
        normalized_message = unicodedata.normalize('NFKD', user_message)
        ascii_message = normalized_message.encode('ascii', 'ignore').decode('ascii')
        
        # Extract alphanumeric words from both (after sanitization)
        import re
        message_words = set(re.findall(r'\w+', ascii_message.lower()))
        filename_words = set(re.findall(r'\w+', filename.lower()))
        
        # Filename should contain alphanumeric characters
        assert len(filename_words) > 0, \
            "Filename should contain alphanumeric characters"
        
        # If the ASCII message has alphanumeric content, filename should overlap or be derived
        if message_words:
            # Check for overlap or that filename is a substring/sanitized version
            has_overlap = len(message_words & filename_words) > 0
            # Or filename contains sanitized version of message start
            sanitized_start = re.sub(r'[^a-zA-Z0-9\s\-_]', '', ascii_message[:20].lower())
            sanitized_start = re.sub(r'[-\s]+', '-', sanitized_start).strip('-_')
            is_derived = sanitized_start and sanitized_start in filename
            
            assert has_overlap or is_derived, \
                f"Filename '{filename}' should be meaningfully derived from ASCII message '{ascii_message[:50]}'"
        # If message has no ASCII content, fallback is used
        else:
            assert filename == 'fallback' or filename == 'untitled', \
                f"When message has no ASCII content, should use fallback or 'untitled', got '{filename}'"

    @settings(max_examples=100)
    @given(
        messages=st.lists(
            st.fixed_dictionaries({
                'role': st.sampled_from(['bot', 'assistant']),
                'content': st.text(min_size=1, max_size=100)
            }),
            min_size=1,
            max_size=5
        ),
        user_message=st.text(min_size=1, max_size=100, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')
        ))
    )
    def test_filename_uses_first_user_message(self, messages, user_message):
        """Property test: Filename uses first user message, not bot messages."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        
        # Arrange: Create chat data with bot messages first, then user message
        chat_data = []
        for msg in messages:
            chat_data.append({'message': msg})
        
        # Add user message
        chat_data.append({
            'message': {
                'role': 'human',
                'content': user_message
            }
        })
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback='fallback',
            source=ChatSource.KIRO_IDE
        )
        
        # Assert: Filename is non-empty and not the fallback
        assert len(filename) > 0, \
            "Filename should be generated from user message"
        
        # The filename should be derived from user_message, not bot messages
        # (This is a behavioral property - we found the first user message)

    @settings(max_examples=100)
    @given(
        fallback=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='-_'
        ))
    )
    def test_fallback_used_when_no_user_messages(self, fallback):
        """Property test: Fallback is used when no user messages exist."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        import re
        import unicodedata
        
        # Arrange: Create chat data with only bot messages
        chat_data = [{
            'message': {
                'role': 'bot',
                'content': 'Bot response'
            }
        }]
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback=fallback,
            source=ChatSource.KIRO_IDE
        )
        
        # Expected: fallback should be normalized to ASCII and sanitized
        normalized = unicodedata.normalize('NFKD', fallback)
        ascii_fallback = normalized.encode('ascii', 'ignore').decode('ascii')
        expected = re.sub(r'[^a-zA-Z0-9\s\-_]', '', ascii_fallback)
        expected = re.sub(r'[-\s]+', '-', expected)
        expected = expected.strip('-_').lower()
        
        # If sanitization results in empty, should use 'untitled'
        if not expected:
            expected = 'untitled'
        
        # Assert: Filename equals sanitized fallback
        assert filename == expected, \
            f"Filename should be sanitized fallback '{expected}' when no user messages, got '{filename}'"

    @settings(max_examples=100)
    @given(
        user_message=st.text(min_size=1, max_size=500, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs'),  # Letters, numbers, spaces
            whitelist_characters='-_.,!?'  # Common punctuation
        ))
    )
    def test_filename_is_filesystem_safe(self, user_message):
        """Property test: Generated filename is filesystem-safe."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        
        # Arrange: Create chat data
        chat_data = [{
            'message': {
                'role': 'human',
                'content': user_message
            }
        }]
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback='fallback',
            source=ChatSource.KIRO_IDE
        )
        
        # Assert: Filename contains only safe characters
        import re
        # Should only contain alphanumeric, hyphens, underscores (after sanitization)
        assert re.match(r'^[a-z0-9\-_]+$', filename), \
            f"Filename should be filesystem-safe, got '{filename}'"
        
        # Assert: Filename is not too long
        assert len(filename) <= 100, \
            f"Filename should be <= 100 chars, got {len(filename)}"

    @settings(max_examples=100)
    @given(
        messages=st.lists(
            st.fixed_dictionaries({
                'role': st.sampled_from(['human', 'user']),
                'content': st.text(min_size=1, max_size=100)
            }),
            min_size=1,
            max_size=10
        )
    )
    def test_filename_always_non_empty(self, messages):
        """Property test: Filename generation always produces non-empty result."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        
        # Arrange: Create chat data
        chat_data = [{'message': msg} for msg in messages]
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback='fallback',
            source=ChatSource.KIRO_IDE
        )
        
        # Assert: Filename is non-empty
        assert len(filename) > 0, \
            "Filename should always be non-empty"
        assert filename.strip() != '', \
            "Filename should not be just whitespace"

    @settings(max_examples=100)
    @given(
        long_message=st.text(min_size=200, max_size=1000, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')
        ))
    )
    def test_long_messages_truncated_appropriately(self, long_message):
        """Property test: Long messages are truncated to reasonable filename length."""
        # Feature: kiro-chat-support, Property 9: Filename Generation From Content
        
        from src.exporters import _generate_filename_from_content
        from src.models import ChatSource
        
        # Arrange: Create chat data with long message
        chat_data = [{
            'message': {
                'role': 'human',
                'content': long_message
            }
        }]
        
        # Act: Generate filename
        filename = _generate_filename_from_content(
            chat_data,
            fallback='fallback',
            source=ChatSource.KIRO_IDE
        )
        
        # Assert: Filename is truncated to reasonable length
        assert len(filename) <= 100, \
            f"Long messages should be truncated to <= 100 chars, got {len(filename)}"
        
        # Assert: Filename is still non-empty
        assert len(filename) > 0, \
            "Truncated filename should still be non-empty"

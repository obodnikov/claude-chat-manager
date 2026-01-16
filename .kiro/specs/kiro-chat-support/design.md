# Design Document: Kiro Chat Support

## Overview

This design extends the Claude Chat Manager to support Kiro IDE chat files alongside existing Claude Desktop support. The architecture follows the existing modular pattern, adding a new parser module for Kiro's JSON format while reusing existing export, display, and filtering infrastructure.

The key design principle is **maximum code reuse** - Kiro support is implemented as an additional data source that feeds into the existing processing pipeline, with format-specific parsing isolated to dedicated modules.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    claude-chat-manager.py                       │
│                      (Main Entry Point)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         ┌────▼────┐                  ┌────▼────┐
         │   CLI   │                  │ Config  │
         │ (cli.py)│                  │(config) │
         └────┬────┘                  └────┬────┘
              │                             │
              │    ┌────────────────────────┘
              │    │
    ┌─────────┴────┴─────────────────────────────────┐
    │                                                │
┌───▼────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Projects│  │  Parser  │  │  Kiro    │  │Exporters │
│        │  │ (Claude) │  │  Parser  │  │          │
└───┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
    │            │              │              │
    └────────────┴──────────────┴──────────────┘
                        │
               ┌────────┴────────┐
               │                 │
          ┌────▼────┐      ┌────▼────┐
          │Formatters│      │ Models  │
          └─────────┘      └─────────┘
```

### New Components

1. **kiro_parser.py** - Parses Kiro `.chat` JSON files
2. **kiro_projects.py** - Discovers Kiro workspaces and sessions
3. **Extended models.py** - ChatSource enum and extended data classes

### Modified Components

1. **config.py** - Add Kiro directory configuration
2. **projects.py** - Unified project listing with source filtering
3. **formatters.py** - Handle Kiro's structured content format
4. **cli.py** - Source filtering in interactive browser
5. **exporters.py** - Minor updates for source-aware exports

## Components and Interfaces

### 1. Kiro Parser Module (`src/kiro_parser.py`)

```python
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class KiroChatSession:
    """Represents a parsed Kiro chat session."""
    session_id: str
    title: str
    messages: List[Dict[str, Any]]
    context: List[Dict[str, Any]]
    execution_id: Optional[str]
    created_at: Optional[str]

def parse_kiro_chat_file(file_path: Path) -> KiroChatSession:
    """Parse a Kiro .chat file and return structured session data.
    
    Args:
        file_path: Path to the .chat file
        
    Returns:
        KiroChatSession with parsed data
        
    Raises:
        ChatFileNotFoundError: If file doesn't exist
        InvalidChatFileError: If JSON is malformed
    """
    pass

def extract_kiro_messages(chat_data: Dict[str, Any]) -> List[ChatMessage]:
    """Extract ChatMessage objects from Kiro chat data.
    
    Args:
        chat_data: Parsed JSON from .chat file
        
    Returns:
        List of ChatMessage objects
    """
    pass

def normalize_kiro_content(content: Any) -> str:
    """Normalize Kiro's structured content to plain text.
    
    Handles both string content and array of content blocks.
    
    Args:
        content: Message content (string or list of blocks)
        
    Returns:
        Normalized string content
    """
    pass
```

### 2. Kiro Projects Module (`src/kiro_projects.py`)

```python
from pathlib import Path
from typing import List, Optional
import base64

@dataclass
class KiroWorkspace:
    """Represents a Kiro workspace with its sessions."""
    workspace_path: str
    workspace_name: str
    sessions: List[KiroSession]
    session_count: int
    last_modified: str

@dataclass  
class KiroSession:
    """Represents a single Kiro chat session."""
    session_id: str
    title: str
    date_created: str
    workspace_directory: str
    chat_file_path: Path

def discover_kiro_workspaces(kiro_data_dir: Path) -> List[KiroWorkspace]:
    """Discover all Kiro workspaces and their sessions.
    
    Args:
        kiro_data_dir: Path to Kiro data directory
        
    Returns:
        List of KiroWorkspace objects
    """
    pass

def decode_workspace_path(encoded_path: str) -> str:
    """Decode base64-encoded workspace path to human-readable name.
    
    Args:
        encoded_path: Base64-encoded workspace path
        
    Returns:
        Decoded workspace path string
    """
    pass

def list_kiro_sessions(workspace_dir: Path) -> List[KiroSession]:
    """List all chat sessions in a Kiro workspace.
    
    Args:
        workspace_dir: Path to workspace-sessions subdirectory
        
    Returns:
        List of KiroSession objects
    """
    pass
```

### 3. Extended Models (`src/models.py`)

```python
from enum import Enum

class ChatSource(Enum):
    """Identifies the source of a chat or project."""
    CLAUDE_DESKTOP = "claude"
    KIRO_IDE = "kiro"
    UNKNOWN = "unknown"

@dataclass
class ProjectInfo:
    """Extended to include source information."""
    name: str
    path: Path
    file_count: int
    total_messages: int
    last_modified: str
    sort_timestamp: Optional[float] = None
    source: ChatSource = ChatSource.UNKNOWN
    # Kiro-specific fields
    workspace_path: Optional[str] = None
    session_ids: Optional[List[str]] = None

@dataclass
class ChatMessage:
    """Extended to include source and structured content."""
    role: str
    content: Any  # str or List[Dict] for Kiro
    timestamp: Optional[str] = None
    tool_result: Optional[Any] = None
    source: ChatSource = ChatSource.UNKNOWN
    # Kiro-specific fields
    execution_id: Optional[str] = None
    context_items: Optional[List[Dict]] = None
```

### 4. Configuration Extensions (`src/config.py`)

```python
class Config:
    # Existing properties...
    
    @property
    def kiro_data_dir(self) -> Path:
        """Get Kiro data directory with OS-specific defaults."""
        custom_dir = os.getenv('KIRO_DATA_DIR')
        if custom_dir:
            return Path(custom_dir)
        return self._get_default_kiro_dir()
    
    @property
    def chat_source_filter(self) -> Optional[ChatSource]:
        """Get configured chat source filter."""
        source = os.getenv('CHAT_SOURCE', 'claude').lower()  # Default to claude
        if source == 'claude':
            return ChatSource.CLAUDE_DESKTOP
        elif source == 'kiro':
            return ChatSource.KIRO_IDE
        elif source == 'all':
            return None  # None means show all
        return ChatSource.CLAUDE_DESKTOP  # Default fallback
    
    def _get_default_kiro_dir(self) -> Path:
        """Get OS-specific default Kiro data directory."""
        if sys.platform == 'win32':
            base = Path(os.environ.get('APPDATA', ''))
            return base / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        elif sys.platform == 'darwin':
            return Path.home() / 'Library' / 'Application Support' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
        else:  # Linux and others
            return Path.home() / '.config' / 'Kiro' / 'User' / 'globalStorage' / 'kiro.kiroagent'
```

### 5. CLI Flag Extensions (`claude-chat-manager.py`)

```python
# Add new argument for source selection
parser.add_argument(
    '--source', '-s',
    choices=['claude', 'kiro', 'all'],
    default='claude',
    help='Chat source to use: claude (default), kiro, or all'
)

# Usage examples:
# python claude-chat-manager.py                    # Claude only (default)
# python claude-chat-manager.py --source kiro      # Kiro only
# python claude-chat-manager.py --source all       # Both sources
# python claude-chat-manager.py -s kiro "Project"  # Export Kiro project
```

The `--source` flag takes precedence over the `CHAT_SOURCE` environment variable, allowing users to override the default on a per-command basis.

## Data Models

### Kiro Chat File Structure

```json
{
  "executionId": "uuid",
  "actionId": "act",
  "context": [
    {"type": "fileTree", "target": 50, ...}
  ],
  "validations": {"editorProblems": {}},
  "chat": [
    {
      "role": "human",
      "content": "string or array of content blocks"
    },
    {
      "role": "bot", 
      "content": "response text"
    }
  ]
}
```

### Kiro Content Block Types

```json
// Text block
{"type": "text", "text": "message content"}

// Image reference
{"type": "image_url", "image_url": {"url": "..."}}

// Tool use
{"type": "tool_use", "name": "toolName", "input": {...}}
```

### Workspace Sessions Structure

```
workspace-sessions/
├── {base64-encoded-workspace-path}/
│   ├── sessions.json           # Session metadata
│   ├── {session-id}.json       # Session chat history (UUID-based)
│   └── ...
```

Note: Session files use `.json` extension with UUID-based filenames (e.g., `6f77fc91-dac4-4a08-bb6d-a0a0170a7c52.json`).

### sessions.json Format

```json
[
  {
    "sessionId": "uuid",
    "title": "Session title (truncated first message)",
    "dateCreated": "timestamp-ms",
    "workspaceDirectory": "C:\\path\\to\\workspace"
  }
]
```

### Execution Log Structure

Kiro stores full bot responses in execution log files within hash-named subdirectories:

```
workspace-sessions/
├── {base64-encoded-workspace-path}/
│   ├── sessions.json
│   ├── {session-id}.chat           # Brief bot responses
│   └── {hash-subdir}/              # Execution log directory
│       └── {execution-id}          # No extension, JSON content
```

**Execution Log File Format:**

```json
{
  "executionId": "uuid-matching-chat-file",
  "messagesFromExecutionId": [
    {
      "role": "bot",
      "entries": [
        {
          "type": "text",
          "text": "Full bot response text here..."
        },
        {
          "type": "toolUse",
          "name": "readFile",
          "input": {"path": "src/config.py"}
        }
      ]
    }
  ]
}
```

## Execution Log Enrichment Design

### Problem Statement

Kiro `.chat` files only contain brief bot acknowledgments like "On it." or "I'll help with that." The full bot responses are stored separately in execution log files. Without enrichment, exported chats would be missing the actual assistant content.

### Solution Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Export Pipeline                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
         ┌──────────────────────────────────────┐
         │ 1. Build Execution Log Index         │
         │    - Scan hash-named subdirectories  │
         │    - Map executionId → file path     │
         └──────────────────┬───────────────────┘
                             │
                             ▼
         ┌──────────────────────────────────────┐
         │ 2. Load .chat File                   │
         │    - Parse JSON structure            │
         │    - Extract executionId             │
         └──────────────────┬───────────────────┘
                             │
                             ▼
         ┌──────────────────────────────────────┐
         │ 3. Find Execution Log                │
         │    - Lookup in index                 │
         │    - Fall back to directory scan     │
         └──────────────────┬───────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         Found                         Not Found
              │                             │
              ▼                             ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│ 4a. Extract Bot         │    │ 4b. Use Original        │
│     Responses           │    │     Content             │
│ - Parse messagesFrom... │    │ - Log warning           │
│ - Extract text entries  │    │ - Continue with brief   │
│ - Replace in chat data  │    │   acknowledgments       │
└─────────────┬───────────┘    └─────────────┬───────────┘
              │                             │
              └──────────────┬──────────────┘
                             │
                             ▼
         ┌──────────────────────────────────────┐
         │ 5. Return Enriched Messages          │
         │    + List of Errors/Warnings         │
         └──────────────────────────────────────┘
```

### Key Functions

```python
def find_execution_log_dirs(workspace_dir: Path) -> List[Path]:
    """Find all hash-named subdirectories containing execution logs."""
    pass

def build_execution_log_index(workspace_dir: Path) -> Dict[str, Path]:
    """Build mapping from executionId to log file path for fast lookups."""
    pass

def parse_execution_log(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse an execution log file (no extension, JSON content)."""
    pass

def extract_bot_responses_from_execution_log(
    execution_log: Dict[str, Any]
) -> List[str]:
    """Extract full bot text responses from messagesFromExecutionId array."""
    pass

def enrich_chat_with_execution_log(
    chat_data: Dict[str, Any],
    workspace_dir: Path,
    execution_log_index: Optional[Dict[str, Path]] = None
) -> Tuple[Dict[str, Any], List[str]]:
    """Replace brief bot responses with full text from execution logs."""
    pass

def extract_kiro_messages_enriched(
    chat_data: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    execution_log_index: Optional[Dict[str, Path]] = None
) -> Tuple[List[ChatMessage], List[str]]:
    """Main extraction function with automatic enrichment."""
    pass
```

### Error Handling Strategy

The enrichment process is designed to be **resilient** - it should never cause an export to fail completely.

| Error Condition | Handling | User Impact |
|-----------------|----------|-------------|
| No executionId in chat | Log warning, use original content | Brief responses in export |
| Execution log not found | Log warning, use original content | Brief responses in export |
| Execution log corrupted | Log error, use original content | Brief responses in export |
| No bot responses in log | Log warning, use original content | Brief responses in export |
| Partial enrichment | Enrich what's possible | Mixed content quality |

**Error Reporting:**
- Errors are collected and returned alongside the enriched data
- Errors are logged at WARNING level (visible in verbose mode)
- Errors do NOT appear in the exported markdown files
- Export continues even when enrichment fails

### Performance Considerations

1. **Index Building**: Build execution log index once per workspace export, not per chat
2. **Lazy Loading**: Only parse execution logs when needed
3. **Early Exit**: Skip enrichment if no executionId present
4. **Batch Operations**: Process all chats in a workspace with shared index



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Kiro Chat Parsing Preserves Message Structure

*For any* valid Kiro `.chat` file containing N messages, parsing the file and extracting messages SHALL produce exactly N ChatMessage objects, each with role and content fields populated.

**Validates: Requirements 1.1, 1.2**

### Property 2: Metadata Preservation Through Parsing

*For any* Kiro chat file containing tool calls or context items, parsing and extracting messages SHALL preserve all tool call data and context items in the resulting ChatMessage objects.

**Validates: Requirements 1.3**

### Property 3: Invalid JSON Produces Descriptive Error

*For any* string that is not valid JSON, attempting to parse it as a Kiro chat file SHALL raise an InvalidChatFileError with a message containing information about the parse failure.

**Validates: Requirements 1.4**

### Property 4: Base64 Workspace Path Round-Trip

*For any* valid filesystem path string, encoding it to base64 and then decoding SHALL produce the original path string (accounting for URL-safe base64 encoding).

**Validates: Requirements 2.2**

### Property 5: Session Discovery Completeness

*For any* Kiro workspace directory containing a valid `sessions.json` with N session entries, discovering sessions SHALL return exactly N KiroSession objects, each with sessionId, title, and dateCreated populated.

**Validates: Requirements 2.4, 2.5**

### Property 6: Source Filtering Correctness

*For any* list of projects from mixed sources (Claude and Kiro), filtering by a specific source SHALL return only projects where the source field matches the filter, and the count SHALL be less than or equal to the original list size.

**Validates: Requirements 3.3, 3.5**

### Property 7: Project Source Indication

*For any* project returned by the unified project listing, the source field SHALL be either ChatSource.CLAUDE_DESKTOP or ChatSource.KIRO_IDE (never UNKNOWN for discovered projects).

**Validates: Requirements 3.2**

### Property 8: Export Format Support

*For any* valid Kiro chat session and any supported export format (pretty, markdown, book, wiki), exporting SHALL complete without raising an exception and produce non-empty output.

**Validates: Requirements 4.1**

### Property 9: Filename Generation From Content

*For any* Kiro chat session with either a title or at least one user message, generating a filename SHALL produce a non-empty string derived from the title or first user message content.

**Validates: Requirements 4.3**

### Property 10: Content Normalization Transparency

*For any* message content that is either a string or an array of content blocks, normalizing the content SHALL produce a non-empty string, and for string inputs, the output SHALL equal the input.

**Validates: Requirements 8.1, 8.4**

### Property 11: Special Block Formatting

*For any* Kiro message containing tool use blocks or image references, formatting the message SHALL produce output that contains distinct markers for these special blocks (e.g., "[Tool: name]" or "[Image]").

**Validates: Requirements 8.2, 8.3**

## Error Handling

### Exception Hierarchy

```python
# Extend existing exceptions.py

class KiroError(ChatManagerError):
    """Base exception for Kiro-related errors."""
    pass

class KiroDirectoryNotFoundError(KiroError):
    """Raised when Kiro data directory doesn't exist."""
    pass

class InvalidKiroChatError(KiroError):
    """Raised when a .chat file contains invalid data."""
    pass

class KiroSessionNotFoundError(KiroError):
    """Raised when a referenced session doesn't exist."""
    pass
```

### Error Scenarios

| Scenario | Exception | Recovery |
|----------|-----------|----------|
| Kiro directory not found | KiroDirectoryNotFoundError | Log warning, continue with Claude-only |
| Invalid .chat JSON | InvalidKiroChatError | Skip file, log error, continue |
| Missing sessions.json | KiroSessionNotFoundError | Skip workspace, log warning |
| Corrupted base64 path | ValueError | Use encoded path as fallback name |
| Empty chat file | InvalidKiroChatError | Skip file, log warning |

### Graceful Degradation

When Kiro support encounters errors:
1. Log the error with full context
2. Continue processing other files/workspaces
3. Display partial results with warning to user
4. Never crash the entire application due to Kiro-specific errors

## Testing Strategy

### Dual Testing Approach

This feature requires both unit tests and property-based tests:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all valid inputs

### Property-Based Testing Configuration

- **Library**: `hypothesis` (Python property-based testing library)
- **Minimum iterations**: 100 per property test
- **Tag format**: `# Feature: kiro-chat-support, Property N: {property_text}`

### Test Categories

#### Unit Tests (`tests/test_kiro_parser.py`)

1. Parse valid .chat file with simple messages
2. Parse .chat file with structured content blocks
3. Parse .chat file with tool calls
4. Handle missing file (ChatFileNotFoundError)
5. Handle invalid JSON (InvalidKiroChatError)
6. Handle empty chat array
7. Normalize string content (passthrough)
8. Normalize array content (concatenation)
9. Handle image blocks in content

#### Unit Tests (`tests/test_kiro_projects.py`)

1. Discover workspaces from valid directory structure
2. Decode base64 workspace paths
3. Parse sessions.json correctly
4. Handle missing sessions.json
5. Handle empty workspace directory
6. Sort sessions by date

#### Property Tests (`tests/test_kiro_properties.py`)

1. **Property 1**: Message count preservation
2. **Property 3**: Invalid JSON error handling
3. **Property 4**: Base64 round-trip
4. **Property 5**: Session discovery completeness
5. **Property 6**: Source filtering correctness
6. **Property 10**: Content normalization transparency

### Test Data Generators (Hypothesis)

```python
from hypothesis import strategies as st

# Generate valid Kiro message
kiro_message = st.fixed_dictionaries({
    'role': st.sampled_from(['human', 'bot', 'tool']),
    'content': st.one_of(
        st.text(min_size=1),  # String content
        st.lists(st.fixed_dictionaries({  # Array content
            'type': st.just('text'),
            'text': st.text(min_size=1)
        }), min_size=1)
    )
})

# Generate valid Kiro chat structure
kiro_chat = st.fixed_dictionaries({
    'executionId': st.uuids().map(str),
    'chat': st.lists(kiro_message, min_size=1, max_size=50)
})

# Generate valid filesystem paths
filesystem_path = st.from_regex(r'[A-Za-z]:\\[A-Za-z0-9_\\]+', fullmatch=True)
```

### Integration Tests

1. End-to-end: Discover Kiro workspace → Parse chats → Export to markdown
2. Mixed source listing: Combine Claude and Kiro projects
3. Interactive browser with Kiro source filter
4. Batch export of Kiro workspace

### Test File Structure

```
tests/
├── test_kiro_parser.py          # Unit tests for parsing
├── test_kiro_projects.py        # Unit tests for discovery
├── test_kiro_properties.py      # Property-based tests
├── test_kiro_integration.py     # Integration tests
└── fixtures/
    └── kiro/
        ├── valid_chat.chat
        ├── structured_content.chat
        ├── invalid.chat
        └── workspace_sessions/
            └── sessions.json
```

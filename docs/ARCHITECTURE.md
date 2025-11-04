# Architecture Documentation

## Overview

Claude Chat Manager is a modular Python application for browsing and exporting Claude Desktop chat files. The codebase is organized into focused modules following clean architecture principles.

## Project Structure

```
claude-chat-manager/
├── src/                      # Source code
│   ├── __init__.py          # Package initialization
│   ├── cli.py               # Command-line interface (~300 lines)
│   ├── colors.py            # Terminal colors (~70 lines)
│   ├── config.py            # Configuration management (~90 lines)
│   ├── display.py           # Terminal display utilities (~150 lines)
│   ├── exceptions.py        # Custom exceptions (~50 lines)
│   ├── exporters.py         # Export functionality (~230 lines)
│   ├── formatters.py        # Message formatting (~230 lines)
│   ├── models.py            # Data models (~60 lines)
│   ├── parser.py            # JSONL parsing (~90 lines)
│   ├── projects.py          # Project management (~180 lines)
│   └── search.py            # Search functionality (~120 lines)
├── tests/                    # Test suite
│   ├── test_config.py
│   ├── test_exceptions.py
│   └── test_formatters.py
├── docs/                     # Documentation
│   └── ARCHITECTURE.md
├── claude-chat-manager.py    # Main entry point
├── requirements.txt          # Dependencies
├── setup.py                  # Package setup
└── pytest.ini                # Test configuration
```

## Module Responsibilities

### Core Modules

**cli.py** - Command-line interface
- Interactive browser implementation
- Menu navigation
- User input handling
- Integrates all other modules

**config.py** - Configuration management
- Environment variable handling
- Default values
- Configuration validation
- Single source of truth for settings

**exceptions.py** - Custom exceptions
- Application-specific error types
- Hierarchical exception structure
- Clear error messages

### Data Modules

**models.py** - Data models
- ProjectInfo dataclass
- ChatMessage dataclass
- Type-safe data structures

**parser.py** - JSONL parsing
- File reading and parsing
- JSON validation
- Message extraction

### Display Modules

**colors.py** - Terminal colors
- ANSI color codes
- Color utility functions
- Role-based coloring

**display.py** - Terminal display
- Pager implementation (less-like)
- Terminal size detection
- Keyboard input handling

**formatters.py** - Message formatting
- Timestamp formatting
- Content formatting
- Tool use formatting
- Name cleaning utilities

### Business Logic Modules

**projects.py** - Project management
- Project discovery
- Project information gathering
- Project searching
- File listing

**search.py** - Search functionality
- Content search across files
- Result aggregation
- Preview generation

**exporters.py** - Export functionality
- Multiple format support (pretty, markdown, book, raw)
- File export operations
- Batch export support

## Design Principles

### 1. Separation of Concerns
Each module has a single, well-defined responsibility. For example:
- `parser.py` only handles JSONL parsing
- `display.py` only handles terminal output
- `exporters.py` only handles export operations

### 2. Dependency Injection
Configuration is injected through the `config` module rather than hardcoded values.

### 3. Type Safety
All functions include type hints for better IDE support and early error detection.

### 4. Error Handling
- Custom exceptions provide clear error context
- Logging used throughout for debugging
- User-friendly error messages

### 5. Testability
- Small, focused functions are easy to test
- Minimal side effects
- Clear input/output contracts

## Data Flow

### Interactive Browser Flow

```
main() → interactive_browser()
         ↓
         list_all_projects() → get_project_info()
         ↓
         User selects project
         ↓
         browse_project_interactive()
         ↓
         view_chat_file() → parse_jsonl_file()
                           → export_chat_pretty()
                           → display_with_pager()
```

### Export Flow

```
export_chat_to_file()
  ↓
  parse_jsonl_file()
  ↓
  export_chat_markdown() / export_chat_book()
  ↓
  format_content() + format_tool_result()
  ↓
  Write to file
```

## Configuration

Configuration is managed through environment variables:

- `CLAUDE_PROJECTS_DIR` - Custom projects directory
- `CLAUDE_LOG_LEVEL` - Logging verbosity
- `CLAUDE_DEFAULT_FORMAT` - Default export format
- `CLAUDE_PAGE_HEIGHT` - Terminal page height

See `.env.example` for all options.

## Logging

Logging is implemented throughout:
- File: `claude-chat-manager.log`
- Console: Configurable via `CLAUDE_LOG_LEVEL`
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Testing

Tests are organized by module:
- `test_config.py` - Configuration tests
- `test_exceptions.py` - Exception tests
- `test_formatters.py` - Formatter tests

Run tests with:
```bash
pytest
pytest --cov=src  # With coverage
```

## Extension Points

### Adding New Export Formats

1. Add format function in `exporters.py`:
```python
def export_chat_custom(chat_data: List[Dict[str, Any]]) -> str:
    # Implementation
    pass
```

2. Update `export_chat_to_file()` to handle new format

3. Add format choice to CLI arguments

### Adding New Search Types

1. Add search function in `search.py`:
```python
def search_by_custom(search_term: str) -> List[SearchResult]:
    # Implementation
    pass
```

2. Add CLI command in `cli.py`

3. Wire up in `main()` argument parser

## Performance Considerations

- File reading is done lazily where possible
- Large content uses paging to avoid memory issues
- Message counting is optimized with simple line counting
- Search stops at first match per file to improve speed

## Security Considerations

- No remote connections
- Only reads local JSONL files
- No code execution from chat content
- Path traversal prevented by Path validation

## Future Improvements

- Async file operations for better performance
- Full-text search with indexing
- Export to additional formats (PDF, HTML)
- Chat statistics and analytics
- GUI interface option

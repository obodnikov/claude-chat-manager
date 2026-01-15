# Implementation Plan: Kiro Chat Support

## Overview

This implementation adds Kiro IDE chat support to Claude Chat Manager with maximum code reuse. The approach is incremental: first add core parsing, then discovery, then integrate with existing infrastructure.

## Tasks

- [x] 1. Extend data models for multi-source support
  - [x] 1.1 Add ChatSource enum to models.py
    - Create `ChatSource` enum with CLAUDE_DESKTOP, KIRO_IDE, UNKNOWN values
    - _Requirements: 7.1, 7.2_
  - [x] 1.2 Extend ChatMessage dataclass with source field
    - Add optional `source: ChatSource` field
    - Add optional `execution_id` and `context_items` fields for Kiro
    - _Requirements: 7.1, 7.3_
  - [x] 1.3 Extend ProjectInfo dataclass with source field
    - Add `source: ChatSource` field
    - Add optional `workspace_path` and `session_ids` fields for Kiro
    - _Requirements: 7.2_
  - [x] 1.4 Write unit tests for extended models
    - Test ChatSource enum values
    - Test ChatMessage with source field
    - Test ProjectInfo with Kiro-specific fields
    - _Requirements: 7.1, 7.2_

- [x] 2. Implement Kiro parser module
  - [x] 2.1 Create src/kiro_parser.py with basic structure
    - Create KiroChatSession dataclass
    - Implement `parse_kiro_chat_file()` function
    - _Requirements: 1.1, 1.2_
  - [x] 2.2 Implement message extraction
    - Implement `extract_kiro_messages()` function
    - Handle both string and array content formats
    - _Requirements: 1.2, 1.3_
  - [x] 2.3 Implement content normalization
    - Implement `normalize_kiro_content()` function
    - Handle text blocks, tool use blocks, image references
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 2.4 Implement error handling
    - Raise ChatFileNotFoundError for missing files
    - Raise InvalidChatFileError for invalid JSON
    - _Requirements: 1.4, 1.5_
  - [x] 2.5 Write unit tests for kiro_parser
    - Test parsing valid .chat files
    - Test structured content handling
    - Test error cases
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 2.6 Write property test for message count preservation
    - **Property 1: Kiro Chat Parsing Preserves Message Structure**
    - **Validates: Requirements 1.1, 1.2**
  - [x] 2.7 Write property test for content normalization
    - **Property 10: Content Normalization Transparency**
    - **Validates: Requirements 8.1, 8.4**

- [x] 3. Checkpoint - Ensure parser tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Kiro projects discovery
  - [x] 4.1 Create src/kiro_projects.py with basic structure
    - Create KiroWorkspace and KiroSession dataclasses
    - Implement `discover_kiro_workspaces()` function
    - _Requirements: 2.1_
  - [x] 4.2 Implement base64 path decoding
    - Implement `decode_workspace_path()` function
    - Handle URL-safe base64 encoding
    - _Requirements: 2.2_
  - [x] 4.3 Implement sessions.json parsing
    - Implement `list_kiro_sessions()` function
    - Parse session metadata (id, title, dateCreated, workspaceDirectory)
    - _Requirements: 2.4, 2.5_
  - [x] 4.4 Implement workspace metadata extraction
    - Calculate session count, last modified date
    - Extract human-readable workspace name
    - _Requirements: 2.3_
  - [x] 4.5 Write unit tests for kiro_projects
    - Test workspace discovery
    - Test base64 decoding
    - Test sessions.json parsing
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 4.6 Write property test for base64 round-trip
    - **Property 4: Base64 Workspace Path Round-Trip**
    - **Validates: Requirements 2.2**
  - [x] 4.7 Write property test for session discovery completeness
    - **Property 5: Session Discovery Completeness**
    - **Validates: Requirements 2.4, 2.5**

- [x] 5. Checkpoint - Ensure discovery tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Extend configuration for Kiro support
  - [x] 6.1 Add Kiro configuration properties to config.py
    - Add `kiro_data_dir` property with OS-specific defaults
    - Add `chat_source_filter` property
    - Implement `_get_default_kiro_dir()` method
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 6.2 Add directory validation
    - Validate Kiro directory exists before scanning
    - Log warning if directory not found
    - _Requirements: 5.5_
  - [x] 6.3 Update .env.example with Kiro settings
    - Add KIRO_DATA_DIR example
    - Add CHAT_SOURCE example
    - _Requirements: 5.1, 5.3_
  - [x] 6.4 Write unit tests for Kiro configuration
    - Test OS-specific default paths
    - Test environment variable overrides
    - Test source filter parsing
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 7. Add CLI source flag
  - [x] 7.1 Add --source argument to claude-chat-manager.py
    - Add argparse argument with choices ['claude', 'kiro', 'all']
    - Default to 'claude'
    - _Requirements: 3.1, 3.3_
  - [x] 7.2 Wire source flag to project listing
    - Pass source filter to project discovery functions
    - Filter results based on source
    - _Requirements: 3.3, 3.5_
  - [x] 7.3 Write unit tests for CLI source flag
    - Test default behavior (claude only)
    - Test --source kiro
    - Test --source all
    - _Requirements: 3.1, 3.3_

- [x] 8. Integrate Kiro with unified project listing
  - [x] 8.1 Update projects.py for multi-source support
    - Modify `list_all_projects()` to accept source filter
    - Add Kiro project discovery when source includes kiro
    - _Requirements: 3.1, 3.2_
  - [x] 8.2 Implement source-aware project merging
    - Combine Claude and Kiro projects when source is 'all'
    - Apply consistent sorting across sources
    - _Requirements: 3.4_
  - [x] 8.3 Add source indicator to project display
    - Show [Claude] or [Kiro] prefix in project listings
    - _Requirements: 3.2_
  - [x] 8.4 Write property test for source filtering
    - **Property 6: Source Filtering Correctness**
    - **Validates: Requirements 3.3, 3.5**
  - [x] 8.5 Write property test for source indication
    - **Property 7: Project Source Indication**
    - **Validates: Requirements 3.2**

- [x] 9. Checkpoint - Ensure integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Extend formatters for Kiro content
  - [x] 10.1 Update formatters.py for structured content
    - Handle array content blocks in message formatting
    - Add special formatting for tool use blocks
    - Add [Image] indicator for image references
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 10.2 Write property test for special block formatting
    - **Property 11: Special Block Formatting**
    - **Validates: Requirements 8.2, 8.3**

- [x] 11. Extend exporters for Kiro support
  - [x] 11.1 Update exporters.py for Kiro chats
    - Ensure all export formats work with Kiro messages
    - Use session title or first message for filenames
    - _Requirements: 4.1, 4.3_
  - [x] 11.2 Add verbose mode metadata preservation
    - Include execution IDs in verbose exports
    - Include context items in verbose exports
    - _Requirements: 4.4_
  - [x] 11.3 Implement batch export for Kiro workspaces
    - Export all sessions in a workspace to output directory
    - _Requirements: 4.5_
  - [x] 11.4 Write property test for export format support
    - **Property 8: Export Format Support**
    - **Validates: Requirements 4.1**
  - [x] 11.5 Write property test for filename generation
    - **Property 9: Filename Generation From Content**
    - **Validates: Requirements 4.3**

- [ ] 12. Update interactive browser for Kiro
  - [ ] 12.1 Update cli.py for source filtering
    - Add source filter to interactive browser
    - Show source indicator in project list
    - _Requirements: 6.1, 6.2_
  - [ ] 12.2 Update search to include Kiro chats
    - Search across both sources when enabled
    - _Requirements: 6.4_

- [ ] 13. Final checkpoint - Full test suite
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Documentation updates
  - [ ] 14.1 Update README.md with Kiro support
    - Document --source flag usage
    - Document KIRO_DATA_DIR configuration
    - Add examples for Kiro exports
  - [ ] 14.2 Update ARCHITECTURE.md
    - Add kiro_parser.py and kiro_projects.py to component list
    - Update data flow diagrams

## Notes

- All tasks are required for comprehensive implementation
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases

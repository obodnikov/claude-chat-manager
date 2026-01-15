# Requirements Document

## Introduction

This feature extends Claude Chat Manager to support Kiro IDE chat files alongside existing Claude Desktop support. The goal is to provide a unified interface for browsing, viewing, and exporting chat conversations from both Claude Desktop (JSONL format) and Kiro IDE (JSON `.chat` format) with maximum code reuse.

## Glossary

- **Chat_Manager**: The main application that browses and exports chat files
- **Kiro_Parser**: Module responsible for parsing Kiro IDE `.chat` files
- **Claude_Parser**: Existing module for parsing Claude Desktop JSONL files
- **Project_Discovery**: Module that discovers and lists available projects/workspaces
- **Workspace_Session**: Kiro's mapping between workspace directories and chat sessions
- **Chat_Source**: Enumeration identifying whether a chat originates from Claude Desktop or Kiro IDE

## Requirements

### Requirement 1: Kiro Chat File Parsing

**User Story:** As a user, I want to parse Kiro IDE chat files, so that I can view and export my Kiro conversations.

#### Acceptance Criteria

1. WHEN a `.chat` file is provided, THE Kiro_Parser SHALL parse it into a list of chat messages
2. WHEN parsing a Kiro chat file, THE Kiro_Parser SHALL extract role, content, and timestamp from each message
3. WHEN a Kiro chat file contains tool calls or context items, THE Kiro_Parser SHALL preserve this metadata
4. IF a `.chat` file contains invalid JSON, THEN THE Kiro_Parser SHALL raise an InvalidChatFileError with descriptive message
5. IF a `.chat` file does not exist, THEN THE Kiro_Parser SHALL raise a ChatFileNotFoundError

### Requirement 2: Kiro Project Discovery

**User Story:** As a user, I want to discover all my Kiro workspaces and their chat sessions, so that I can browse my conversation history.

#### Acceptance Criteria

1. THE Project_Discovery SHALL scan the Kiro data directory for workspace session folders
2. WHEN discovering Kiro projects, THE Project_Discovery SHALL decode base64-encoded workspace paths to human-readable names
3. WHEN listing Kiro projects, THE Project_Discovery SHALL display workspace directory name, session count, and last modified date
4. THE Project_Discovery SHALL read `sessions.json` to map session IDs to workspace directories
5. WHEN a workspace has multiple sessions, THE Project_Discovery SHALL list all sessions with their titles and creation dates

### Requirement 3: Unified Project Listing

**User Story:** As a user, I want to see both Claude Desktop and Kiro projects in a unified list, so that I can easily navigate all my AI conversations.

#### Acceptance Criteria

1. THE Chat_Manager SHALL support configurable data directories for both Claude Desktop and Kiro IDE
2. WHEN listing projects, THE Chat_Manager SHALL indicate the source (Claude Desktop or Kiro IDE) for each project
3. THE Chat_Manager SHALL allow filtering projects by source type
4. WHEN sorting projects, THE Chat_Manager SHALL use consistent sorting across both sources (by date, name, or message count)
5. WHERE the user specifies a source filter, THE Chat_Manager SHALL only display projects from that source

### Requirement 4: Kiro Chat Export

**User Story:** As a user, I want to export Kiro chats in the same formats as Claude Desktop chats, so that I have consistent documentation.

#### Acceptance Criteria

1. THE Exporters SHALL support exporting Kiro chats in all existing formats (pretty, markdown, book, wiki)
2. WHEN exporting Kiro chats, THE Exporters SHALL use the same formatting logic as Claude Desktop exports
3. WHEN generating filenames for Kiro exports, THE Exporters SHALL use session title or first user message
4. THE Exporters SHALL preserve Kiro-specific metadata (execution IDs, context items) in verbose export modes
5. WHEN batch exporting a Kiro workspace, THE Exporters SHALL export all sessions to the output directory

### Requirement 5: Configuration for Kiro Support

**User Story:** As a user, I want to configure the Kiro data directory location, so that I can use the tool with custom Kiro installations.

#### Acceptance Criteria

1. THE Config SHALL support `KIRO_DATA_DIR` environment variable for custom Kiro data location
2. THE Config SHALL auto-detect the default Kiro data directory based on operating system:
   - Windows: `%APPDATA%\Kiro\User\globalStorage\kiro.kiroagent\`
   - macOS: `~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/`
   - Linux: `~/.config/Kiro/User/globalStorage/kiro.kiroagent/`
3. THE Config SHALL support `CHAT_SOURCE` environment variable to set default source filter (claude, kiro, all)
4. WHEN both Claude and Kiro directories are configured, THE Chat_Manager SHALL scan both by default
5. THE Config SHALL validate that the detected or configured Kiro directory exists before scanning

### Requirement 6: Interactive Browser Kiro Support

**User Story:** As a user, I want to browse Kiro chats interactively, so that I can view conversations in the terminal.

#### Acceptance Criteria

1. WHEN browsing interactively, THE CLI SHALL display a source indicator (Claude/Kiro) for each project
2. THE CLI SHALL allow switching between Claude-only, Kiro-only, and combined views
3. WHEN viewing a Kiro chat, THE Display SHALL format messages consistently with Claude Desktop display
4. THE CLI SHALL support searching across both Claude Desktop and Kiro chats

### Requirement 7: Data Model Extension

**User Story:** As a developer, I want unified data models that work with both chat sources, so that the codebase remains maintainable.

#### Acceptance Criteria

1. THE ChatMessage model SHALL include an optional `source` field indicating origin (claude/kiro)
2. THE ProjectInfo model SHALL include a `source` field and support Kiro-specific metadata
3. THE Models SHALL support Kiro's structured content format (array of content blocks)
4. WHEN converting between formats, THE Models SHALL preserve all essential information

### Requirement 8: Kiro Message Content Handling

**User Story:** As a user, I want Kiro's structured message content to be properly displayed, so that I can read conversations naturally.

#### Acceptance Criteria

1. WHEN a Kiro message contains an array of content blocks, THE Formatters SHALL concatenate text blocks into readable content
2. WHEN a Kiro message contains tool use blocks, THE Formatters SHALL format them distinctly from regular text
3. WHEN a Kiro message contains image references, THE Formatters SHALL indicate image presence in text exports
4. THE Formatters SHALL handle both string content and structured content arrays transparently

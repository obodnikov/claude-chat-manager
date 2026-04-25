# Architecture Documentation

## 1. Purpose of This Document

This document serves as the **architectural source of truth** for Claude Chat Manager. It describes the system as it exists today, not as planned or imagined.

**What it does:**
- Maps repository structure to actual components
- Documents data flows and runtime behavior
- Defines stability zones (what's safe to change vs. risky)
- References AI coding rules (does NOT redefine them)
- Provides quick-start guidance for AI assistants

**What it does NOT do:**
- Define coding rules (see AI*.md files)
- Duplicate implementation details (see docs/)
- Prescribe future architecture

**Audience:** AI coding assistants, new developers, future maintainers

---

## 2. High-Level System Overview

**Project Type:** CLI tool for browsing and exporting Claude Desktop chat files

**Characteristics:**
- Single-user desktop application
- No network services (except optional LLM API calls)
- File-based data source (JSONL files)
- Interactive TUI + batch export modes

**Tech Stack:**
- Python 3.9+ (standard library focused)
- No web framework (pure CLI)
- Optional: OpenRouter API for AI title generation
- Testing: pytest, mypy, black

**Architecture Pattern:**

```
┌─────────────────────────────────────────────────────────┐
│                  claude-chat-manager.py                 │
│                    (Main Entry Point)                   │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    ┌────▼────┐            ┌────▼────┐
    │   CLI   │            │ Config  │
    │ (cli.py)│            │(config) │
    └────┬────┘            └─────────┘
         │
    ┌────┴────────────────────────────────────────────────┐
    │                                                     │
┌───▼────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌───▼────┐
│Projects│  │ Parser │  │  Kiro  │  │ Codex  │  │Exporters│
│        │  │(Claude)│  │ Parser │  │ Parser │  │        │
└────┬───┘  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
     │          │            │            │            │
     └──────────┴────────────┴────────────┴────────────┘
                          │
              ┌───────────┴───────────┐
              │           │           │
         ┌────▼────┐ ┌───▼─────┐ ┌───▼───┐
         │Formatters│ │ Models  │ │Display│
         └─────────┘ └─────────┘ └───────┘
```

---

## 3. Repository Structure

```
claude-chat-manager/
├── claude-chat-manager.py      # Main entry point (CLI arg parsing, logging setup)
├── sanitize-chats.py           # Post-processing tool for existing exports
├── merge-chats.py              # Intelligent chat merge utility
├── auto-export.py              # Full export+merge pipeline orchestrator (CLI)
├── claude-reader.py            # Legacy monolithic script (deprecated)
│
├── src/                        # Core application modules
│   ├── __init__.py
│   ├── cli.py                  # Interactive browser, menu navigation (~300 lines)
│   ├── colors.py               # ANSI color codes (~70 lines)
│   ├── config.py               # Environment variable loading (~400 lines)
│   ├── display.py              # Terminal pager, keyboard input (~150 lines)
│   ├── exceptions.py           # Custom exception hierarchy (~50 lines)
│   ├── exporters.py            # Export formats (markdown, book, wiki) (~600 lines)
│   ├── filters.py              # Chat filtering logic (trivial detection) (~200 lines)
│   ├── formatters.py           # Message formatting, timestamp parsing (~230 lines)
│   ├── kiro_parser.py          # Kiro IDE .chat file parsing (~200 lines)
│   ├── kiro_projects.py        # Kiro workspace/session discovery (~250 lines)
│   ├── codex_parser.py         # Codex CLI JSONL rollout parsing (~200 lines)
│   ├── codex_projects.py       # Codex project discovery by cwd (~150 lines)
│   ├── llm_client.py           # OpenRouter API client (~150 lines)
│   ├── models.py               # Data classes (ProjectInfo, ChatMessage, ChatSource) (~100 lines)
│   ├── parser.py               # JSONL file parsing (~90 lines)
│   ├── projects.py             # Project discovery, search (~180 lines)
│   ├── sanitizer.py            # Sensitive data detection/redaction (~500 lines)
│   ├── search.py               # Content search across chats (~120 lines)
│   ├── project_matcher.py      # Conversation project → filesystem folder matching (~950 lines)
│   ├── auto_exporter.py        # Auto-export pipeline orchestrator (~700 lines)
│   ├── chat_merger.py          # Intelligent chat file merging (fingerprinting)
│   ├── wiki_generator.py       # Wiki generation with LLM titles (~600 lines)
│   └── wiki_parser.py          # Parse existing wiki files (~200 lines)
│
├── tests/                      # Unit tests (pytest)
│   ├── test_cli_sanitization.py    # CLI sanitization integration tests
│   ├── test_cli_source_flag.py     # CLI --source flag tests
│   ├── test_config.py
│   ├── test_config_env.py          # Environment variable config tests
│   ├── test_exceptions.py
│   ├── test_file_discovery_integration.py  # File discovery integration tests
│   ├── test_formatters.py
│   ├── test_interactive_browser.py # Interactive browser tests
│   ├── test_kiro_export.py         # Kiro export integration tests
│   ├── test_kiro_parser.py         # Kiro parser unit tests
│   ├── test_kiro_projects.py       # Kiro projects unit tests
│   ├── test_kiro_properties.py     # Kiro property-based tests
│   ├── test_codex_parser.py        # Codex parser unit tests
│   ├── test_codex_projects.py      # Codex projects unit tests
│   ├── test_llm_client.py
│   ├── test_models.py              # Model tests including ChatSource
│   ├── test_sanitizer.py
│   ├── test_sanitize_chats.py
│   ├── test_wiki_generator.py
│   └── test_wiki_parser.py
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md         # This file
│   ├── BUILDING.md             # PyInstaller build instructions
│   ├── DEVELOPMENT.md          # Dev setup, testing, code style
│   ├── SANITIZATION.md         # Sanitization feature guide
│   ├── SANITIZATION_SPEC.md    # Technical sanitization details
│   ├── BOOK_MODE_ENHANCEMENTS.md  # Book export features
│   ├── CODEX_IMPLEMENTATION.md # Codex CLI implementation guide
│   └── chats/                  # Conversation history (implementation context)
│
├── .env.example                # Configuration template
├── requirements.txt            # Runtime dependencies (minimal)
├── requirements-dev.txt        # Development dependencies
├── setup.py                    # Package setup
├── pytest.ini                  # Test configuration
├── claude-chat-manager.spec    # PyInstaller spec for executable builds
├── AI.md                       # Global AI coding rules
├── CLAUDE.md                   # AI behavioral rules
└── README.md                   # User documentation
```

**Critical Paths:**
- **Entry point:** `claude-chat-manager.py` → `src/cli.py`
- **Claude data source:** `~/.claude/projects/*.jsonl` (configurable via `CLAUDE_PROJECTS_DIR`)
- **Kiro data source:** OS-specific Kiro directory (configurable via `KIRO_DATA_DIR`)
  - Windows: `%APPDATA%\Kiro\User\globalStorage\kiro.kiroagent\workspace-sessions\`
  - macOS: `~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/`
  - Linux: `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/`
- **Codex data source:** `~/.codex/sessions/` (configurable via `CODEX_DATA_DIR` or `CODEX_HOME`)
- **Config loading:** `.env` file in project root (loaded by `src/config.py`)
- **Logs:** `logs/claude-chat-manager.log`

---

## 4. Core Components

### 4.1 CLI & User Interface
**Modules:** `cli.py`, `display.py`, `colors.py`

**Responsibilities:**
- Interactive project browser with menu navigation
- Unix `less`-like pager for chat viewing
- Keyboard input handling (cross-platform)
- ANSI color output for terminal

**Key Functions:**
- `interactive_browser()` - Main menu loop
- `browse_project_interactive()` - Project chat selection
- `display_with_pager()` - Scrollable chat viewer

### 4.2 Data Layer (Claude Desktop)
**Modules:** `parser.py`, `models.py`, `projects.py`

**Responsibilities:**
- JSONL file parsing and validation
- Project discovery from filesystem
- Data models (ProjectInfo, ChatMessage, ChatSource)
- Message counting and metadata extraction

**Key Functions:**
- `parse_jsonl_file()` - Parse JSONL to Python dicts
- `list_all_projects()` - Discover all Claude projects
- `find_project_by_name()` - Fuzzy project search

### 4.2.1 Data Layer (Kiro IDE)
**Modules:** `kiro_parser.py`, `kiro_projects.py`

**Responsibilities:**
- Kiro `.chat` JSON file parsing
- Workspace and session discovery
- Base64 workspace path decoding
- Structured content normalization (array → string)
- Session metadata extraction from `sessions.json`
- Execution log enrichment (full bot responses)

**Key Classes:**
- `KiroChatSession` - Parsed Kiro chat session data
- `KiroWorkspace` - Workspace with sessions
- `KiroSession` - Individual session metadata

**Key Functions:**
- `parse_kiro_chat_file()` - Parse Kiro .chat JSON files
- `extract_kiro_messages()` - Extract ChatMessage objects from Kiro data
- `extract_kiro_messages_enriched()` - Extract with execution log enrichment
- `normalize_kiro_content()` - Convert structured content to plain text
- `discover_kiro_workspaces()` - Find all Kiro workspaces
- `decode_workspace_path()` - Decode base64 workspace paths
- `list_kiro_sessions()` - List sessions in a workspace
- `build_execution_log_index()` - Build executionId → file path mapping
- `enrich_chat_with_execution_log()` - Replace brief responses with full text

**Execution Log Enrichment:**

Kiro `.chat` files contain brief bot acknowledgments. Full responses are in execution logs:

```
workspace-sessions/{workspace}/
├── {session}.chat              # Brief: "On it."
└── {hash-subdir}/
    └── {execution-id}          # Full: Complete bot response
```

The enrichment process:
1. Build index of execution logs (once per workspace)
2. For each chat, find matching execution log by executionId
3. Extract full bot responses from `messagesFromExecutionId` array
4. Replace brief acknowledgments with full text
5. Return enriched messages + any errors encountered

Errors are logged but don't fail exports - original content is preserved.

### 4.2.2 Data Layer (Codex CLI)
**Modules:** `codex_parser.py`, `codex_projects.py`

**Responsibilities:**
- Codex JSONL rollout file parsing
- Project discovery by scanning `~/.codex/sessions/` recursively
- Session grouping by `cwd` (working directory)
- Content normalization from Responses API format
- Session metadata extraction (model, git branch, CLI version)

**Key Data Classes:**
- `CodexSessionMeta` - Session metadata (cwd, model, timestamp, cli_version, git_branch)
- `CodexSession` - Parsed session with metadata and messages

**Key Functions:**
- `parse_codex_rollout()` - Parse a JSONL rollout file into CodexSession
- `parse_session_meta()` - Extract session metadata from first JSONL line
- `extract_codex_messages()` - Convert rollout events to ChatMessage objects
- `normalize_codex_content()` - Normalize Responses API content arrays to text
- `discover_codex_sessions()` - Find all rollout files under sessions directory
- `group_sessions_by_project()` - Group sessions by cwd into ProjectInfo objects

**Codex Data Structure:**

```
~/.codex/sessions/
└── YYYY/MM/DD/
    └── rollout-<timestamp>-<uuid>.jsonl
```

Each rollout file contains:
1. First line: `session_meta` event with `cwd`, `model`, `cli_version`, `git` info
2. Subsequent lines: `response_item` events containing `message` items with role/content

Sessions sharing the same `cwd` are grouped into one logical project.

### 4.3 Export Engine
**Modules:** `exporters.py`, `formatters.py`, `filters.py`

**Responsibilities:**
- Multiple export formats (pretty, markdown, book, wiki)
- Content filtering (trivial chat detection, system tag removal)
- Batch export to directories
- Single-chat export with smart filenames
- Source-aware exports (Claude Desktop, Kiro IDE, and Codex CLI)

**Export Formats:**
- **Pretty:** Terminal-friendly with colors and icons
- **Markdown:** Standard markdown with timestamps
- **Book:** Clean format without timestamps, enhanced user visibility
- **Wiki:** AI-generated single-page documentation with TOC

**Key Functions:**
- `export_chat_pretty()` - Terminal format
- `export_chat_book()` - Clean book format
- `export_project_wiki()` - Wiki generation
- `export_project_chats()` - Batch export

### 4.4 External Integrations
**Modules:** `llm_client.py`, `sanitizer.py`

**OpenRouter Integration (Optional):**
- AI-powered chat title generation
- Uses `anthropic/claude-haiku-4.5` by default
- Fallback to first user question if unavailable
- API key via `OPENROUTER_API_KEY` env var

**Sanitization Engine:**
- Pattern-based sensitive data detection
- Multiple detection levels (minimal, balanced, aggressive)
- Multiple redaction styles (simple, stars, labeled, partial, hash)
- Configurable via `.env` or CLI flags

**Key Classes:**
- `OpenRouterClient` - HTTP client for OpenRouter API
- `Sanitizer` - Pattern matching and redaction engine

### 4.5 Auto-Export Pipeline
**Modules:** `project_matcher.py`, `auto_exporter.py`, `chat_merger.py`, `auto-export.py`

**Responsibilities:**
- Discover conversation projects across all sources
- Map conversation project names → filesystem folders under a user-provided root
- Persist mappings in a JSON config (`~/.config/claude-chat-manager/project-mapping.json`)
- Export and merge chats into each project's `docs/chats/` folder in a single run
- Group multiple sources (Claude/Kiro/Codex) that target the same folder

**Key Classes:**
- `ProjectMapping` - Single project mapping entry (source, target, action)
- `MappingConfig` - Load/save/query the mapping JSON config
- `ProjectMatcher` - Matching engine (workspace path, Claude name decode, basename, fuzzy)
- `AutoExporter` - Pipeline orchestrator (discover → group → export → merge)
- `ExportResult` - Per-target summary with new/updated/skipped counts
- `ChatMerger` - Content-fingerprint-based merge (used by AutoExporter and the standalone `merge-chats.py`)

**Key Functions:**
- `ProjectMatcher.match_project()` - Runs the full match strategy chain for one project
- `ProjectMatcher.detect_docs_chats_dir()` - Heuristic search for the chat output folder
- `AutoExporter.run()` - Execute the full export+merge pipeline
- `AutoExporter.dry_run_report()` - Preview mode — no writes

**Matching Strategy (priority order):**
1. Config lookup (already mapped and confirmed)
2. Workspace path exact match (Kiro `workspace_path`, Codex `cwd`)
3. Claude project name decode (`Users-Mike-Src-Project` → path segments)
4. Basename exact match (case-insensitive)
5. Fuzzy token-based match (threshold ≥ 0.8)
6. User prompt (in `--learn` mode) or skip

**CLI Entry Point:** `auto-export.py` at project root, same pattern as `merge-chats.py` and `sanitize-chats.py`. See `docs/AUTO_EXPORT.md` for the user guide.

---

## 5. Data Flow & Runtime Model

### 5.1 Interactive Browser Flow (Multi-Source)

```
User runs: python claude-chat-manager.py --source all
                    │
                    ▼
         ┌──────────────────────┐
         │ Load .env config     │
         │ Setup logging        │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Check --source flag  │
         │ (claude/kiro/codex/  │
         │  all)                │
         └──────────┬───────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│Scan Claude│ │ Scan Kiro │ │Scan Codex │
│~/.claude/ │ │ workspace-│ │~/.codex/  │
│projects/  │ │ sessions/ │ │sessions/  │
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │ Merge & sort projects│
         │ Add source indicators│
         │ [Claude]/[Kiro]/     │
         │ [Codex]              │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Display project list │
         │ (sorted by date)     │
         └──────────┬───────────┘
                    │
         User selects project
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│ Claude:   │ │ Kiro:     │ │ Codex:    │
│ List      │ │ List      │ │ List      │
│ *.jsonl   │ │ sessions  │ │ rollout   │
│ files     │ │ from JSON │ │ *.jsonl   │
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
         User selects chat
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│Parse JSONL│ │Parse .chat│ │Parse JSONL│
│ (Claude)  │ │JSON (Kiro)│ │ (Codex)   │
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │ Normalize content    │
         │ (Kiro/Codex→string)  │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Format for display   │
         │ Show in pager        │
         └──────────────────────┘
```

### 5.2 Export Flow (Book Format)

```
User runs: python claude-chat-manager.py "Project" -f book -o exports/
                    │
                    ▼
         ┌──────────────────────┐
         │ Find project by name │
         │ (check all sources)  │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Get chat files       │
         │ (*.jsonl or *.json   │
         │  or rollout *.jsonl) │
         └──────────┬───────────┘
                    │
         For each chat file:
                    │
                    ▼
         ┌──────────────────────┐
         │ Parse file           │
         │ (JSONL/Kiro/Codex)   │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Filter trivial chats?│ (configurable)
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Generate filename    │
         │ (LLM or first Q)     │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Filter system tags   │
         │ Remove tool noise    │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Apply sanitization?  │ (if enabled)
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │ Write to .md file    │
         └──────────────────────┘
```

### 5.3 Configuration Loading Hierarchy

```
1. Environment variables (highest priority)
   ↓
2. .env file in project root
   ↓
3. Default values in config.py
```

**Example:**
```python
CLAUDE_PROJECTS_DIR = os.getenv('CLAUDE_PROJECTS_DIR') or ~/.claude/projects
SANITIZE_ENABLED = os.getenv('SANITIZE_ENABLED') or false
WIKI_GENERATE_TITLES = os.getenv('WIKI_GENERATE_TITLES') or true
```

---

## 6. Configuration & Environment Assumptions

### Environment Variables (.env)

**Core Settings:**
- `CLAUDE_PROJECTS_DIR` - Custom Claude projects directory
- `CLAUDE_LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `CLAUDE_DEFAULT_FORMAT` - Default export format
- `CLAUDE_PAGE_HEIGHT` - Terminal page height

**Kiro IDE Settings:**
- `KIRO_DATA_DIR` - Custom Kiro data directory (OS-specific default)
- `CHAT_SOURCE` - Default source filter (claude, kiro, codex, all)

**Codex CLI Settings:**
- `CODEX_DATA_DIR` - Custom Codex data directory (default: `~/.codex`)
- `CODEX_HOME` - Alternative Codex home directory (standard Codex env var)

**LLM Integration:**
- `OPENROUTER_API_KEY` - API key for title generation
- `OPENROUTER_MODEL` - Model to use (default: `anthropic/claude-haiku-4.5`)
- `OPENROUTER_TIMEOUT` - API timeout in seconds

**Wiki Generation:**
- `WIKI_GENERATE_TITLES` - Enable LLM title generation (true/false)
- `WIKI_SKIP_TRIVIAL` - Filter trivial chats (true/false)
- `WIKI_MIN_MESSAGES` - Minimum message count (default: 3)
- `WIKI_MIN_WORDS` - Minimum word count (default: 75)
- `WIKI_FILTER_SYSTEM_TAGS` - Remove system tags (true/false)

**Book Export:**
- `BOOK_SKIP_TRIVIAL` - Filter trivial chats (true/false)
- `BOOK_GENERATE_TITLES` - Generate descriptive filenames (true/false)
- `BOOK_USE_LLM_TITLES` - Use LLM for filenames (false by default)
- `BOOK_FILTER_SYSTEM_TAGS` - Remove system tags (true/false)
- `BOOK_FILTER_TOOL_NOISE` - Remove tool messages (true/false)
- `BOOK_INCLUDE_DATE` - Append date to filenames (true/false)

**Sanitization:**
- `SANITIZE_ENABLED` - Enable sanitization (false by default)
- `SANITIZE_LEVEL` - Detection level (minimal/balanced/aggressive/custom)
- `SANITIZE_STYLE` - Redaction style (simple/stars/labeled/partial/hash)
- `SANITIZE_PATHS` - Sanitize file paths (false by default)

### Deployment Assumptions

- **Platform:** Cross-platform (Windows, macOS, Linux)
- **Python:** 3.9+ required
- **Dependencies:** Minimal (standard library only for core functionality)
- **Claude Data Location:** `~/.claude/projects/` (Claude Desktop default)
- **Kiro Data Location:** OS-specific (see Critical Paths section)
- **Codex Data Location:** `~/.codex/sessions/` (configurable via `CODEX_DATA_DIR` or `CODEX_HOME`)
- **Executable:** Can be built with PyInstaller (see `docs/BUILDING.md`)

---


## 7. Stability Zones

### ✅ Stable (Production-Ready, Low Risk)

**Core Data Layer:**
- `parser.py` - JSONL parsing (well-tested, stable format)
- `models.py` - Data classes with ChatSource enum (well-tested)
- `projects.py` - Project discovery with multi-source support (stable)

**Kiro Data Layer:**
- `kiro_parser.py` - Kiro JSON parsing with execution log enrichment (322 tests passing)
- `kiro_projects.py` - Workspace/session discovery (property-tested)

**Codex Data Layer:**
- `codex_parser.py` - Codex JSONL rollout parsing (34 tests passing)
- `codex_projects.py` - Project discovery by cwd grouping (10 tests passing)

**Formatting:**
- `formatters.py` - Message formatting with structured content support (mature)
- `colors.py` - ANSI colors (complete, no changes needed)

**Configuration:**
- `config.py` - Environment variable loading with Kiro and Codex settings (stable)

**Guidance:** Safe to use as-is. Changes should be additive only.

### 🔄 Semi-Stable (Functional, May Evolve)

**Export Engine:**
- `exporters.py` - Export formats (may add new formats)
- `filters.py` - Chat filtering (thresholds may be tuned)
- `wiki_generator.py` - Wiki generation (may add features)

**Auto-Export Pipeline:**
- `project_matcher.py` - Matching engine and config management (new feature, heuristics may evolve)
- `auto_exporter.py` - Pipeline orchestrator (new feature)
- `chat_merger.py` - Content-fingerprint merge engine (new feature, thresholds may be tuned)

**CLI Interface:**
- `cli.py` - Interactive browser (UX improvements possible)
- `display.py` - Terminal pager (platform-specific tweaks)

**External Integrations:**
- `llm_client.py` - OpenRouter client (API may change)

**Guidance:** Functional but expect minor changes. Test thoroughly after modifications.

### ⚠️ Experimental (Working, May Be Replaced)

**Sanitization:**
- `sanitizer.py` - Pattern-based detection (patterns evolving)
- `sanitize-chats.py` - Post-processing tool (new feature)

**Wiki Parsing:**
- `wiki_parser.py` - Parse existing wikis (format may change)

**Guidance:** Use with caution. Patterns and formats may change based on user feedback.

### 🔮 Planned (Not Yet Implemented)

- GUI interface (mentioned in docs but not implemented)
- Full-text search with indexing (performance improvement)
- PDF/HTML export formats (additional output options)
- Chat statistics and analytics (data insights)

**Guidance:** Do not depend on these features. They are aspirational.

---

## 8. AI Coding Rules and Behavioral Contracts

### ⚠️ CRITICAL: This Document Does NOT Define Coding Rules

All AI coding assistants MUST:
1. **Read AI*.md files FIRST** before making any code changes
2. **Apply rules strictly** from those files
3. **Resolve conflicts conservatively** or ask for clarification

### Authoritative AI Rule Files

**Global Rules:**
- `AI.md` - Python coding standards, project structure, error handling
  - PEP8 style, type hints, docstrings
  - Modules under 800 lines
  - Custom exceptions + logging (no print)
  - Configuration in .env (no hardcoding)
  - Tests in tests/ directory
  - Docs in docs/ directory

**Behavioral Rules:**
- `CLAUDE.md` - AI assistant behavior
  - Always check AI*.md for coding rules
  - Review docs/chats/ for implementation context
  - Check documentation in root and docs/
  - **Never start coding immediately** - propose solution first

### Rule Precedence (Highest → Lowest)

```
1. Explicit user instructions in current task
   ↓
2. Stack-specific AI_*.md (if exists)
   ↓
3. Global AI.md
   ↓
4. This ARCHITECTURE.md (architectural constraints only)
   ↓
5. Implicit conventions from codebase
```

### Conflict Resolution Process

**If rules conflict or are ambiguous:**
1. **STOP** - Do not proceed with implementation
2. **ASK** - Present the conflict to the user
3. **WAIT** - Get explicit clarification before continuing

**Example:**
```
"AI.md says modules should be under 800 lines, but the proposed
feature would make exporters.py 850 lines. Should I:
a) Split into two modules
b) Increase the limit for this file
c) Refactor existing code to make room?"
```

### Key Architectural Decisions to Preserve

**1. Modular Structure (from refactoring 2025-11-04):**
- Keep modules under 800 lines
- Separate concerns (parsing, formatting, exporting)
- No monolithic files

**2. Configuration Pattern:**
- All settings via .env file
- No hardcoded paths or values
- Environment variables override .env

**3. Error Handling:**
- Custom exception hierarchy (`exceptions.py`)
- Logging module (not print statements)
- User-friendly error messages

**4. Testing Strategy:**
- Unit tests with pytest
- Type checking with mypy
- Code formatting with black
- All tests in tests/ directory

**5. Export Architecture:**
- Shared filtering logic (`filters.py`)
- Consistent sanitization across formats
- Reusable components (ChatFilter, Sanitizer)

**6. Documentation Structure:**
- README.md for users
- docs/ for detailed guides
- AI*.md for coding rules
- docs/chats/ for implementation history

---

## 9. Quick Start for AI Assistants

### Pre-Flight Checklist Before Making Changes

**1. Read AI Rules:**
```
□ Read AI.md (global Python rules)
□ Read CLAUDE.md (behavioral rules)
□ Check for stack-specific AI_*.md files
```

**2. Understand Context:**
```
□ Read this ARCHITECTURE.md (system structure)
□ Check docs/chats/ for related conversations
□ Review relevant docs/*.md files
```

**3. Verify Stability:**
```
□ Check Section 7 (Stability Zones)
□ Identify if changes affect ✅ Stable or ⚠️ Experimental code
□ Plan accordingly (stable = conservative, experimental = flexible)
```

**4. Propose Before Implementing:**
```
□ Describe the solution approach
□ Ask for explicit approval
□ Do NOT start coding immediately
```

### Where to Find Specific Information

**"How do I add a new export format?"**
→ See `src/exporters.py`, study existing formats (book, wiki)

**"How does configuration work?"**
→ See `src/config.py` and `.env.example`

**"How do I add a new CLI command?"**
→ See `claude-chat-manager.py` (argparse) and `src/cli.py` (handlers)

**"How does sanitization work?"**
→ See `docs/SANITIZATION.md` (user guide) and `src/sanitizer.py` (implementation)

**"How do I build an executable?"**
→ See `docs/BUILDING.md` (PyInstaller instructions)

**"What are the coding standards?"**
→ See `AI.md` (NOT this file)

**"How do I run tests?"**
→ See `docs/DEVELOPMENT.md` (testing guide)

**"What was the refactoring history?"**
→ See `docs/chats/refactoring-monolithic-python-script-into-production-ready-codebase-2025-11-04.md`

**"How does Kiro IDE support work?"**
→ See `src/kiro_parser.py` (parsing), `src/kiro_projects.py` (discovery), and README.md (usage)

**"How does Codex CLI support work?"**
→ See `src/codex_parser.py` (parsing), `src/codex_projects.py` (discovery), `docs/CODEX_IMPLEMENTATION.md` (design), and README.md (usage)

**"How does auto-export work?"**
→ See `docs/AUTO_EXPORT.md` (user guide), `docs/AUTO_EXPORT_PLAN.md` (design), `src/project_matcher.py` (matching), `src/auto_exporter.py` (pipeline), and `auto-export.py` (CLI)

**"How do I add support for a new chat source?"**
→ Study `src/kiro_parser.py` and `src/codex_parser.py` as examples, then:
1. Create parser module for the new format
2. Create projects module for discovery
3. Add source to `ChatSource` enum in `src/models.py`
4. Update `src/config.py` with new settings
5. Wire into `src/projects.py` for unified listing

### Common Modification Patterns

**Adding a new configuration option:**
1. Add to `.env.example` with comment
2. Add property to `Config` class in `src/config.py`
3. Use via `config.property_name` in code
4. Document in relevant docs/*.md file

**Adding a new export format:**
1. Create `export_chat_newformat()` in `src/exporters.py`
2. Add format choice to argparse in `claude-chat-manager.py`
3. Wire up in `export_chat_to_file()` function
4. Add tests in `tests/test_exporters.py`
5. Document in README.md

**Adding a new sanitization pattern:**
1. Add pattern to `PATTERNS` dict in `src/sanitizer.py`
2. Update level selection in `_select_patterns_by_level()`
3. Add tests in `tests/test_sanitizer.py`
4. Document in `docs/SANITIZATION.md`

**Adding a new chat source (like Kiro or Codex):**
1. Create `src/{source}_parser.py` with parsing functions
2. Create `src/{source}_projects.py` with discovery functions
3. Add source value to `ChatSource` enum in `src/models.py`
4. Add configuration properties to `src/config.py`
5. Update `src/projects.py` to include new source in unified listing
6. Add `--source` flag option in `claude-chat-manager.py`
7. Add tests in `tests/test_{source}_*.py`
8. Document in README.md and ARCHITECTURE.md

---


**Document Version:** 1.4  
**Last Updated:** 2026-04-24  
**Total Lines:** ~520  
**Status:** ✅ Complete (Claude Desktop, Kiro IDE, Codex CLI, Auto-Export pipeline)

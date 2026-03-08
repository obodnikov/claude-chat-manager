# Claude Chat Manager 🤖

A powerful Python tool to browse, read, and export Claude Desktop's JSONL chat files with an intuitive interface and Unix `less`-like paging for smooth reading experience.

**Version 3.0.0** - Now with Codex CLI and Kiro IDE support! Browse and export chats from Claude Desktop, Kiro IDE, and OpenAI Codex CLI.

## ✨ Features

- 📋 **Interactive Project Browser** - Navigate through all your Claude projects
- 🔍 **Smart Search** - Search project names and chat content across all conversations
- 📖 **Paged Chat Viewing** - Unix `less`-like navigation for comfortable reading
- 📊 **Multiple Export Formats** - Pretty terminal output, Markdown, clean Book format, or raw JSON
- 📚 **Wiki Generation** - Generate AI-powered single-page wikis from entire projects
- 🔒 **Data Sanitization** - NEW! Automatically detect and redact API keys, tokens, and passwords
- 🤖 **AI-Powered Titles** - Automatic chat title generation using LLM (via OpenRouter)
- 🎯 **Batch Export** - Export entire projects to organized Markdown files
- 🎨 **Colored Output** - Beautiful terminal interface with syntax highlighting
- ⚡ **Fast Performance** - Efficient parsing of large chat histories
- 🔧 **Codex CLI Support** - Browse and export OpenAI Codex CLI sessions
- 🔄 **Easy Navigation** - Intuitive menu system with back buttons

## 🚀 Installation

### Prerequisites
- Python 3.6 or higher
- Claude Desktop installed with chat history

### Quick Install
```bash
# Clone or download the repository
cd claude-chat-manager

# Optional: Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies (optional, for testing)
pip install -r requirements-dev.txt

# Make it executable
chmod +x claude-chat-manager.py

# Run it
python3 claude-chat-manager.py
```

### System-wide Installation
```bash
# Install globally
sudo cp claude-chat-manager.py /usr/local/bin/claude-chat-manager
sudo chmod +x /usr/local/bin/claude-chat-manager

# Now use from anywhere
claude-chat-manager --list
```

### Create Alias
```bash
# Add to ~/.bashrc or ~/.zshrc
alias claude='python3 /path/to/claude-chat-manager.py'

# Usage
claude --list
claude "My Project" -f book -o my-exports
```

## 📖 Usage

### Interactive Browser (Default)
```bash
python3 claude-chat-manager.py
```

**Main Menu:**
```
🤖 Claude JSONL Chat Browser
============================================================

Available projects:

 1) Docker Container Update Checker            (3 chats, 45 msgs, 2025-09-20 17:52)
 2) Ubuntu Kernel Cleanup Script               (2 chats, 32 msgs, 2025-09-19 16:45)
 3) Home Mike Src Pollen Web Application       (5 chats, 78 msgs, 2025-09-20 12:28)

Options:
  1-3) Browse specific project
  l) List all projects with details
  r) Show recent projects
  c) Search chat content
  q) Quit
```

### Command Line Options

#### List Projects
```bash
python3 claude-chat-manager.py --list
python3 claude-chat-manager.py -l
```

#### Search Projects
```bash
# Search by project name
python3 claude-chat-manager.py --search "docker"
python3 claude-chat-manager.py -s "pollen"
```

#### Search Chat Content
```bash
# Find conversations containing specific terms
python3 claude-chat-manager.py --content "update checker"
python3 claude-chat-manager.py -c "systemctl"
```

#### Recent Projects
```bash
# Show 5 most recent projects
python3 claude-chat-manager.py --recent 5
python3 claude-chat-manager.py -r 10
```

#### Browse Specific Project
```bash
# View project chats interactively
python3 claude-chat-manager.py "Docker Container Update Checker"
python3 claude-chat-manager.py "Home Mike Src Pollen Web Application"
```

#### Export Options

**Non-Interactive Export (NEW in v2.0!)**

When you specify `-o` (output), the tool exports directly without showing the interactive menu:

```bash
# Export to a named directory
python3 claude-chat-manager.py "My Project" -f book -o my-exports
# → Creates: my-exports/ with all chats as separate .md files

# Export to a directory with trailing slash
python3 claude-chat-manager.py "My Project" -f markdown -o exports/
# → Creates: exports/ with all chats as separate .md files

# Export with a filename (creates timestamped directory)
python3 claude-chat-manager.py "My Project" -f book -o chat.md
# → Creates: chat_20251104_193033/ with all chats as separate .md files
#    (Timestamp format: YYYYMMDD_HHMMSS)
```

**Export Behavior:**
- `-o dirname` → Exports to `dirname/` directory
- `-o dirname/` → Exports to `dirname/` directory
- `-o file.md` → Exports to timestamped `file_YYYYMMDD_HHMMSS/` directory

**Available Formats:**
```bash
python3 claude-chat-manager.py "My Project" -f pretty    # Terminal output (default)
python3 claude-chat-manager.py "My Project" -f book      # Clean book format
python3 claude-chat-manager.py "My Project" -f markdown  # Standard markdown
python3 claude-chat-manager.py "My Project" -f wiki      # AI-powered wiki (single page)
python3 claude-chat-manager.py "My Project" -f raw       # Raw JSON
```

**Wiki Format (NEW!):**

Generate a single-page wiki from all project chats with AI-generated titles:

```bash
# Generate wiki with AI-powered titles
python3 claude-chat-manager.py "My Project" --wiki project-wiki.md

# Or use format flag
python3 claude-chat-manager.py "My Project" -f wiki -o my-wiki.md
```

**Updating Existing Wikis (NEW!):**

Keep your wiki up-to-date as you add new chats to your project:

```bash
# Update existing wiki with new chats (smart merge)
python3 claude-chat-manager.py "My Project" --wiki project-wiki.md --update

# Force full rebuild of entire wiki (regenerates all titles)
python3 claude-chat-manager.py "My Project" --wiki project-wiki.md --rebuild
```

**Update Features:**
- 🔄 **Smart Merge**: Automatically detects if new chats can be appended or need full rebuild
- 💾 **Title Caching**: Reuses existing titles from wiki (saves API costs in update mode)
- ⚡ **Fast Updates**: Append-only strategy when all new chats are newer than existing ones
- 🔍 **Auto-Detection**: Compares chat IDs and timestamps to identify new conversations
- 🛡️ **Safe Defaults**: Prompts for confirmation if wiki exists without `--update` or `--rebuild` flags

**How Updates Work:**
1. **Update Mode** (`--update`): Analyzes existing wiki, identifies new chats, reuses cached titles for existing chats, generates titles only for new chats, merges and sorts chronologically
2. **Rebuild Mode** (`--rebuild`): Regenerates entire wiki from scratch, creates fresh AI titles for all chats (ignores cache)
3. **Smart Strategy**: If all new chats are newer → fast append; if chronological insertion needed → full rebuild

**Filtering Trivial Chats (NEW!):**

The wiki generator automatically filters out trivial or pointless conversations to keep your documentation focused and meaningful:

```bash
# Filtering is enabled by default with these thresholds:
# - Minimum 3 messages
# - Minimum 75 total words
# - Filters warmup/test/hello keywords in short first messages
```

**Customize Filtering** (in your `.env` file):
```bash
# Enable/disable filtering (default: true)
WIKI_SKIP_TRIVIAL=true

# Minimum messages for a chat to be included (default: 3)
WIKI_MIN_MESSAGES=3

# Minimum total word count (default: 75)
WIKI_MIN_WORDS=75

# Keywords that indicate trivial chats (comma-separated)
WIKI_SKIP_KEYWORDS=warmup,test,hello,hi,ready

# Require code blocks or file references (default: false)
WIKI_REQUIRE_CONTENT=false
```

**Filtering Criteria:**
- ⚖️ **Message Count**: Chats with too few messages are filtered
- 📝 **Word Count**: Very short conversations are excluded
- 🔑 **Keyword Detection**: "Warmup", "test", etc. in brief first messages
- 💻 **Content Requirement**: Optionally require code or file modifications
- 🏷️ **System Tag Filtering**: Automatically removes `<ide_opened_file>`, `<system-reminder>`, and other system notifications from user messages

**System Tag Filtering (NEW!):**

The wiki generator now intelligently filters system notification tags from user messages:
- **Pure system messages** (only tags, no user text) are completely skipped
- **Mixed messages** (tags + user text) have tags stripped, keeping the actual user question
- **Normal messages** without tags are preserved as-is

Filtered system tags:
- `<ide_opened_file>` - File opening notifications from IDE
- `<system-reminder>` - System reminder messages
- `<user-prompt-submit-hook>` - Hook execution messages
- `<command-message>` - Command status messages

This can be disabled by setting `WIKI_FILTER_SYSTEM_TAGS=false` in your `.env` file.

After generation, the summary shows how many chats were filtered:
```
📊 Wiki Generation Summary:
==================================================
   Total chats in wiki: 27
   Filtered out (trivial): 3 chats
   Titles generated: 27
==================================================
```

**The wiki format:**
- 📚 **Single Page**: Combines all chats into one organized document
- 🤖 **AI Titles**: Uses LLM to generate descriptive titles for each chat
- 📅 **Chronological**: Sorts conversations by date
- 🧹 **Clean Content**: Filters out tool use/result noise for better readability
- 🔍 **Smart Filtering**: Automatically excludes trivial warmup/test chats
- 📝 **Hierarchical Table of Contents**: Auto-generated with user questions as clickable sub-items
- 👤 **Enhanced User Visibility**: User questions clearly marked with visual separators and emoji
- 🔗 **Direct Navigation**: Jump directly to any user question from the TOC
- 💻 **Syntax Highlighting**: Fenced code blocks with language detection
- 📎 **File References**: Preserves inline file references in italics
- 🔖 **Metadata Caching**: Hidden HTML comments store chat IDs and timestamps for updates

**User Question Visibility (NEW!):**

The wiki now makes user questions and feedback highly visible:
- **Hierarchical TOC**: Each chat section lists user questions as sub-items with 🗣️ emoji
- **Visual Markers**: User messages prefixed with `👤 **USER:**` and horizontal separators
- **Direct Links**: Click on any user question in the TOC to jump directly to that point in the conversation

Example TOC structure:
```markdown
### 1. Refactoring Python Script
*Nov 04, 2025 | Chat ID: abc123*

**Key Topics:**
- 🗣️ Refactor code with all 7 points
- 🗣️ CLI parameters still show menu (bug)
- 🗣️ Update README with usage guide
```

Example content with user markers:
```markdown
---

👤 **USER:**
> When I run command with cli parameters it still give me access to menu

You're absolutely right! Let me fix this...
```

**Setup for AI-Powered Titles:**

1. Get a free API key from [OpenRouter](https://openrouter.ai/keys)
2. Copy `.env.example` to `.env`
3. Add your API key:
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
   ```

Without an API key, the tool falls back to using the first user question as the title.

**Interactive Export (within the browser):**

When browsing interactively without `-o`, you can still export from the project menu:
- Press `e` to export all chats to markdown
- Press `eb` to export all chats to book format

## 🔒 Sensitive Data Sanitization (NEW!)

Automatically detect and redact sensitive information from chat exports including API keys, tokens, passwords, and environment variables.

### Quick Start

```bash
# Preview what would be sanitized
python3 claude-chat-manager.py "My Project" --sanitize-preview

# Export with sanitization
python3 claude-chat-manager.py "My Project" -f book -o exports/ --sanitize

# Wiki with sanitization
python3 claude-chat-manager.py "My Project" --wiki wiki.md --sanitize
```

### What Gets Detected

- **API Keys**: OpenAI (`sk-*`), GitHub (`ghp_*`), AWS (`AKIA*`), Google (`AIza*`), etc.
- **Tokens**: Bearer tokens, JWTs, Slack tokens
- **Passwords**: Contextual detection (`password = "..."`)
- **Environment Variables**: `API_KEY=sk-xxx`, `export TOKEN=...`

### CLI Flags

```bash
--sanitize                    # Enable sanitization
--sanitize-level LEVEL        # minimal, balanced, aggressive, custom
--sanitize-style STYLE        # simple, stars, labeled, partial, hash
--sanitize-paths              # Sanitize file paths
--sanitize-preview            # Preview without exporting
--sanitize-report FILE        # Generate detailed report
```

### Examples

```bash
# Use aggressive detection with labeled redaction
python3 claude-chat-manager.py "Project" -f book -o exports/ \
    --sanitize --sanitize-level aggressive --sanitize-style labeled

# Preview with custom settings
python3 claude-chat-manager.py "Project" --sanitize-preview \
    --sanitize-level aggressive --sanitize-paths
```

### Redaction Styles

| Style | Example |
|-------|---------|
| `partial` (default) | `sk-proj-abc...` → `sk-pr***xyz` |
| `labeled` | `sk-proj-abc...` → `[API_KEY]` |
| `simple` | `sk-proj-abc...` → `REDACTED` |
| `stars` | `sk-proj-abc...` → `**********` |
| `hash` | `sk-proj-abc...` → `[a3f4d8c2]` |

### Configuration (.env)

```bash
SANITIZE_ENABLED=true
SANITIZE_LEVEL=balanced
SANITIZE_STYLE=partial
SANITIZE_PATHS=false
```

### Post-Processing Tool

Sanitize already-exported files:

```bash
# Interactive mode - review each match
python3 sanitize-chats.py exported-chats/ --interactive

# Batch mode - auto-sanitize
python3 sanitize-chats.py exported-chats/

# Preview only
python3 sanitize-chats.py my-chat.md --preview
```

📚 **Full Documentation:** See [docs/SANITIZATION.md](docs/SANITIZATION.md) for complete guide, patterns, and best practices.

## 🔄 Chat Merge Utility (NEW!)

Intelligently merge exported chat files from different sources (e.g., multiple computers) while avoiding duplicates and handling incomplete conversations.

### The Problem

When working across multiple machines:
- Same conversations get different filenames (LLM-generated)
- Some conversations are incomplete (continued on another machine)
- Manual deduplication is tedious and error-prone

### The Solution

```bash
# Merge new exports into your project docs
python3 merge-chats.py \
  --source ~/exports/MacBook-Air-...-20260130_195936 \
  --target ./docs/chats/ \
  --preview
```

### How It Works

- **Content Fingerprinting**: Identifies conversations by content, not filename
- **Smart Detection**: Finds duplicates and incomplete versions automatically
- **Safe Merging**: Preview, interactive, or automatic modes with backups

### Quick Start

```bash
# 1. Preview what would be merged (dry-run)
python3 merge-chats.py --source NEW_EXPORTS/ --target docs/chats/ --preview

# 2. Interactive mode - review each decision
python3 merge-chats.py --source NEW_EXPORTS/ --target docs/chats/ --interactive

# 3. Automatic merge with backup and report
python3 merge-chats.py --source NEW_EXPORTS/ --target docs/chats/ --auto --backup --report merge.md
```

### Merge Actions

| Action | Description |
|--------|-------------|
| ✅ **NEW** | No match found - copy to target |
| 🔄 **UPDATE** | Source has more messages - replace incomplete version |
| ⏭️ **SKIP** | Identical conversation already exists |
| ⚠️ **REVIEW** | Manual check needed (similarity unclear) |

### Configuration

```bash
--similarity 0.8              # Match threshold (0.0-1.0, default: 0.8)
--fingerprint-messages 3      # Message pairs for fingerprint (default: 3)
--backup                      # Create .md.backup before overwriting
--report FILE                 # Generate detailed merge report
```

📚 **Full Documentation:** See [docs/MERGE_CHATS.md](docs/MERGE_CHATS.md) for complete guide, examples, and workflows.

## 🎮 Navigation Controls

### Project Browser
- **1-9**: Select project by number
- **l**: List all projects with details
- **r**: Show recent projects
- **c**: Search chat content
- **b**: Back to previous menu (where applicable)
- **q**: Quit

### Chat Viewer (Pager Mode)
- **Space** or **Enter**: Next page/line
- **b**: Back one page
- **j**: Next line (vim-style)
- **k**: Previous line (vim-style)
- **d**: Half page down
- **u**: Half page up
- **g**: Go to top
- **G**: Go to bottom (Shift+G)
- **q**: Return to project menu

### Project Menu
- **1-9**: Select chat (view or export) - Opens action menu with options:
  - **1**: View in terminal
  - **2**: Export to markdown
  - **3**: Export to book format
  - **4**: Cancel
- **a**: View all chats sequentially
- **e**: Export all chats to markdown
- **eb**: Export all chats to book format
- **b**: Back to main menu
- **q**: Quit

## 📊 Output Formats

### Pretty Format (Default)
```
👤 Message 1 - User
🕒 2025-09-20 12:28:46
💬 check script.js and detailed_history_styles.css...

🤖 Message 2 - Assistant
🕒 2025-09-20 12:28:50
💬 I'll check the files for you...

🔧 [Tool Use: Read]
   File: /home/mike/src/pollen-web-application/script.js

📄 [File Read]: /home/mike/src/pollen-web-application/script.js (1034 lines)
```

### Wiki Format (NEW! - AI-Powered Single Page)
```markdown
# My Project Wiki

**Generated:** 2025-11-04 19:30:00

## Table of Contents

1. [Setting Up Testing Infrastructure](#setting-up-testing-infrastructure) (2024-01-15)
2. [Implementing Custom Exception Handling](#implementing-custom-exception-handling) (2024-01-16)
3. [Adding Configuration Management](#adding-configuration-management) (2024-01-17)

---

## Setting Up Testing Infrastructure

**Date:** January 15, 2024

> How do I add pytest to this project?

First, let's install pytest and create a basic test structure. I'll help you set up a proper testing infrastructure.

*Files modified: requirements-dev.txt, tests/test_config.py*

```python
# tests/test_config.py
import pytest
from src.config import Config

def test_config_initialization():
    config = Config()
    assert config is not None
```

The test suite is now configured and ready to use.

> Should I add coverage reporting?

Yes, coverage reporting is valuable. Let's add pytest-cov to track test coverage...

---

## Implementing Custom Exception Handling

**Date:** January 16, 2024

> I need to add custom exceptions for better error handling

I'll help you create a custom exception hierarchy...
```

Features:
- **AI-Generated Titles**: Each chat gets a descriptive 8-10 word title based on content
- **Chronological Order**: Conversations sorted by date for logical reading
- **Clean Content**: Tool use/result messages filtered out, only conversation preserved
- **Table of Contents**: Quick navigation with anchor links
- **File References**: Inline references in italics (e.g., *src/config.py*)
- **Fenced Code Blocks**: Proper syntax highlighting with language detection
- **Fallback Titles**: Uses first user question if LLM unavailable

### Book Format (Clean & Readable - Enhanced!)

**NEW in v2.1:** Book mode now includes intelligent filtering and cleaning features inspired by wiki mode!

**Enhanced Features:**
- ✨ **Trivial Chat Filtering**: Automatically skips low-value conversations (warmup, tests, etc.)
- 🎯 **Smart Filenames**: Generates descriptive names from content instead of UUIDs
- 🧹 **System Tag Cleaning**: Removes IDE notifications and system messages
- 🔇 **Tool Noise Removal**: Filters out technical tool execution details
- 👤 **Enhanced User Highlighting**: Clear visual separators and USER markers
- 📎 **File Reference Tracking**: Clean file lists without tool noise
- 💻 **Code Block Preservation**: Maintains proper markdown formatting

```markdown
# Claude Chat Export

**Generated: 2025-11-09 10:30:00**

---

👤 **USER:**
> should i include package-lock file in .gitignore

I'll check your current .gitignore file to see what's already included and provide guidance on package-lock.json.

For Node.js projects, the decision about package-lock.json in .gitignore depends on your project type...

*Files: .gitignore*

---

👤 **USER:**
> what about yarn.lock?

For yarn.lock, the recommendation is different from package-lock.json...
```

**Configuration** (all optional, enabled by default):
```bash
# .env
BOOK_SKIP_TRIVIAL=true              # Filter out trivial chats
BOOK_GENERATE_TITLES=true           # Generate descriptive filenames
BOOK_USE_LLM_TITLES=false          # Use AI for titles (requires API key)
BOOK_FILTER_SYSTEM_TAGS=true       # Remove system notifications
BOOK_FILTER_TOOL_NOISE=true        # Remove tool execution details
BOOK_SHOW_FILE_REFS=true           # Show modified files
BOOK_INCLUDE_DATE=true             # Append date to filenames (YYYY-MM-DD)
```

See [docs/BOOK_MODE_ENHANCEMENTS.md](docs/BOOK_MODE_ENHANCEMENTS.md) for complete details.

### Markdown Format (Standard)
```markdown
# Claude Chat Export

**Generated: 2025-09-21 10:30:00**

## Message 1 - User
**Time:** 2025-09-20 12:28:46

check script.js and detailed_history_styles.css...

---

## Message 2 - Assistant
**Time:** 2025-09-20 12:28:50

I'll check the files for you...
```

## 🔧 Advanced Features

### Tool Usage Display
The reader intelligently formats Claude's tool usage:
- **🔧 Tool Use**: Shows function calls with parameters
- **📄 File Read**: Displays file operations with line counts
- **✏️ File Edit**: Indicates file modifications
- **✅ Todo Update**: Shows task management changes

### Project Name Cleaning
Projects starting with `-` (like `-home-mike-src-project`) are automatically cleaned to readable format (`Home Mike Src Project`).

### Batch Export
Export entire projects to organized files:
```bash
# In interactive mode, select project then choose:
# 'e' for standard markdown export
# 'eb' for clean book format export

# Creates directories with machine hostname and timestamp:
# MacBook-Air-Michael-Claude_Chat_Manager-markdown-20251109_103654/
# MacBook-Air-Michael-Claude_Chat_Manager-book-20251109_103654/
#   ├── implementing-authentication-2025-11-09.md
#   ├── fixing-database-queries-2025-11-08.md
#   └── adding-user-roles-2025-11-07.md
```

### Search Features
- **Project Search**: Find projects by name (supports partial matching)
- **Content Search**: Search across all chat content with context preview
- **Recent Filter**: Quickly find recently modified conversations

## 📁 File Structure

### Claude Desktop
Claude Desktop stores projects in:
- **Linux/macOS**: `~/.claude/projects/`
- **Windows**: `%USERPROFILE%\.claude\projects\`

Each project contains `.jsonl` files representing individual chats.

### Kiro IDE
Kiro IDE stores chat sessions in:
- **Windows**: `%APPDATA%\Kiro\User\globalStorage\kiro.kiroagent\workspace-sessions\`
- **macOS**: `~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/`
- **Linux**: `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/`

Each workspace has a base64-encoded folder containing `sessions.json` and individual `.json` chat files.

### Codex CLI
Codex CLI stores session rollout files in:
- **All platforms**: `~/.codex/sessions/` (configurable via `CODEX_HOME` env var)

Sessions are organized by date (`YYYY/MM/DD/`) with JSONL rollout files:
```
~/.codex/sessions/
└── 2026/
    └── 02/
        └── 20/
            └── rollout-2026-02-20T09-00-00-abc123.jsonl
```

Each JSONL file contains a `session_meta` first line with `cwd` (working directory), which is used to group sessions into projects.

## 🔄 Kiro IDE Support (NEW!)

Claude Chat Manager now supports Kiro IDE chat files alongside Claude Desktop, providing a unified interface for all your AI conversations.

### Quick Start with Kiro

```bash
# List Kiro projects only
python3 claude-chat-manager.py --source kiro

# List both Claude Desktop and Kiro projects
python3 claude-chat-manager.py --source all

# Export a Kiro project
python3 claude-chat-manager.py --source kiro "My Workspace" -f book -o exports/

# Interactive browser with Kiro chats
python3 claude-chat-manager.py --source kiro
```

### Source Selection

Use the `--source` (or `-s`) flag to control which chat sources to display:

| Flag | Description |
|------|-------------|
| `--source claude` | Claude Desktop only (default) |
| `--source kiro` | Kiro IDE only |
| `--source codex` | Codex CLI only |
| `--source all` | All sources combined |

### Configuration

Set the default source in your `.env` file:

```bash
# Default chat source (claude, kiro, codex, or all)
CHAT_SOURCE=claude

# Custom Kiro data directory (optional)
KIRO_DATA_DIR=/path/to/custom/kiro/data
```

### Kiro Data Directory Locations

The tool auto-detects Kiro's data directory based on your OS:

| OS | Default Location |
|----|------------------|
| Windows | `%APPDATA%\Kiro\User\globalStorage\kiro.kiroagent\` |
| macOS | `~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/` |
| Linux | `~/.config/Kiro/User/globalStorage/kiro.kiroagent/` |

### Features with Kiro

All existing features work with Kiro chats:
- ✅ Interactive browsing with source indicators `[Claude]` / `[Kiro]` / `[Codex]`
- ✅ All export formats (pretty, markdown, book, wiki)
- ✅ Content search across both sources
- ✅ Batch export of workspaces
- ✅ Sensitive data sanitization
- ✅ Smart filtering of trivial chats

### Kiro-Specific Handling

- **Structured Content**: Kiro's array-based message content is automatically normalized
- **Tool Blocks**: Tool use and results are formatted distinctly
- **Image References**: Image blocks display as `[Image]` in text exports
- **Session Titles**: Uses Kiro's session title or first user message for filenames

### Execution Log Enrichment

Kiro stores chat data in two locations:
1. **`.chat` files** - Contain brief bot acknowledgments like "On it." or "I'll help with that."
2. **Execution log files** - Contain the full bot responses with complete explanations

When exporting Kiro chats, the tool automatically enriches bot messages by:
1. Finding the corresponding execution log for each chat session
2. Extracting full bot responses from the `messagesFromExecutionId` array
3. Replacing brief acknowledgments with complete responses

**This happens automatically** - no configuration needed. Your exports will contain the full conversation content.

**Error Handling:**

If execution logs are missing or corrupted, the tool:
- Logs a warning message (visible in verbose mode or log files)
- Continues with the original brief response from the `.chat` file
- Does not fail the entire export

Common scenarios:
| Scenario | Behavior |
|----------|----------|
| Execution log found | Full bot response in export ✅ |
| Execution log missing | Brief response preserved, warning logged ⚠️ |
| Execution log corrupted | Brief response preserved, error logged ⚠️ |
| No executionId in chat | Original content used, warning logged ⚠️ |

**Note:** Execution logs are stored in hash-named subdirectories within the workspace. The tool scans these directories automatically to build an index for efficient lookups.

## 🔧 Codex CLI Support (NEW!)

Claude Chat Manager now supports OpenAI Codex CLI sessions as a third chat source, providing a unified interface for all your AI coding conversations.

### Quick Start with Codex

```bash
# List Codex projects only
python3 claude-chat-manager.py --source codex

# List all sources (Claude + Kiro + Codex)
python3 claude-chat-manager.py --source all

# Export a Codex project
python3 claude-chat-manager.py --source codex "My Project" -f book -o exports/

# Search across Codex sessions
python3 claude-chat-manager.py --source codex -c "database migration"
```

### How Codex Projects Work

Unlike Claude Desktop (project folders) and Kiro IDE (workspace sessions), Codex CLI organizes sessions by date. The tool groups sessions by their working directory (`cwd`) to form logical projects:

```
~/.codex/sessions/
└── 2026/02/20/
    ├── rollout-2026-02-20T09-00-00-abc123.jsonl  (cwd: /home/user/my-app)
    └── rollout-2026-02-20T14-30-00-def456.jsonl  (cwd: /home/user/my-app)
```

Both rollout files above share the same `cwd`, so they appear as one project: "My App".

### Configuration

Set Codex options in your `.env` file:

```bash
# Custom Codex data directory (default: ~/.codex)
CODEX_DATA_DIR=/path/to/custom/codex/data

# Or use the standard Codex environment variable
CODEX_HOME=/path/to/custom/codex

# Default source filter
CHAT_SOURCE=codex
```

### Codex Data Directory

The tool reads from `~/.codex/sessions/` by default (or `$CODEX_HOME/sessions/`). Override with `CODEX_DATA_DIR` in `.env`.

### Features with Codex

All existing features work with Codex sessions:
- ✅ Interactive browsing with `[Codex]` source indicator
- ✅ All export formats (pretty, markdown, book, wiki)
- ✅ Content search across sessions
- ✅ Batch export of projects
- ✅ Sensitive data sanitization
- ✅ Smart filtering of trivial chats

### Codex-Specific Handling

- **JSONL Rollout Format**: Parses `session_meta` and `response_item` events from rollout files
- **Content Normalization**: Handles Responses API content arrays (`input_text`, `output_text`)
- **Project Grouping**: Sessions sharing the same `cwd` are grouped into one project
- **Session Metadata**: Extracts model name, git branch, CLI version, and timestamps
- **Smart Naming**: Project names derived from the working directory path

## 🛠️ What's New

### v3.0.0 - Codex CLI & Kiro IDE Support (February 2026)

**New Features:**
- 🔧 **Codex CLI Support**: Browse and export OpenAI Codex CLI sessions as a third chat source
- 🔄 **Kiro IDE Support**: Browse and export Kiro IDE chat sessions alongside Claude Desktop
- 🎯 **Source Selection**: `--source` flag to filter by claude, kiro, codex, or all
- 📁 **Unified Listing**: Combined project view with source indicators `[Claude]` / `[Kiro]` / `[Codex]`
- 🔧 **Structured Content**: Automatic handling of Kiro's array-based and Codex's JSONL rollout formats
- 🖼️ **Image Indicators**: `[Image]` markers for image references in exports
- ⚙️ **Configuration**: `KIRO_DATA_DIR`, `CODEX_DATA_DIR`, and `CHAT_SOURCE` environment variables

**Codex CLI Technical Details:**
- New `codex_parser.py` module for parsing Codex JSONL rollout files
- New `codex_projects.py` module for project discovery by `cwd` grouping
- Session metadata extraction (model, git branch, CLI version)
- Content normalization from Responses API format (input_text, output_text)
- Filters `response_item` events, extracts `message` items only
- Date-organized session discovery (`~/.codex/sessions/YYYY/MM/DD/`)

**Kiro IDE Technical Details:**
- New `kiro_parser.py` module for parsing Kiro `.chat` JSON files
- New `kiro_projects.py` module for workspace and session discovery
- Extended data models with `ChatSource` enum
- Base64 workspace path decoding for human-readable names
- Full integration with existing export, search, and sanitization features

### v2.2.0 - Single Chat Export & Directory Naming (November 2025)

**New Features:**
- 💾 **Single Chat Export**: Select individual chats for export via action menu
  - Choose to view OR export after selecting a chat
  - Supports both markdown and book formats
  - Uses same intelligent filename generation as batch exports
- 🏷️ **Improved Directory Naming**: Machine-hostname-based export directories
  - Format: `MacBook-Air-Michael-Claude_Chat_Manager-book-20251109_103654`
  - Clear machine identification for multi-system workflows
- 🎯 **Enhanced UX**: Clearer menu options and workflow
  - "Select chat (view or export)" - more descriptive menu text
  - Action sub-menu for flexible workflows

**Export Locations:**
- **Batch exports**: Timestamped directories with hostname
- **Single exports**: Current directory with descriptive filenames

### v2.1.0 - Book Mode Enhancements (November 2025)

**Major Improvements:**
- 🎯 **Intelligent Filtering**: Automatically filters trivial/warmup chats
- 📝 **Smart Filenames**: Generates descriptive names from conversation topics
- 🧹 **Content Cleaning**: Removes system tags and tool execution noise
- 👤 **Better User Visibility**: Enhanced highlighting with visual separators
- 📎 **File Tracking**: Clean references to modified files
- 🔄 **Shared Architecture**: Unified filtering logic between wiki and book modes

**Configuration:**
- All features configurable via `.env` file
- Sensible defaults (enabled by default)
- Optional LLM-powered title generation
- Backward compatible with previous versions

See [docs/BOOK_MODE_ENHANCEMENTS.md](docs/BOOK_MODE_ENHANCEMENTS.md) for complete documentation.

### v2.0.0 - Previous Features

**Book Format Features:**
- **Clean presentation**: Removes timestamps and message numbers for distraction-free reading
- **Simple user questions**: Questions appear as blockquotes with USER markers
- **Direct responses**: Assistant answers without headers or metadata
- **Perfect for sharing**: Creates clean, readable documents ideal for documentation or reference
- **Batch export**: Use `eb` command in project browser for bulk book format export

**Wiki Format Features:**
- AI-powered single-page wiki generation
- Smart merge and rebuild functionality for updates
- Hierarchical table of contents with user questions
- Automatic trivial chat filtering

### Enhanced Header
- Bold formatting for generation timestamp
- Cleaner visual presentation
- Consistent across all export formats

## 🔍 Troubleshooting

### Common Issues

#### "Claude projects directory not found"
```bash
# Check if Claude Desktop is installed and has been used
ls ~/.claude/projects/
```

#### "No valid messages found"
- Ensure the JSONL files aren't corrupted
- Try with `-f raw` to see the original JSON structure

#### "Permission denied"
```bash
# Make sure the script is executable
chmod +x claude-reader.py
```

#### Navigation doesn't work on Windows
- The script falls back to Enter-based navigation on Windows
- All functionality remains available, just press Enter instead of single keys

### Debug Mode
For troubleshooting, use the raw format to inspect the JSON structure:
```bash
python3 claude-reader.py "My Project" -f raw | head -50
```

## 📝 Examples

### Daily Workflow
```bash
# Quick check of recent projects
python3 claude-chat-manager.py -r 5

# Search for specific topics
python3 claude-chat-manager.py -c "docker deployment"

# Browse and export a project in clean book format
python3 claude-chat-manager.py "My Important Project" -f book -o my-docs
```

### Documentation Generation
```bash
# Export all projects in clean book format for documentation
python3 claude-chat-manager.py "Docker Setup" -f book -o docker-docs
python3 claude-chat-manager.py "API Development" -f book -o api-docs
python3 claude-chat-manager.py "System Scripts" -f book -o scripts-docs

# Generate comprehensive project wikis
python3 claude-chat-manager.py "Docker Setup" --wiki docker-wiki.md
python3 claude-chat-manager.py "API Development" --wiki api-wiki.md

# Update wikis as you add new chats
python3 claude-chat-manager.py "Docker Setup" --wiki docker-wiki.md --update
python3 claude-chat-manager.py "API Development" --wiki api-wiki.md --update
```

### Content Research
```bash
# Find all conversations about specific topics
python3 claude-chat-manager.py -c "authentication"
python3 claude-chat-manager.py -c "database migration"
python3 claude-chat-manager.py -c "error handling"
```

## 🆕 What's New in v2.0

### Major Improvements
- **🏗️ Modular Architecture**: Refactored into 14 focused modules (all under 800 lines)
- **✅ Comprehensive Testing**: 73 unit tests with pytest, all passing
- **📝 Full Documentation**: Google-style docstrings, type hints on all functions
- **🔧 Configuration**: Environment variable support via `.env` file
- **📊 Professional Code**: PEP8 compliant, proper logging, custom exceptions
- **⚡ Non-Interactive Export**: Direct export with `-o` flag (no menu required)
- **📚 Wiki Generation**: AI-powered single-page wiki with LLM-generated titles
- **🔄 Wiki Updates**: Smart merge and rebuild functionality for existing wikis (NEW!)

### Code Quality
- **Type Safety**: 100% type hint coverage
- **Error Handling**: Custom exception hierarchy
- **Logging**: Proper logging module (replaces print statements)
- **Testing**: Automated test suite with coverage reporting
- **Documentation**: Complete architecture and development guides

### Configuration Support

Create a `.env` file **in the project directory** to customize behavior:

```bash
# Copy the example file
cp .env.example .env

# Edit with your settings
nano .env
```

Example configuration:
```bash
# Custom Claude projects directory
CLAUDE_PROJECTS_DIR=/path/to/custom/projects

# Logging level (DEBUG, INFO, WARNING, ERROR)
CLAUDE_LOG_LEVEL=INFO

# Default export format
CLAUDE_DEFAULT_FORMAT=book

# OpenRouter API for wiki generation (optional)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
OPENROUTER_MODEL=anthropic/claude-haiku-4.5

# Wiki generation settings
WIKI_TITLE_MAX_TOKENS=2000
WIKI_GENERATE_TITLES=true
```

**Important:** The `.env` file is loaded from the script's installation directory, not your current working directory. This means you can run the tool from anywhere and it will still use the same configuration.

See `.env.example` for all available options.

### Wiki Generation Feature

The wiki feature transforms your entire project history into a single, well-organized documentation page:

**Use Cases:**
- 📚 **Project Documentation**: Generate comprehensive docs from development chats
- 🔍 **Knowledge Base**: Create searchable reference material from Q&A sessions
- 📖 **Learning Resource**: Convert technical discussions into tutorial-style guides
- 🗂️ **Archive**: Preserve important conversations in clean, readable format
- 🤝 **Sharing**: Export project history for team members or stakeholders
- 🔄 **Living Documentation**: Update wikis incrementally as you add new chats (NEW!)

**How It Works:**

*Initial Generation:*
1. Analyzes all chats in a project
2. Uses AI to generate descriptive titles (or falls back to first question)
3. Filters out tool use/result noise for clean reading
4. Sorts chronologically by date
5. Creates table of contents with anchor links
6. Preserves code blocks and file references
7. Embeds hidden metadata for future updates
8. Outputs single markdown file

*Updating Existing Wikis:*
1. Parses existing wiki to extract chat IDs and cached titles
2. Compares with current project chats to identify new ones
3. **Update mode**: Reuses cached titles (saves API costs), generates titles only for new chats, smart merge (append or full rebuild)
4. **Rebuild mode**: Regenerates all titles from scratch, ignores cache, fresh generation
5. Automatic strategy selection based on chat timestamps

**Update Strategies:**
- **Append-Only**: Used when all new chats are newer than existing ones (fast)
- **Full Rebuild**: Used when new chats need chronological insertion (thorough)
- **Title Caching**: Stored in invisible HTML comments, reused in update mode

**Configuration:**
- **Model**: Default is `anthropic/claude-haiku-4.5` (fast, cost-effective, latest version)
- **Token Limit**: Analyzes first 2000 tokens of each chat for title
- **Fallback**: Automatically uses first user question if LLM fails
- **Zero Dependencies**: Uses Python's standard library (no requests/httpx needed)
- **Metadata Format**: `<!-- wiki-meta: chat_id=abc12345, timestamp=1704412800 -->`

## 🆕 Book Format Use Cases

The enhanced book format is perfect for:
- **📚 Documentation**: Create clean reference materials with auto-generated descriptive filenames
- **📤 Sharing**: Export conversations in a professional format, filtered for quality
- **📝 Tutorials**: Convert technical discussions into tutorial-style documents without tool noise
- **🎯 Focus**: Read conversations without timestamps, metadata, or system notifications
- **📖 Archiving**: Store important conversations in a clean, timeless format
- **🔍 Quality Control**: Automatically filter out trivial warmup/test conversations
- **🏢 Professional Use**: Generate client-ready documentation from development chats

## 🤝 Contributing

Feel free to contribute improvements:
1. Add support for additional export formats
2. Enhance search functionality
3. Improve pager navigation
4. Add filtering options
5. Optimize performance for very large chat histories

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development guidelines.

## 📚 Documentation

- **[REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)** - Complete v2.0 refactoring details
- **[TEST_REPORT.md](TEST_REPORT.md)** - Test results and coverage
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Development guide
- **[.env.example](.env.example)** - Configuration template

## 🧪 Testing

Run the test suite:
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src
```

All 73 tests passing! ✅

## 📄 License

This tool is provided as-is for personal use with Claude Desktop chat histories. Respect Claude's terms of service when using this tool.

## 🔗 Related Tools

- **Claude Desktop**: The official Claude application
- **Kiro IDE**: Alternative Claude-powered IDE with chat support
- **merge-chats.py**: Included utility for merging exports from multiple sources
- **sanitize-chats.py**: Included utility for post-processing sensitive data
- **jq**: Command-line JSON processor for manual JSONL inspection
- **less**: Unix pager that inspired the navigation system
- **grep**: For additional content searching capabilities

---

## 🎯 Project Stats

- **Version**: 3.0.0
- **Python**: 3.9+
- **Modules**: 19 source modules
- **Tests**: 448 unit tests (100% passing)
- **Coverage**: Core modules 52-100%
- **Type Hints**: 100% coverage
- **Documentation**: Complete with examples and enhancement guide
- **Chat Sources**: Claude Desktop + Kiro IDE + Codex CLI
- **Utilities**:
  - **merge-chats.py** - Intelligent chat file merging
  - **sanitize-chats.py** - Sensitive data sanitization
- **Features**: 5 export formats including:
  - Enhanced book mode with intelligent filtering
  - Single-chat export with action menu
  - Machine-hostname-based directory naming
  - AI-powered wiki with update/rebuild capabilities
  - Shared filtering architecture across modes
  - Multi-source support (Claude Desktop + Kiro IDE + Codex CLI)

---

**Made with ❤️ for the Claude community**

*Version 3.0 - Claude Desktop, Kiro IDE, and Codex CLI support!*
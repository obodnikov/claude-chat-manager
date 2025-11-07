# Claude Chat Manager 🤖

A powerful Python tool to browse, read, and export Claude Desktop's JSONL chat files with an intuitive interface and Unix `less`-like paging for smooth reading experience.

**Version 2.0** - Fully refactored with modular architecture, comprehensive testing, and professional code standards.

## ✨ Features

- 📋 **Interactive Project Browser** - Navigate through all your Claude projects
- 🔍 **Smart Search** - Search project names and chat content across all conversations
- 📖 **Paged Chat Viewing** - Unix `less`-like navigation for comfortable reading
- 📊 **Multiple Export Formats** - Pretty terminal output, Markdown, clean Book format, or raw JSON
- 📚 **Wiki Generation** - NEW! Generate AI-powered single-page wikis from entire projects
- 🤖 **AI-Powered Titles** - Automatic chat title generation using LLM (via OpenRouter)
- 🎯 **Batch Export** - Export entire projects to organized Markdown files
- 🎨 **Colored Output** - Beautiful terminal interface with syntax highlighting
- ⚡ **Fast Performance** - Efficient parsing of large chat histories
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
- **1-9**: View specific chat
- **a**: View all chats sequentially
- **e**: Export all chats to markdown
- **eb**: Export all chats to book format (NEW!)
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

### Book Format (Clean & Readable)
```markdown
# Claude Chat Export

**Generated: 2025-09-21 12:25:52**

> should i include package-lock file in .gitignore

I'll check your current .gitignore file to see what's already included and provide guidance on package-lock.json.

🔧 [Tool Use: Read]
   File: /home/mike/src/pollen-local-api/.gitignore

For Node.js projects, the decision about package-lock.json in .gitignore depends on your project type...

> what about yarn.lock?

For yarn.lock, the recommendation is different from package-lock.json...
```

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

# Creates directories like:
# ProjectName_export_20250921_103000/
# ProjectName_book_export_20250921_103000/
#   ├── chat-session-1.md
#   ├── mobile-fixes.md
#   └── api-optimization.md
```

### Search Features
- **Project Search**: Find projects by name (supports partial matching)
- **Content Search**: Search across all chat content with context preview
- **Recent Filter**: Quickly find recently modified conversations

## 📁 File Structure

Claude Desktop stores projects in:
- **Linux/macOS**: `~/.claude/projects/`
- **Windows**: `%USERPROFILE%\.claude\projects\`

Each project contains `.jsonl` files representing individual chats.

## 🛠️ What's New

### Book Format Features
- **Clean presentation**: Removes timestamps and message numbers for distraction-free reading
- **Simple user questions**: Questions appear as simple blockquotes (`> question text`)
- **Direct responses**: Assistant answers without headers or metadata
- **Perfect for sharing**: Creates clean, readable documents ideal for documentation or reference
- **Batch export**: Use `eb` command in project browser for bulk book format export

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

The book format is perfect for:
- **📚 Documentation**: Create clean reference materials from conversations
- **📤 Sharing**: Export conversations in a professional, readable format
- **📝 Tutorials**: Convert technical discussions into tutorial-style documents
- **🎯 Focus**: Read conversations without timestamp and metadata distractions
- **📖 Archiving**: Store important conversations in a clean, timeless format

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
- **jq**: Command-line JSON processor for manual JSONL inspection
- **less**: Unix pager that inspired the navigation system
- **grep**: For additional content searching capabilities

---

## 🎯 Project Stats

- **Version**: 2.0.0
- **Python**: 3.9+
- **Modules**: 14 source modules (wiki_parser added)
- **Tests**: 73 unit tests (100% passing)
- **Coverage**: Core modules 52-100%
- **Type Hints**: 100% coverage
- **Documentation**: Complete with examples
- **Features**: 5 export formats including AI-powered wiki with update/rebuild capabilities

---

**Made with ❤️ for the Claude community**

*Version 2.0 - Production-ready with professional code standards!*
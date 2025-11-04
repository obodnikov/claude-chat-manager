# Claude Chat Reader 🤖

A powerful Python tool to browse, read, and export Claude Desktop's JSONL chat files with an intuitive interface and Unix `less`-like paging for smooth reading experience.

## ✨ Features

- 📋 **Interactive Project Browser** - Navigate through all your Claude projects
- 🔍 **Smart Search** - Search project names and chat content across all conversations
- 📖 **Paged Chat Viewing** - Unix `less`-like navigation for comfortable reading
- 📊 **Multiple Export Formats** - Pretty terminal output, Markdown, clean Book format, or raw JSON
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
# Download the script
curl -o claude-reader.py [script-url]
# or copy the script content to claude-reader.py

# Make it executable
chmod +x claude-reader.py

# Run it
python3 claude-reader.py
```

### System-wide Installation
```bash
# Install globally
sudo cp claude-reader.py /usr/local/bin/claude-reader
sudo chmod +x /usr/local/bin/claude-reader

# Now use from anywhere
claude-reader --list
```

### Create Alias
```bash
# Add to ~/.bashrc or ~/.zshrc
alias claude='python3 /path/to/claude-reader.py'

# Usage
claude --list
claude "My Project" -f book
```

## 📖 Usage

### Interactive Browser (Default)
```bash
python3 claude-reader.py
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
python3 claude-reader.py --list
```

#### Search Projects
```bash
# Search by project name
python3 claude-reader.py --search "docker"
python3 claude-reader.py -s "pollen"
```

#### Search Chat Content
```bash
# Find conversations containing specific terms
python3 claude-reader.py --content "update checker"
python3 claude-reader.py -c "systemctl"
```

#### Recent Projects
```bash
# Show 5 most recent projects
python3 claude-reader.py --recent 5
python3 claude-reader.py -r 10
```

#### Browse Specific Project
```bash
# View project chats interactively
python3 claude-reader.py "Docker Container Update Checker"
python3 claude-reader.py "Home Mike Src Pollen Web Application"
```

#### Export Options
```bash
# Export to clean book format (NEW!)
python3 claude-reader.py "My Project" --format book --output clean_chat.md

# Export to markdown file
python3 claude-reader.py "My Project" --format markdown --output chat.md

# Export in different formats
python3 claude-reader.py "My Project" -f pretty    # Terminal output (default)
python3 claude-reader.py "My Project" -f book      # Clean book format
python3 claude-reader.py "My Project" -f markdown  # Standard markdown
python3 claude-reader.py "My Project" -f raw       # Raw JSON
```

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

### Book Format (NEW! - Clean & Readable)
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
claude-reader -r 5

# Search for specific topics
claude-reader -c "docker deployment"

# Browse and export a project in clean book format
claude-reader "My Important Project"
# Then in interactive mode: 'eb' to export in book format
```

### Documentation Generation
```bash
# Export all projects in clean book format for documentation
for project in "Docker Setup" "API Development" "System Scripts"; do
    claude-reader "$project" -f book -o "${project// /-}-book.md"
done
```

### Content Research
```bash
# Find all conversations about specific topics
claude-reader -c "authentication"
claude-reader -c "database migration"
claude-reader -c "error handling"
```

## 🆕 Book Format Use Cases

The new book format is perfect for:
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

## 📄 License

This tool is provided as-is for personal use with Claude Desktop chat histories. Respect Claude's terms of service when using this tool.

## 🔗 Related Tools

- **Claude Desktop**: The official Claude application
- **jq**: Command-line JSON processor for manual JSONL inspection
- **less**: Unix pager that inspired the navigation system
- **grep**: For additional content searching capabilities

---

**Made with ❤️ for the Claude community**

*Featuring the new Book format for clean, distraction-free reading and sharing!*
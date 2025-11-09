# Building Claude Chat Manager Executable

This guide explains how to build standalone executables of Claude Chat Manager using PyInstaller.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Building on Different Platforms](#building-on-different-platforms)
  - [macOS](#macos)
  - [Linux](#linux)
  - [Windows](#windows)
- [What Gets Bundled](#what-gets-bundled)
- [Testing the Executable](#testing-the-executable)
- [Distribution](#distribution)
- [Troubleshooting](#troubleshooting)
- [Advanced Options](#advanced-options)

---

## Prerequisites

### Required
- **Python 3.9 or higher**
- **PyInstaller** (will be installed below)

### Optional
- **UPX** (Universal Packer for eXecutables) - for smaller executable size
  - macOS: `brew install upx`
  - Linux: `sudo apt install upx-ucl` or `sudo yum install upx`
  - Windows: Download from https://upx.github.io/

---

## Quick Start

The fastest way to build an executable:

```bash
# 1. Navigate to project directory
cd /path/to/claude-chat-manager

# 2. Install PyInstaller (if not already installed)
pip install pyinstaller

# 3. Build the executable
pyinstaller claude-chat-manager.spec

# 4. Find your executable
# macOS/Linux: dist/claude-chat-manager
# Windows: dist/claude-chat-manager.exe
```

That's it! The executable is now in the `dist/` directory.

---

## Building on Different Platforms

### macOS

```bash
# Install PyInstaller
pip3 install pyinstaller

# Optional: Install UPX for smaller executable
brew install upx

# Build the executable
pyinstaller claude-chat-manager.spec

# The executable will be at:
# dist/claude-chat-manager
# Size: ~8-12 MB (with UPX: ~4-6 MB)

# Make it executable (should already be)
chmod +x dist/claude-chat-manager

# Test it
./dist/claude-chat-manager --list
```

**macOS-specific notes:**
- The executable works on macOS 10.13+ (High Sierra and newer)
- Code signing: If you want to distribute widely, consider signing:
  ```bash
  codesign -s "Developer ID Application: Your Name" dist/claude-chat-manager
  ```
- Notarization: For distribution outside App Store, you may need to notarize

### Linux

```bash
# Install PyInstaller
pip3 install pyinstaller

# Optional: Install UPX for smaller executable
sudo apt install upx-ucl  # Debian/Ubuntu
sudo yum install upx      # RHEL/CentOS/Fedora

# Build the executable
pyinstaller claude-chat-manager.spec

# The executable will be at:
# dist/claude-chat-manager
# Size: ~8-12 MB (with UPX: ~4-6 MB)

# Make it executable (should already be)
chmod +x dist/claude-chat-manager

# Test it
./dist/claude-chat-manager --list
```

**Linux-specific notes:**
- Build on the oldest Linux distribution you want to support
- Executables built on newer systems may not work on older ones
- Consider building in a Docker container for maximum compatibility:
  ```bash
  docker run -v $(pwd):/src python:3.9-slim bash -c \
    "cd /src && pip install pyinstaller && pyinstaller claude-chat-manager.spec"
  ```

### Windows

```powershell
# Install PyInstaller
pip install pyinstaller

# Optional: Install UPX for smaller executable
# Download from https://upx.github.io/ and add to PATH

# Build the executable
pyinstaller claude-chat-manager.spec

# The executable will be at:
# dist\claude-chat-manager.exe
# Size: ~8-12 MB (with UPX: ~4-6 MB)

# Test it
.\dist\claude-chat-manager.exe --list
```

**Windows-specific notes:**
- Windows Defender may flag the executable as suspicious (false positive)
- To avoid this, consider code signing with a certificate
- Build with Python from python.org (not Microsoft Store version)

---

## What Gets Bundled

The spec file creates a **single-file executable** that includes:

### ✅ Included
- Python runtime (embedded)
- Main script: `claude-chat-manager.py`
- All source modules from `src/` directory:
  - `cli.py`, `colors.py`, `config.py`, `display.py`
  - `exceptions.py`, `exporters.py`, `filters.py`, `formatters.py`
  - `llm_client.py`, `models.py`, `parser.py`, `projects.py`
  - `search.py`, `wiki_generator.py`, `wiki_parser.py`
- Configuration template: `.env.example`
- Standard library modules

### ❌ NOT Included
- Your personal `.env` file (by design - for security)
- Test files (`tests/`)
- Documentation (`docs/`)
- Development dependencies (`pytest`, `mypy`, etc.)
- Virtual environment files
- Git history

### 🔒 Security Note
Your `.env` file is **intentionally excluded** to protect:
- Your OpenRouter API key
- Custom directory paths
- Personal configuration settings

Users of the executable will create their own `.env` file.

---

## Testing the Executable

### Basic Functionality Test

```bash
# Navigate to dist directory
cd dist

# Test help
./claude-chat-manager --help

# Test listing projects
./claude-chat-manager --list

# Test interactive browser
./claude-chat-manager

# Test search
./claude-chat-manager --search "test"

# Test export (if you have projects)
./claude-chat-manager "Project Name" -f book -o output/
```

### Verify All Features Work

1. **Interactive Browser** ✓
   ```bash
   ./claude-chat-manager
   # Navigate through menus, view chats
   ```

2. **Export Formats** ✓
   ```bash
   ./claude-chat-manager "Project" -f pretty -o test.txt
   ./claude-chat-manager "Project" -f markdown -o test.md
   ./claude-chat-manager "Project" -f book -o test-book.md
   ```

3. **Wiki Generation** ✓ (requires API key)
   ```bash
   # Create .env with your API key
   echo "OPENROUTER_API_KEY=sk-or-v1-xxxxx" > .env
   ./claude-chat-manager "Project" --wiki test-wiki.md
   ```

4. **Search Features** ✓
   ```bash
   ./claude-chat-manager --search "docker"
   ./claude-chat-manager --content "script"
   ./claude-chat-manager --recent 5
   ```

### Configuration Test

The executable looks for `.env` in this order:
1. Current working directory (`./.env`)
2. User's config directory (`~/.config/claude-chat-manager/.env`)
3. Falls back to defaults

Test configuration loading:
```bash
# Create test .env
cat > .env << EOF
CLAUDE_LOG_LEVEL=DEBUG
CLAUDE_DEFAULT_FORMAT=book
EOF

# Run with DEBUG logging
./claude-chat-manager --list
# Should show DEBUG log messages
```

---

## Distribution

### Sharing the Executable

The built executable is **completely standalone**. Recipients don't need:
- Python installed
- pip packages
- Virtual environments
- Any dependencies

### Distribution Methods

#### 1. Direct File Sharing
```bash
# Just share the executable file
cp dist/claude-chat-manager ~/Desktop/
# Send to users via email, file sharing, etc.
```

#### 2. GitHub Releases
```bash
# Create a release with the executable
# Users download from: https://github.com/user/repo/releases

# Example commands:
cd dist
tar -czf claude-chat-manager-macos.tar.gz claude-chat-manager
# Upload to GitHub Releases
```

#### 3. Installation Script
Create a simple installer:

**install.sh** (for macOS/Linux):
```bash
#!/bin/bash
# Copy executable to /usr/local/bin
sudo cp claude-chat-manager /usr/local/bin/
sudo chmod +x /usr/local/bin/claude-chat-manager

# Copy .env.example to user's config directory
mkdir -p ~/.config/claude-chat-manager
cp .env.example ~/.config/claude-chat-manager/

echo "Installed! Run: claude-chat-manager"
```

#### 4. Package Managers

**Homebrew** (macOS/Linux):
```ruby
# Create a Homebrew formula
class ClaudeChatManager < Formula
  desc "Browse and export Claude Desktop chat files"
  homepage "https://github.com/user/claude-chat-manager"
  url "https://github.com/user/claude-chat-manager/releases/download/v2.2.0/claude-chat-manager-macos.tar.gz"
  sha256 "..."

  def install
    bin.install "claude-chat-manager"
  end
end
```

### User Setup Instructions

Include these instructions with your distribution:

```markdown
# Claude Chat Manager - Setup

## Installation

1. **Download** the executable for your platform:
   - macOS: `claude-chat-manager` (macOS)
   - Linux: `claude-chat-manager` (Linux)
   - Windows: `claude-chat-manager.exe` (Windows)

2. **Make executable** (macOS/Linux):
   ```bash
   chmod +x claude-chat-manager
   ```

3. **Optional: Install system-wide** (macOS/Linux):
   ```bash
   sudo mv claude-chat-manager /usr/local/bin/
   ```

## Configuration (Optional)

For wiki generation features, create a `.env` file:

```bash
# Extract the example configuration
cat > .env << EOF
OPENROUTER_API_KEY=sk-or-v1-your-key-here
EOF
```

## Usage

```bash
# Interactive browser
./claude-chat-manager

# List all projects
./claude-chat-manager --list

# Export project
./claude-chat-manager "My Project" -f book -o exports/
```
```

---

## Troubleshooting

### Common Issues

#### "Permission denied" (macOS/Linux)
```bash
# Make the executable runnable
chmod +x dist/claude-chat-manager
```

#### "File is damaged and can't be opened" (macOS)
```bash
# This is Gatekeeper protection. Allow it:
xattr -d com.apple.quarantine dist/claude-chat-manager

# Or right-click → Open → Open anyway
```

#### "Windows protected your PC" (Windows)
- Click "More info" → "Run anyway"
- This is SmartScreen filter for unsigned executables
- Consider code signing for production distribution

#### Executable is too large
```bash
# Install UPX for compression
brew install upx  # macOS
sudo apt install upx-ucl  # Linux

# Rebuild
pyinstaller claude-chat-manager.spec
# Size should reduce by ~50%
```

#### Module not found errors
```bash
# Ensure all src/ modules are in the spec file
# Check hiddenimports list in claude-chat-manager.spec

# Rebuild with verbose output
pyinstaller claude-chat-manager.spec --log-level DEBUG
```

#### "Claude projects directory not found"
```bash
# The executable looks in default location: ~/.claude/projects/
# If your projects are elsewhere, create .env:
echo "CLAUDE_PROJECTS_DIR=/custom/path" > .env
```

### Debug Build

For troubleshooting, create a debug build:

```bash
# Edit claude-chat-manager.spec
# Change: debug=False
# To:     debug=True

# Rebuild
pyinstaller claude-chat-manager.spec

# Run with verbose output
./dist/claude-chat-manager --list
```

### Clean Build

If you encounter issues, try a clean build:

```bash
# Remove build artifacts
rm -rf build/ dist/ *.spec~

# Rebuild
pyinstaller claude-chat-manager.spec
```

---

## Advanced Options

### One-Directory Build (Alternative)

Instead of a single file, create a directory with dependencies:

**claude-chat-manager-onedir.spec:**
```python
# Change the EXE section to:
exe = EXE(
    pyz,
    a.scripts,
    [],  # Don't bundle everything
    exclude_binaries=True,  # Keep binaries separate
    name='claude-chat-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='claude-chat-manager',
)
```

**Pros:**
- Faster startup time
- Easier to debug
- Can see bundled files

**Cons:**
- Must distribute entire directory
- Less portable

Build:
```bash
pyinstaller claude-chat-manager-onedir.spec
# Creates: dist/claude-chat-manager/ directory
```

### Custom Icon

Add an icon to your executable:

```bash
# Create or download an icon file:
# - macOS: .icns file
# - Windows: .ico file
# - Linux: .png (converted to .ico)

# Edit claude-chat-manager.spec:
# icon='path/to/icon.icns'  # macOS
# icon='path/to/icon.ico'   # Windows

# Rebuild
pyinstaller claude-chat-manager.spec
```

### Version Information (Windows)

Add version metadata for Windows:

```python
# In claude-chat-manager.spec, add after imports:
version_info = (
    ('FileVersion', '2.2.0.0'),
    ('ProductVersion', '2.2.0.0'),
    ('FileDescription', 'Claude Chat Manager'),
    ('CompanyName', 'Claude Chat Manager Team'),
    ('ProductName', 'Claude Chat Manager'),
    ('LegalCopyright', 'Copyright (c) 2025'),
)

# Add to EXE():
exe = EXE(
    # ... existing parameters ...
    version='version_info.txt',  # Create this file with above info
)
```

### Cross-Platform Builds

**Important:** PyInstaller executables are **platform-specific**. You cannot:
- Build on macOS for Windows
- Build on Linux for macOS
- Build on Windows for Linux

**Solutions:**

1. **Use separate machines** for each platform
2. **Use CI/CD** (GitHub Actions, GitLab CI):
   ```yaml
   # .github/workflows/build.yml
   name: Build Executables
   on: [push]
   jobs:
     build-macos:
       runs-on: macos-latest
       steps:
         - uses: actions/checkout@v2
         - run: pip install pyinstaller
         - run: pyinstaller claude-chat-manager.spec
         - uses: actions/upload-artifact@v2
           with:
             name: claude-chat-manager-macos
             path: dist/claude-chat-manager
   ```

3. **Use Docker** for Linux builds (from any platform)

### Optimization

Make the executable smaller and faster:

```bash
# 1. Install UPX
brew install upx  # macOS

# 2. Enable UPX in spec (already enabled)
# upx=True in EXE()

# 3. Exclude unused modules
# Add to excludes list in Analysis()

# 4. Strip debug symbols (Linux/macOS)
# After building:
strip dist/claude-chat-manager

# 5. Remove docstrings at build time
# Add to spec file:
# import sys
# sys.dont_write_bytecode = True
```

---

## Build Script (Optional)

Create an automated build script:

**build.sh:**
```bash
#!/bin/bash
# Build script for Claude Chat Manager

set -e  # Exit on error

echo "🚀 Building Claude Chat Manager..."

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/

# Install/upgrade PyInstaller
echo "📦 Installing PyInstaller..."
pip install --upgrade pyinstaller

# Build executable
echo "🔨 Building executable..."
pyinstaller claude-chat-manager.spec

# Test the build
echo "✅ Testing executable..."
./dist/claude-chat-manager --help > /dev/null

# Show size
echo "📊 Executable size:"
ls -lh dist/claude-chat-manager

echo "✨ Build complete! Executable: dist/claude-chat-manager"
```

Usage:
```bash
chmod +x build.sh
./build.sh
```

---

## Platform-Specific Installers

### macOS DMG

Create a disk image for distribution:

```bash
# Install create-dmg
brew install create-dmg

# Create DMG
create-dmg \
  --volname "Claude Chat Manager" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --app-drop-link 600 185 \
  "claude-chat-manager.dmg" \
  "dist/"
```

### Linux Package (.deb)

Create a Debian package:

```bash
# Install fpm
gem install fpm

# Create .deb package
fpm -s dir -t deb \
  -n claude-chat-manager \
  -v 2.2.0 \
  --description "Browse and export Claude Desktop chat files" \
  --url "https://github.com/user/claude-chat-manager" \
  --license "MIT" \
  dist/claude-chat-manager=/usr/local/bin/
```

### Windows Installer

Use Inno Setup or NSIS to create an installer.

---

## Summary

### Quick Reference

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller claude-chat-manager.spec

# Find executable
# macOS/Linux: dist/claude-chat-manager
# Windows: dist/claude-chat-manager.exe

# Test it
./dist/claude-chat-manager --list

# Distribute the single executable file
# Users don't need Python or any dependencies!
```

### File Checklist for Distribution

When distributing, include:
- ✅ `claude-chat-manager` (or `.exe`) - The executable
- ✅ `.env.example` - Configuration template (optional, already bundled)
- ✅ `README.md` - Usage instructions (optional)
- ❌ `.env` - **NEVER** distribute (contains secrets)

---

For more information, see:
- [README.md](../README.md) - Main documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [PyInstaller Documentation](https://pyinstaller.org/)

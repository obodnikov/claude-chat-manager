# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Claude Chat Manager.

This spec file creates a single-file executable that bundles:
- The main script (claude-chat-manager.py)
- All source modules from src/ directory
- Configuration template (.env.example)

Usage:
    pyinstaller claude-chat-manager.spec

The resulting executable will be in dist/claude-chat-manager
"""

import sys
from pathlib import Path

# Get the project root directory
project_root = Path('.').absolute()

# Define all source modules to include
src_modules = [
    'src/__init__.py',
    'src/cli.py',
    'src/colors.py',
    'src/config.py',
    'src/display.py',
    'src/exceptions.py',
    'src/exporters.py',
    'src/filters.py',
    'src/formatters.py',
    'src/llm_client.py',
    'src/models.py',
    'src/parser.py',
    'src/projects.py',
    'src/search.py',
    'src/wiki_generator.py',
    'src/wiki_parser.py',
]

# Data files to include (template configuration)
datas = [
    ('.env.example', '.'),  # Bundle .env.example as reference
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'src',
    'src.cli',
    'src.colors',
    'src.config',
    'src.display',
    'src.exceptions',
    'src.exporters',
    'src.filters',
    'src.formatters',
    'src.llm_client',
    'src.models',
    'src.parser',
    'src.projects',
    'src.search',
    'src.wiki_generator',
    'src.wiki_parser',
]

# Analysis phase - collect all dependencies
a = Analysis(
    ['claude-chat-manager.py'],  # Main entry point
    pathex=[str(project_root)],  # Additional paths to search
    binaries=[],  # No binary dependencies
    datas=datas,  # Data files to bundle
    hiddenimports=hiddenimports,  # Hidden imports
    hookspath=[],  # No custom hooks
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',  # Exclude unused GUI libraries
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,  # No encryption
    noarchive=False,
)

# PYZ (Python archive) - compressed Python modules
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None
)

# EXE (executable) - single-file bundle
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='claude-chat-manager',  # Output executable name
    debug=False,  # Set to True for debugging
    bootloader_ignore_signals=False,
    strip=False,  # Don't strip symbols (better error messages)
    upx=True,  # Use UPX compression if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console application (CLI tool)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one (e.g., 'icon.ico' or 'icon.icns')
)

# Platform-specific notes:
# - macOS: Creates a single executable file
# - Linux: Creates a single executable file
# - Windows: Creates claude-chat-manager.exe
#
# The executable will look for .env configuration in:
# 1. Current working directory
# 2. User's home directory (.config/claude-chat-manager/.env)
# 3. Fall back to defaults if not found

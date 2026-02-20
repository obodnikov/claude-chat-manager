"""Setup script for Claude Chat Manager."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="claude-chat-manager",
    version="3.0.0",
    author="Claude Chat Manager Team",
    description="A tool to browse and export Claude Desktop chat files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/claude-chat-manager",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        # No runtime dependencies - uses standard library only
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.5.0",
            "pylint>=2.17.0",
            "flake8>=6.1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "claude-chat-manager=claude_chat_manager:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)

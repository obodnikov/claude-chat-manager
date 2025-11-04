# Development Guide

## Setup Development Environment

### 1. Clone the repository
```bash
git clone <repository-url>
cd claude-chat-manager
```

### 2. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install development tools
```bash
pip install -e ".[dev]"
```

## Code Style

### PEP 8 Compliance
All code must follow PEP 8 style guidelines:
- 4 spaces for indentation
- Max line length: 100 characters
- Two blank lines between top-level definitions
- Use snake_case for functions and variables
- Use PascalCase for classes

### Type Hints
All functions must include type hints:
```python
def format_timestamp(ts: Optional[Union[str, int, float]]) -> str:
    """Format timestamp to readable format."""
    pass
```

### Docstrings
Use Google-style docstrings:
```python
def my_function(param1: str, param2: int) -> bool:
    """Short description of function.

    Longer description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param2 is negative.

    Example:
        >>> my_function("test", 42)
        True
    """
    pass
```

## Code Quality Tools

### Black (Code Formatter)
```bash
black src/ tests/
```

### Mypy (Type Checker)
```bash
mypy src/
```

### Pylint (Linter)
```bash
pylint src/
```

### Flake8 (Style Guide Enforcement)
```bash
flake8 src/ tests/
```

## Testing

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_formatters.py

# Run specific test
pytest tests/test_formatters.py::TestFormatTimestamp::test_format_timestamp_none

# Run in verbose mode
pytest -v
```

### Writing Tests
Place tests in `tests/` directory with `test_` prefix:

```python
"""Tests for my_module module."""

import pytest
from src.my_module import my_function


class TestMyFunction:
    """Tests for my_function."""

    def test_basic_case(self):
        """Test basic functionality."""
        result = my_function("input")
        assert result == "expected"

    def test_edge_case(self):
        """Test edge case."""
        with pytest.raises(ValueError):
            my_function("")
```

### Test Coverage
Aim for >80% test coverage:
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## Module Guidelines

### Keep Modules Small
- Each module should be under 800 lines
- Split large modules into smaller, focused ones
- Each module should have a single responsibility

### Use Proper Imports
```python
# Good
from pathlib import Path
from typing import List, Optional

from .config import config
from .exceptions import ClaudeReaderError

# Avoid
from src.config import *
import sys, os  # Multiple imports on one line
```

### Error Handling
Use custom exceptions and logging:
```python
import logging

from .exceptions import ProjectNotFoundError

logger = logging.getLogger(__name__)

def my_function(path: Path) -> None:
    """My function."""
    if not path.exists():
        logger.error(f"Path not found: {path}")
        raise ProjectNotFoundError(f"Project not found at {path}")

    try:
        # Do something
        pass
    except Exception as e:
        logger.exception("Unexpected error")
        raise
```

## Configuration

### Environment Variables
Use `.env.example` as template:
```bash
cp .env.example .env
# Edit .env with your settings
```

### Config Module
Add new config values to `src/config.py`:
```python
@property
def my_new_setting(self) -> str:
    """Get my new setting.

    Returns:
        Setting value.
    """
    return os.getenv('MY_NEW_SETTING', 'default_value')
```

## Logging

### Setup Logging
Logging is configured in `claude-chat-manager.py`:
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed information for debugging")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message")
logger.exception("Error with traceback")
```

### Log Levels
- **DEBUG**: Detailed debugging information
- **INFO**: General informational messages
- **WARNING**: Warning messages
- **ERROR**: Error messages
- **CRITICAL**: Critical errors

## Git Workflow

### Branching Strategy
```bash
# Feature branch
git checkout -b feature/my-feature

# Bug fix branch
git checkout -b fix/bug-description

# Commit changes
git add .
git commit -m "Add: description of changes"
```

### Commit Messages
Follow conventional commits:
- `Add:` New feature
- `Fix:` Bug fix
- `Update:` Update existing feature
- `Refactor:` Code refactoring
- `Test:` Add or update tests
- `Docs:` Documentation changes

### Before Committing
```bash
# Format code
black src/ tests/

# Run linters
flake8 src/ tests/
pylint src/

# Type check
mypy src/

# Run tests
pytest
```

## Adding New Features

### 1. Create Feature Branch
```bash
git checkout -b feature/my-feature
```

### 2. Write Tests First (TDD)
Create test file in `tests/`:
```python
def test_my_new_feature():
    """Test new feature."""
    result = my_new_function()
    assert result == expected
```

### 3. Implement Feature
Create or modify module in `src/`:
```python
def my_new_function() -> str:
    """My new function.

    Returns:
        Result string.
    """
    return "result"
```

### 4. Update Documentation
Update relevant docs:
- `README.md` - User-facing changes
- `docs/ARCHITECTURE.md` - Architectural changes
- `docs/DEVELOPMENT.md` - Development process changes

### 5. Run Quality Checks
```bash
pytest --cov=src
black src/ tests/
flake8 src/ tests/
mypy src/
```

### 6. Commit and Push
```bash
git add .
git commit -m "Add: my new feature"
git push origin feature/my-feature
```

## Debugging

### Using Python Debugger
```python
import pdb

def my_function():
    x = 42
    pdb.set_trace()  # Debugger will stop here
    return x
```

### Verbose Logging
```bash
# Enable debug logging
export CLAUDE_LOG_LEVEL=DEBUG
python claude-chat-manager.py -v
```

### Check Log File
```bash
tail -f claude-chat-manager.log
```

## Performance Profiling

### Using cProfile
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
my_function()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

### Memory Profiling
```bash
pip install memory-profiler

python -m memory_profiler claude-chat-manager.py
```

## Release Process

### 1. Update Version
Update version in:
- `setup.py`
- `src/__init__.py`

### 2. Update Changelog
Document changes in `CHANGELOG.md`

### 3. Run Full Test Suite
```bash
pytest --cov=src
```

### 4. Build Package
```bash
python setup.py sdist bdist_wheel
```

### 5. Tag Release
```bash
git tag -a v2.0.0 -m "Release version 2.0.0"
git push origin v2.0.0
```

## Troubleshooting

### Import Errors
Ensure `src/` is in Python path:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
```

### Test Failures
Run tests with verbose output:
```bash
pytest -vv --tb=long
```

### Type Check Errors
Ignore specific errors if needed:
```python
# type: ignore
```

But prefer fixing the actual issue!

## Resources

- [PEP 8 Style Guide](https://pep8.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Pytest Documentation](https://docs.pytest.org/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

"""Tests for sanitize-chats.py post-processing script."""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

# Add parent directory to path for script import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from the script
import importlib.util
spec = importlib.util.spec_from_file_location(
    "sanitize_chats",
    Path(__file__).parent.parent / "sanitize-chats.py"
)
sanitize_chats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sanitize_chats)

BackupManager = sanitize_chats.BackupManager
FileProcessor = sanitize_chats.FileProcessor

# Also import needed modules
from src.sanitizer import Sanitizer


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir)


@pytest.fixture
def sample_chat_file(temp_dir):
    """Create a sample chat markdown file with secrets."""
    content = """# Claude Chat Export

## Chat 1

**USER:**
Here's my API key: sk-proj-abc123xyz789def456ghi789jkl012mno345

**ASSISTANT:**
I see you shared an API key. Please keep it secure.

## Chat 2

**USER:**
Use this token: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9

Set the password: myPassword123

And the env var:
```bash
export OPENROUTER_API_KEY=sk-or-v1-secret123456789abc
```
"""

    file_path = temp_dir / "test_chat.md"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def clean_chat_file(temp_dir):
    """Create a chat file with no secrets."""
    content = """# Claude Chat Export

**USER:**
This is a clean chat with no sensitive information.

**ASSISTANT:**
Great! This file should not trigger any sanitization.
"""

    file_path = temp_dir / "clean_chat.md"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sanitizer():
    """Create a configured sanitizer instance."""
    return Sanitizer(
        enabled=True,
        level='balanced',
        style='partial',
        sanitize_paths=False
    )


class TestBackupManager:
    """Test backup file management."""

    def test_create_backup(self, temp_dir, sample_chat_file):
        """Test backup file creation."""
        manager = BackupManager(create_backups=True)

        backup_path = manager.create_backup(sample_chat_file)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix == '.bak'
        assert backup_path in manager.backups_created

        # Verify backup content matches original
        original_content = sample_chat_file.read_text()
        backup_content = backup_path.read_text()
        assert original_content == backup_content

    def test_backup_disabled(self, sample_chat_file):
        """Test backup creation when disabled."""
        manager = BackupManager(create_backups=False)

        backup_path = manager.create_backup(sample_chat_file)

        assert backup_path is None
        assert len(manager.backups_created) == 0

    def test_cleanup_backups(self, temp_dir, sample_chat_file):
        """Test backup cleanup."""
        manager = BackupManager(create_backups=True)

        # Create backups
        backup1 = manager.create_backup(sample_chat_file)
        backup2 = manager.create_backup(sample_chat_file)

        assert backup1.exists()
        assert backup2.exists()

        # Cleanup
        manager.cleanup_backups()

        assert not backup1.exists()
        assert not backup2.exists()

    def test_backup_permission_error(self, temp_dir, sample_chat_file, capsys):
        """Test backup creation with permission error."""
        manager = BackupManager(create_backups=True)

        # Mock shutil.copy2 to raise PermissionError
        with patch('shutil.copy2', side_effect=PermissionError("Access denied")):
            backup_path = manager.create_backup(sample_chat_file)

        assert backup_path is None
        captured = capsys.readouterr()
        assert "Warning" in captured.out or "Warning" in captured.err


class TestFileProcessor:
    """Test file processing logic."""

    def test_find_single_markdown_file(self, temp_dir, sample_chat_file):
        """Test finding a single markdown file."""
        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        files = processor.find_markdown_files([sample_chat_file])

        assert len(files) == 1
        assert files[0] == sample_chat_file

    def test_find_markdown_files_in_directory(self, temp_dir):
        """Test finding all markdown files in a directory."""
        # Create multiple markdown files
        (temp_dir / "chat1.md").write_text("# Chat 1")
        (temp_dir / "chat2.md").write_text("# Chat 2")
        (temp_dir / "notes.txt").write_text("Not markdown")

        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "chat3.md").write_text("# Chat 3")

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        files = processor.find_markdown_files([temp_dir])

        assert len(files) == 3  # Only .md files
        assert all(f.suffix == '.md' for f in files)

    def test_find_files_nonexistent_path(self, temp_dir, capsys):
        """Test handling of nonexistent paths."""
        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        nonexistent = temp_dir / "does_not_exist.md"
        files = processor.find_markdown_files([nonexistent])

        assert len(files) == 0
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_read_file_success(self, sample_chat_file):
        """Test reading a valid file."""
        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = processor.read_file(sample_chat_file)

        assert content is not None
        assert "sk-proj-abc123xyz789def456ghi789jkl012mno345" in content

    def test_read_file_binary(self, temp_dir, capsys):
        """Test reading a binary file."""
        binary_file = temp_dir / "binary.md"
        binary_file.write_bytes(b'\x89PNG\r\n\x1a\n')  # PNG header

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = processor.read_file(binary_file)

        assert content is None
        captured = capsys.readouterr()
        assert "binary" in captured.out.lower()

    def test_write_file_success(self, temp_dir):
        """Test writing file atomically."""
        test_file = temp_dir / "output.md"

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        success = processor.write_file(test_file, "Test content")

        assert success
        assert test_file.exists()
        assert test_file.read_text() == "Test content"

    def test_write_file_atomic_behavior(self, temp_dir):
        """Test that write is atomic (uses temp file via mkstemp)."""
        test_file = temp_dir / "output.md"
        test_file.write_text("Original content")

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        # Mock tempfile.mkstemp to verify it's called
        import tempfile
        original_mkstemp = tempfile.mkstemp
        mkstemp_called = []

        def mock_mkstemp(*args, **kwargs):
            result = original_mkstemp(*args, **kwargs)
            mkstemp_called.append(result)
            return result

        with patch('tempfile.mkstemp', side_effect=mock_mkstemp):
            success = processor.write_file(test_file, "New content")

        # Verify mkstemp was called (atomic write)
        assert len(mkstemp_called) > 0
        assert success is True
        assert test_file.read_text() == "New content"

    def test_process_file_batch_mode(self, sample_chat_file, sanitizer):
        """Test processing file in batch mode."""
        backup_manager = BackupManager(create_backups=False)
        processor = FileProcessor(sanitizer, backup_manager)

        matches_applied, matches_found = processor.process_file(
            sample_chat_file,
            interactive=False,
            preview=False
        )

        assert matches_applied > 0
        assert len(matches_found) > 0

        # Verify file was sanitized
        content = sample_chat_file.read_text()
        assert "sk-proj-abc123xyz789def456ghi789jkl012mno345" not in content  # Original removed
        assert "sk-pr***345" in content or "[API_KEY]" in content  # Redacted present

    def test_process_file_preview_mode(self, sample_chat_file, sanitizer):
        """Test processing file in preview mode (no changes)."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        original_content = sample_chat_file.read_text()

        matches_applied, matches_found = processor.process_file(
            sample_chat_file,
            interactive=False,
            preview=True
        )

        assert matches_applied == 0  # Nothing applied in preview
        assert len(matches_found) > 0  # But matches were found

        # Verify file was NOT changed
        assert sample_chat_file.read_text() == original_content

    def test_process_file_no_matches(self, clean_chat_file, sanitizer):
        """Test processing file with no secrets."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        matches_applied, matches_found = processor.process_file(
            clean_chat_file,
            interactive=False,
            preview=False
        )

        assert matches_applied == 0
        assert len(matches_found) == 0

    def test_process_file_creates_backup(self, sample_chat_file, sanitizer):
        """Test that processing creates backup."""
        backup_manager = BackupManager(create_backups=True)
        processor = FileProcessor(sanitizer, backup_manager)

        processor.process_file(sample_chat_file, interactive=False)

        assert len(backup_manager.backups_created) == 1
        backup_file = backup_manager.backups_created[0]
        assert backup_file.exists()

    def test_get_context(self, sample_chat_file, sanitizer):
        """Test getting context lines around a match."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = sample_chat_file.read_text()

        # Get context around line 6 (where API key is)
        context = processor._get_context(content, line_number=6, context_lines=2)

        assert context is not None
        assert "sk-proj-abc123xyz789def456ghi789jkl012mno345" in context
        assert "→" in context  # Arrow marker for target line

    def test_interactive_review_approve_all(self, sample_chat_file, sanitizer):
        """Test interactive mode with 'approve all' response."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = sample_chat_file.read_text()
        matches = sanitizer.preview_sanitization(content)

        # Mock user input: approve all
        with patch('builtins.input', return_value='a'):
            approved = processor._interactive_review(sample_chat_file, content, matches)

        assert approved is not None
        assert len(approved) == len(matches)

    def test_interactive_review_skip_all(self, sample_chat_file, sanitizer):
        """Test interactive mode with 'skip all' response."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = sample_chat_file.read_text()
        matches = sanitizer.preview_sanitization(content)

        # Mock user input: skip all
        with patch('builtins.input', return_value='s'):
            approved = processor._interactive_review(sample_chat_file, content, matches)

        assert approved is not None
        assert len(approved) == 0

    def test_interactive_review_quit(self, sample_chat_file, sanitizer):
        """Test interactive mode with 'quit' response."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = sample_chat_file.read_text()
        matches = sanitizer.preview_sanitization(content)

        # Mock user input: quit
        with patch('builtins.input', return_value='q'):
            approved = processor._interactive_review(sample_chat_file, content, matches)

        assert approved is None  # Quit returns None

    def test_interactive_review_selective(self, sample_chat_file, sanitizer):
        """Test interactive mode with selective approval."""
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        content = sample_chat_file.read_text()
        matches = sanitizer.preview_sanitization(content)

        # Mock user input: yes, no, yes (alternating)
        responses = ['y', 'n', 'y', 's']  # Yes, no, yes, then skip rest
        with patch('builtins.input', side_effect=responses):
            approved = processor._interactive_review(sample_chat_file, content, matches)

        assert approved is not None
        assert len(approved) < len(matches)  # Some approved, some skipped


class TestMainFunction:
    """Test main script execution."""

    def test_main_preview_mode(self, temp_dir, sample_chat_file, capsys):
        """Test running main in preview mode."""
        args = [
            'sanitize-chats.py',
            str(sample_chat_file),
            '--preview'
        ]

        with patch('sys.argv', args):
            exit_code = sanitize_chats.main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Preview mode" in captured.out
        assert "no changes were made" in captured.out.lower()

    def test_main_batch_mode(self, temp_dir, sample_chat_file, capsys):
        """Test running main in batch mode."""
        args = [
            'sanitize-chats.py',
            str(sample_chat_file)
        ]

        with patch('sys.argv', args):
            exit_code = sanitize_chats.main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Sanitization complete" in captured.out or "Files modified" in captured.out

    def test_main_no_files_found(self, temp_dir, capsys):
        """Test main with no markdown files."""
        args = [
            'sanitize-chats.py',
            str(temp_dir / 'nonexistent/')
        ]

        with patch('sys.argv', args):
            exit_code = sanitize_chats.main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "No markdown files found" in captured.out

    def test_main_with_report(self, temp_dir, sample_chat_file):
        """Test generating a sanitization report."""
        report_file = temp_dir / "report.txt"

        args = [
            'sanitize-chats.py',
            str(sample_chat_file),
            '--report', str(report_file)
        ]

        with patch('sys.argv', args):
            exit_code = sanitize_chats.main()

        assert exit_code == 0
        assert report_file.exists()

        report_content = report_file.read_text()
        assert "SANITIZATION REPORT" in report_content
        assert "Total matches" in report_content

    def test_main_custom_level_and_style(self, temp_dir, sample_chat_file):
        """Test using custom level and style via CLI."""
        args = [
            'sanitize-chats.py',
            str(sample_chat_file),
            '--level', 'aggressive',
            '--style', 'labeled',
            '--no-backup'
        ]

        with patch('sys.argv', args):
            exit_code = sanitize_chats.main()

        assert exit_code == 0

        # Verify labeled style was used
        content = sample_chat_file.read_text()
        assert "[API_KEY]" in content or "sk-proj-abc123xyz789def456ghi789jkl012mno345" not in content


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows handles permissions differently")
    def test_write_file_permission_denied(self, temp_dir):
        """Test write_file with permission denied."""
        import stat

        test_file = temp_dir / "readonly.md"
        test_file.write_text("original")

        # Make directory read-only
        temp_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            sanitizer = Sanitizer(enabled=True)
            backup_manager = BackupManager()
            processor = FileProcessor(sanitizer, backup_manager)

            # Should fail gracefully
            result = processor.write_file(test_file, "new content")
            assert result is False
        finally:
            # Restore permissions
            temp_dir.chmod(stat.S_IRWXU)

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows handles permissions differently")
    def test_read_file_permission_denied(self, temp_dir, capsys):
        """Test read_file with permission denied."""
        import stat

        test_file = temp_dir / "noaccess.md"
        test_file.write_text("secret")

        # Make file unreadable
        test_file.chmod(0o000)

        try:
            sanitizer = Sanitizer(enabled=True)
            backup_manager = BackupManager()
            processor = FileProcessor(sanitizer, backup_manager)

            content = processor.read_file(test_file)
            assert content is None

            captured = capsys.readouterr()
            assert "Error reading" in captured.out
        finally:
            # Restore permissions for cleanup
            test_file.chmod(0o644)

    def test_process_file_with_unicode_content(self, temp_dir):
        """Test processing file with Unicode content."""
        content = """# Чат с эмодзи 🔒

**USER:**
Here's my key: sk-proj-abc123def456ghi789jkl012mno345pqr678stu901

Привет мир! 你好世界! مرحبا بالعالم!
"""

        file_path = temp_dir / "unicode.md"
        file_path.write_text(content, encoding='utf-8')

        sanitizer = Sanitizer(enabled=True, level='balanced', style='partial')
        backup_manager = BackupManager(create_backups=False)
        processor = FileProcessor(sanitizer, backup_manager)

        matches_applied, matches_found = processor.process_file(file_path)

        assert matches_applied > 0
        # Verify Unicode characters preserved
        result_content = file_path.read_text(encoding='utf-8')
        assert "Привет мир" in result_content
        assert "你好世界" in result_content

    def test_find_files_with_symlinks(self, temp_dir):
        """Test that symlinks are skipped."""
        real_file = temp_dir / "real.md"
        real_file.write_text("# Real file")

        symlink = temp_dir / "link.md"
        try:
            symlink.symlink_to(real_file)
        except OSError:
            # Skip test on systems that don't support symlinks
            pytest.skip("Symlinks not supported")

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        # Should only find real file, not symlink
        files = processor.find_markdown_files([temp_dir])

        # On systems with symlink support, should find 1 file
        assert len(files) >= 1
        assert real_file in files
        # Symlink should be skipped
        assert all(not f.is_symlink() for f in files)

    def test_write_file_disk_full_simulation(self, temp_dir, capsys):
        """Test write_file when disk is full (simulated)."""
        test_file = temp_dir / "test.md"

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        # Mock tempfile.mkstemp to raise OSError (disk full)
        import tempfile
        original_mkstemp = tempfile.mkstemp

        def mock_mkstemp(*args, **kwargs):
            raise OSError(28, "No space left on device")

        with patch('tempfile.mkstemp', side_effect=mock_mkstemp):
            result = processor.write_file(test_file, "content")

        assert result is False
        captured = capsys.readouterr()
        assert "Error writing" in captured.out

    def test_process_empty_file(self, temp_dir):
        """Test processing an empty markdown file."""
        empty_file = temp_dir / "empty.md"
        empty_file.write_text("")

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager()
        processor = FileProcessor(sanitizer, backup_manager)

        matches_applied, matches_found = processor.process_file(empty_file)

        assert matches_applied == 0
        assert len(matches_found) == 0

    def test_process_very_large_file(self, temp_dir):
        """Test processing a large file with many secrets."""
        # Create file with 100 API keys
        lines = ["# Large Chat\n"]
        for i in range(100):
            key = f"sk-proj-{'a' * 20}{i:04d}{'b' * 20}"
            lines.append(f"\nAPI Key {i}: {key}\n")

        large_file = temp_dir / "large.md"
        large_file.write_text("".join(lines))

        sanitizer = Sanitizer(enabled=True)
        backup_manager = BackupManager(create_backups=False)
        processor = FileProcessor(sanitizer, backup_manager)

        matches_applied, matches_found = processor.process_file(large_file)

        assert matches_applied == 100
        assert len(matches_found) == 100


class TestArgumentParsing:
    """Test command-line argument parsing."""

    def test_parse_basic_arguments(self):
        """Test parsing basic arguments."""
        args = ['sanitize-chats.py', 'file.md']

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert len(parsed.paths) == 1
        assert parsed.paths[0] == Path('file.md')
        assert not parsed.interactive
        assert not parsed.preview

    def test_parse_interactive_flag(self):
        """Test parsing interactive flag."""
        args = ['sanitize-chats.py', 'file.md', '--interactive']

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert parsed.interactive

    def test_parse_preview_flag(self):
        """Test parsing preview flag."""
        args = ['sanitize-chats.py', 'file.md', '-p']

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert parsed.preview

    def test_parse_multiple_paths(self):
        """Test parsing multiple input paths."""
        args = ['sanitize-chats.py', 'file1.md', 'file2.md', 'dir/']

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert len(parsed.paths) == 3

    def test_parse_level_and_style(self):
        """Test parsing level and style options."""
        args = [
            'sanitize-chats.py',
            'file.md',
            '--level', 'aggressive',
            '--style', 'hash'
        ]

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert parsed.level == 'aggressive'
        assert parsed.style == 'hash'

    def test_parse_report_option(self):
        """Test parsing report file option."""
        args = ['sanitize-chats.py', 'file.md', '--report', 'report.txt']

        with patch('sys.argv', args):
            parsed = sanitize_chats.parse_arguments()

        assert parsed.report == Path('report.txt')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

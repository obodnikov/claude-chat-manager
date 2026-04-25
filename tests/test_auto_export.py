"""Tests for auto-export.py learn mode.

Covers:
- Source-qualified mapping keys (cross-source collision prevention)
- Custom target path traversal rejection
- Update mode preserving confirmed mappings
- Helper functions
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on path so auto-export imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import ChatSource, ProjectInfo
from src.project_matcher import MappingConfig, ProjectMapping

# Import functions under test from auto-export.py
# The script uses sys.path manipulation, so we import after path setup
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "auto_export",
    str(Path(__file__).parent.parent / "auto-export.py"),
)
auto_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auto_export)

_mapping_key = auto_export._mapping_key
_validate_custom_target = auto_export._validate_custom_target
_canonicalize_custom_target = auto_export._canonicalize_custom_target
_source_label = auto_export._source_label
_format_target_path = auto_export._format_target_path
learn_mode = auto_export.learn_mode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_project_info(
    name: str,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP,
    workspace_path: Optional[str] = None,
) -> ProjectInfo:
    """Create a minimal ProjectInfo for testing."""
    return ProjectInfo(
        name=name,
        path=Path(f"/fake/{name}"),
        file_count=1,
        total_messages=5,
        last_modified="2026-04-23",
        source=source,
        workspace_path=workspace_path,
    )


@pytest.fixture
def root_dir(tmp_path: Path) -> Path:
    """Create a root directory with a few project folders."""
    for name in ("project-alpha", "project-beta", "shared-project"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "docs" / "chats").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return a temporary config file path."""
    return tmp_path / "config" / "project-mapping.json"


# ---------------------------------------------------------------------------
# Test _mapping_key
# ---------------------------------------------------------------------------

class TestMappingKey:
    """Source-qualified key generation."""

    def test_claude_key(self) -> None:
        key = _mapping_key("my-project", ChatSource.CLAUDE_DESKTOP)
        assert key == "claude:my-project"

    def test_kiro_key(self) -> None:
        key = _mapping_key("my-project", ChatSource.KIRO_IDE)
        assert key == "kiro:my-project"

    def test_codex_key(self) -> None:
        key = _mapping_key("my-project", ChatSource.CODEX)
        assert key == "codex:my-project"

    def test_same_name_different_source_produces_different_keys(self) -> None:
        k1 = _mapping_key("shared-project", ChatSource.CLAUDE_DESKTOP)
        k2 = _mapping_key("shared-project", ChatSource.KIRO_IDE)
        k3 = _mapping_key("shared-project", ChatSource.CODEX)
        assert len({k1, k2, k3}) == 3


# ---------------------------------------------------------------------------
# Test _validate_custom_target
# ---------------------------------------------------------------------------

class TestValidateCustomTarget:
    """Path traversal rejection for custom targets."""

    def test_valid_subfolder(self, root_dir: Path) -> None:
        assert _validate_custom_target("project-alpha", root_dir) is None

    def test_valid_nested_subfolder(self, root_dir: Path) -> None:
        assert _validate_custom_target("project-alpha/sub", root_dir) is None

    def test_rejects_dotdot_traversal(self, root_dir: Path) -> None:
        error = _validate_custom_target("../other-repo", root_dir)
        assert error is not None
        assert "outside root" in error

    def test_rejects_nested_dotdot(self, root_dir: Path) -> None:
        error = _validate_custom_target("project-alpha/../../escape", root_dir)
        assert error is not None
        assert "outside root" in error

    def test_rejects_absolute_path(self, root_dir: Path) -> None:
        error = _validate_custom_target("/tmp/evil", root_dir)
        assert error is not None
        assert "outside root" in error

    def test_accepts_nonexistent_subfolder(self, root_dir: Path) -> None:
        # Folder doesn't exist yet but is still under root
        assert _validate_custom_target("new-project", root_dir) is None

    def test_rejects_empty_string(self, root_dir: Path) -> None:
        error = _validate_custom_target("", root_dir)
        assert error is not None
        assert "empty" in error.lower() or "'.'" in error

    def test_rejects_dot(self, root_dir: Path) -> None:
        error = _validate_custom_target(".", root_dir)
        assert error is not None

    def test_rejects_slash(self, root_dir: Path) -> None:
        error = _validate_custom_target("/", root_dir)
        assert error is not None

    def test_rejects_root_equivalent(self, root_dir: Path) -> None:
        # 'project-alpha/..' resolves to root itself
        error = _validate_custom_target("project-alpha/..", root_dir)
        assert error is not None


# ---------------------------------------------------------------------------
# Test cross-source collision prevention in learn_mode
# ---------------------------------------------------------------------------

class TestCrossSourceCollision:
    """Same project name from different sources must not overwrite mappings."""

    def test_same_name_different_sources_both_stored(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Two sources with the same project name should produce two
        separate config entries with source-qualified keys."""
        projects = [
            _make_project_info("shared-project", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("shared-project", ChatSource.KIRO_IDE),
        ]

        # Simulate user confirming both
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['y', 'y']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        # Load saved config and verify both keys exist
        cfg = MappingConfig(config_path)
        cfg.load()

        claude_key = _mapping_key("shared-project", ChatSource.CLAUDE_DESKTOP)
        kiro_key = _mapping_key("shared-project", ChatSource.KIRO_IDE)

        claude_mapping = cfg.get_mapping(claude_key)
        kiro_mapping = cfg.get_mapping(kiro_key)

        assert claude_mapping is not None, f"Missing config entry for {claude_key}"
        assert kiro_mapping is not None, f"Missing config entry for {kiro_key}"
        assert claude_mapping.action == 'export'
        assert kiro_mapping.action == 'export'

    def test_skip_one_source_keeps_other(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Skipping one source should not affect the other source's mapping."""
        projects = [
            _make_project_info("shared-project", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("shared-project", ChatSource.KIRO_IDE),
        ]

        # Confirm first, skip second
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['y', 'skip']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        claude_key = _mapping_key("shared-project", ChatSource.CLAUDE_DESKTOP)
        kiro_key = _mapping_key("shared-project", ChatSource.KIRO_IDE)

        assert cfg.get_mapping(claude_key).action == 'export'
        assert cfg.get_mapping(kiro_key).action == 'skip'


# ---------------------------------------------------------------------------
# Test custom path traversal rejection in learn_mode
# ---------------------------------------------------------------------------

class TestCustomPathTraversal:
    """Custom folder input must be confined to root directory."""

    def test_dotdot_custom_target_rejected(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Entering '../escape' as custom target should be rejected."""
        projects = [
            _make_project_info("unknown-project", ChatSource.CLAUDE_DESKTOP),
        ]

        # No auto-match → user enters traversal path
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['../escape']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        key = _mapping_key("unknown-project", ChatSource.CLAUDE_DESKTOP)
        # Should NOT have an export mapping for the traversal path
        mapping = cfg.get_mapping(key)
        # Either no mapping or not an export to the traversal target
        if mapping is not None:
            assert mapping.target != "../escape"

    def test_valid_custom_target_accepted(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Entering a valid subfolder name should be accepted."""
        projects = [
            _make_project_info("unknown-project", ChatSource.CLAUDE_DESKTOP),
        ]

        # No auto-match → user enters valid folder name
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['project-alpha']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        key = _mapping_key("unknown-project", ChatSource.CLAUDE_DESKTOP)
        mapping = cfg.get_mapping(key)
        assert mapping is not None
        assert mapping.action == 'export'
        assert mapping.target == 'project-alpha'


# ---------------------------------------------------------------------------
# Test --learn --update mode
# ---------------------------------------------------------------------------

class TestUpdateMode:
    """Update mode should preserve confirmed mappings and add new ones."""

    def test_update_preserves_confirmed_adds_new(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """Existing confirmed mappings survive; new projects get prompted."""
        # Pre-populate config with a confirmed mapping
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))

        existing_key = _mapping_key("project-alpha", ChatSource.CLAUDE_DESKTOP)
        cfg.set_mapping(existing_key, ProjectMapping(
            source_name="project-alpha",
            target="project-alpha",
            docs_chats_path="docs/chats",
            action='export',
            confirmed=True,
            match_method='basename',
            source_type=ChatSource.CLAUDE_DESKTOP,
        ))
        cfg.save()

        # Discovery returns the existing project + a new one
        projects = [
            _make_project_info("project-alpha", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("project-beta", ChatSource.KIRO_IDE),
        ]

        # Only the new project should be prompted (confirm it)
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['y']):
            result = learn_mode(root_dir, config_path, update=True)

        assert result == 0

        cfg2 = MappingConfig(config_path)
        cfg2.load()

        # Existing mapping preserved
        alpha = cfg2.get_mapping(existing_key)
        assert alpha is not None
        assert alpha.confirmed is True
        assert alpha.target == "project-alpha"

        # New mapping added
        beta_key = _mapping_key("project-beta", ChatSource.KIRO_IDE)
        beta = cfg2.get_mapping(beta_key)
        assert beta is not None
        assert beta.confirmed is True

    def test_update_does_not_reprompt_confirmed_skip(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """A confirmed skip mapping should not be re-prompted in update mode."""
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))

        skip_key = _mapping_key("old-experiment", ChatSource.CODEX)
        cfg.set_mapping(skip_key, ProjectMapping(
            source_name="old-experiment",
            action='skip',
            confirmed=True,
            match_method='user_skip',
            source_type=ChatSource.CODEX,
        ))
        cfg.save()

        projects = [
            _make_project_info("old-experiment", ChatSource.CODEX),
        ]

        # No input() calls should happen — the project is already confirmed
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=RuntimeError("should not prompt")):
            result = learn_mode(root_dir, config_path, update=True)

        assert result == 0


# ---------------------------------------------------------------------------
# Test helper functions
# ---------------------------------------------------------------------------

class TestSourceLabel:
    """Display labels for chat sources."""

    def test_claude_label(self) -> None:
        assert _source_label(ChatSource.CLAUDE_DESKTOP) == "Claude"

    def test_kiro_label(self) -> None:
        assert _source_label(ChatSource.KIRO_IDE) == "Kiro"

    def test_codex_label(self) -> None:
        assert _source_label(ChatSource.CODEX) == "Codex"


class TestFormatTargetPath:
    """Target path formatting for display."""

    def test_no_target_shows_question_marks(self) -> None:
        mapping = ProjectMapping(source_name="x", target=None)
        result = _format_target_path(Path("/root"), mapping)
        assert "???" in result

    def test_with_target_includes_folder(self, tmp_path: Path) -> None:
        mapping = ProjectMapping(
            source_name="x",
            target="my-project",
            docs_chats_path="docs/chats",
        )
        result = _format_target_path(tmp_path, mapping)
        assert "my-project" in result
        assert "docs/chats" in result


# ---------------------------------------------------------------------------
# Test _canonicalize_custom_target
# ---------------------------------------------------------------------------

class TestCanonicalizeCustomTarget:
    """Equivalent paths should normalize to the same stored value."""

    def test_plain_name(self, root_dir: Path) -> None:
        assert _canonicalize_custom_target("project-alpha", root_dir) == "project-alpha"

    def test_dot_slash_prefix(self, root_dir: Path) -> None:
        assert _canonicalize_custom_target("./project-alpha", root_dir) == "project-alpha"

    def test_redundant_traversal(self, root_dir: Path) -> None:
        result = _canonicalize_custom_target(
            "project-alpha/../project-alpha", root_dir
        )
        assert result == "project-alpha"

    def test_nested_path(self, root_dir: Path) -> None:
        result = _canonicalize_custom_target("project-alpha/sub", root_dir)
        assert result == "project-alpha/sub"


# ---------------------------------------------------------------------------
# Test empty custom target rejection in learn_mode
# ---------------------------------------------------------------------------

class TestEmptyCustomTarget:
    """Empty or whitespace-only custom input should not create export mappings."""

    def test_slash_only_input_skipped(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """User entering '/' (which strips to empty) should be skipped."""
        projects = [
            _make_project_info("unknown-project", ChatSource.CLAUDE_DESKTOP),
        ]

        # No auto-match → user enters '/'
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['/']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        key = _mapping_key("unknown-project", ChatSource.CLAUDE_DESKTOP)
        mapping = cfg.get_mapping(key)
        # Should not have an export mapping with empty target
        if mapping is not None:
            assert mapping.action != 'export' or mapping.target not in (None, '', '.')

    def test_dot_input_skipped(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """User entering '.' should be skipped."""
        projects = [
            _make_project_info("unknown-project", ChatSource.CLAUDE_DESKTOP),
        ]

        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['.']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        key = _mapping_key("unknown-project", ChatSource.CLAUDE_DESKTOP)
        mapping = cfg.get_mapping(key)
        if mapping is not None:
            assert mapping.action != 'export' or mapping.target != '.'


# ---------------------------------------------------------------------------
# Test path canonicalization in learn_mode
# ---------------------------------------------------------------------------

class TestCustomTargetCanonicalization:
    """'./proj' and 'proj' should store the same canonical target."""

    def test_dot_slash_and_plain_store_same_target(
        self, root_dir: Path, config_path: Path
    ) -> None:
        projects = [
            _make_project_info("proj-a", ChatSource.CLAUDE_DESKTOP),
            _make_project_info("proj-b", ChatSource.KIRO_IDE),
        ]

        # First enters './project-alpha', second enters 'project-alpha'
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['./project-alpha', 'project-alpha']):
            result = learn_mode(root_dir, config_path)

        assert result == 0

        cfg = MappingConfig(config_path)
        cfg.load()

        key_a = _mapping_key("proj-a", ChatSource.CLAUDE_DESKTOP)
        key_b = _mapping_key("proj-b", ChatSource.KIRO_IDE)

        mapping_a = cfg.get_mapping(key_a)
        mapping_b = cfg.get_mapping(key_b)

        assert mapping_a is not None
        assert mapping_b is not None
        # Both should have the same canonical target
        assert mapping_a.target == mapping_b.target == "project-alpha"


# ---------------------------------------------------------------------------
# Test config precedence (CLI --config > AUTO_EXPORT_CONFIG > default)
# ---------------------------------------------------------------------------

class TestConfigPrecedence:
    """Config path resolution follows CLI > env var > default."""

    def test_env_var_used_when_no_cli_config(
        self, root_dir: Path, tmp_path: Path
    ) -> None:
        """AUTO_EXPORT_CONFIG env var should be used when --config is not passed."""
        env_config = tmp_path / "env-config.json"

        # Simulate: no --config flag, env var set
        test_argv = ['auto-export.py', '--root', str(root_dir), '--learn']
        with patch('sys.argv', test_argv), \
             patch.dict(os.environ, {'AUTO_EXPORT_CONFIG': str(env_config)}), \
             patch.object(auto_export, 'learn_mode', return_value=0) as mock_learn:
            auto_export.main()

        # learn_mode should have been called with the env var path
        call_kwargs = mock_learn.call_args
        actual_config = call_kwargs.kwargs.get('config_path') or call_kwargs[1].get('config_path')
        if actual_config is None:
            actual_config = call_kwargs[0][1]  # positional arg
        assert Path(actual_config) == env_config.resolve()

    def test_cli_config_overrides_env_var(
        self, root_dir: Path, tmp_path: Path
    ) -> None:
        """Explicit --config should take priority over AUTO_EXPORT_CONFIG."""
        cli_config = tmp_path / "cli-config.json"
        env_config = tmp_path / "env-config.json"

        test_argv = [
            'auto-export.py', '--root', str(root_dir),
            '--learn', '--config', str(cli_config),
        ]
        with patch('sys.argv', test_argv), \
             patch.dict(os.environ, {'AUTO_EXPORT_CONFIG': str(env_config)}), \
             patch.object(auto_export, 'learn_mode', return_value=0) as mock_learn:
            auto_export.main()

        call_kwargs = mock_learn.call_args
        actual_config = call_kwargs.kwargs.get('config_path') or call_kwargs[1].get('config_path')
        if actual_config is None:
            actual_config = call_kwargs[0][1]
        assert Path(actual_config) == cli_config.resolve()
        assert Path(actual_config) != env_config.resolve()


# ---------------------------------------------------------------------------
# Test --config= form with env var (CLI must win)
# ---------------------------------------------------------------------------

class TestConfigEqualsForm:
    """--config=/path form must override AUTO_EXPORT_CONFIG."""

    def test_config_equals_form_overrides_env_var(
        self, root_dir: Path, tmp_path: Path
    ) -> None:
        """--config=/path/to/file should beat AUTO_EXPORT_CONFIG."""
        cli_config = tmp_path / "cli-config.json"
        env_config = tmp_path / "env-config.json"

        # Use the --config=VALUE form (no space)
        test_argv = [
            'auto-export.py', '--root', str(root_dir),
            '--learn', f'--config={cli_config}',
        ]
        with patch('sys.argv', test_argv), \
             patch.dict(os.environ, {'AUTO_EXPORT_CONFIG': str(env_config)}), \
             patch.object(auto_export, 'learn_mode', return_value=0) as mock_learn:
            auto_export.main()

        call_kwargs = mock_learn.call_args
        actual_config = call_kwargs.kwargs.get('config_path') or call_kwargs[1].get('config_path')
        if actual_config is None:
            actual_config = call_kwargs[0][1]
        assert Path(actual_config) == cli_config.resolve()
        assert Path(actual_config) != env_config.resolve()


# ---------------------------------------------------------------------------
# Test stale mapping replacement on invalid custom input
# ---------------------------------------------------------------------------

class TestStaleMappingReplacement:
    """Invalid custom input must overwrite stale mappings, not leave them."""

    def test_invalid_custom_replaces_stale_export_mapping(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """If a prior export mapping exists and user enters '../escape',
        the stale export mapping must be replaced with a skip."""
        # Pre-populate config with an export mapping
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))

        key = _mapping_key("my-project", ChatSource.CLAUDE_DESKTOP)
        cfg.set_mapping(key, ProjectMapping(
            source_name="my-project",
            target="project-alpha",
            docs_chats_path="docs/chats",
            action='export',
            confirmed=True,
            match_method='basename',
            source_type=ChatSource.CLAUDE_DESKTOP,
        ))
        cfg.save()

        projects = [
            _make_project_info("my-project", ChatSource.CLAUDE_DESKTOP),
        ]

        # Re-learn: auto-match shows project-alpha, user enters invalid '../escape'
        # The auto-match will show project-alpha (basename match), user overrides
        # with a traversal path → should replace the stale export with skip
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['../escape']):
            result = learn_mode(root_dir, config_path, update=False)

        assert result == 0

        cfg2 = MappingConfig(config_path)
        cfg2.load()

        mapping = cfg2.get_mapping(key)
        assert mapping is not None
        # Must NOT still be an export to project-alpha
        assert mapping.action == 'skip', (
            f"Stale export mapping survived: action={mapping.action}, "
            f"target={mapping.target}"
        )

    def test_empty_custom_replaces_stale_export_mapping(
        self, root_dir: Path, config_path: Path
    ) -> None:
        """If a prior export mapping exists and user enters '.',
        the stale export mapping must be replaced with a skip."""
        cfg = MappingConfig(config_path)
        cfg.load()
        cfg.set_root_directory(str(root_dir))

        key = _mapping_key("my-project", ChatSource.KIRO_IDE)
        cfg.set_mapping(key, ProjectMapping(
            source_name="my-project",
            target="project-beta",
            docs_chats_path="docs/chats",
            action='export',
            confirmed=True,
            match_method='workspace_path',
            source_type=ChatSource.KIRO_IDE,
        ))
        cfg.save()

        projects = [
            _make_project_info("my-project", ChatSource.KIRO_IDE),
        ]

        # Re-learn: user enters '.' → empty target → should replace with skip
        with patch.object(auto_export, 'list_all_projects', return_value=projects), \
             patch('builtins.input', side_effect=['.']):
            result = learn_mode(root_dir, config_path, update=False)

        assert result == 0

        cfg2 = MappingConfig(config_path)
        cfg2.load()

        mapping = cfg2.get_mapping(key)
        assert mapping is not None
        assert mapping.action == 'skip', (
            f"Stale export mapping survived: action={mapping.action}, "
            f"target={mapping.target}"
        )

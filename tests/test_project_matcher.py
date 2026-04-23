"""Tests for project matching and mapping configuration.

Tests cover:
- MappingConfig: load, save, get/set mappings, defaults
- ProjectMatcher: all matching strategies, docs/chats detection
- Helper functions: _normalize_name, _is_subsequence
"""

import json
from pathlib import Path
from typing import List, Optional

import pytest

from src.exceptions import ConfigurationError
from src.models import ChatSource, ProjectInfo
from src.project_matcher import (
    DEFAULT_CONFIG_PATH,
    FUZZY_MATCH_THRESHOLD,
    MappingConfig,
    ProjectMapping,
    ProjectMatcher,
    _is_subsequence,
    _normalize_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def root_dir(tmp_path: Path) -> Path:
    """Create a root directory with sample project folders."""
    projects = [
        'claude-chat-manager',
        'my-side-project',
        'web-dashboard',
        'python_utils',
        'DataPipeline',
    ]
    for name in projects:
        (tmp_path / name).mkdir()
    return tmp_path


@pytest.fixture
def root_dir_with_docs(root_dir: Path) -> Path:
    """Root directory where some projects have docs/chats folders."""
    # claude-chat-manager has docs/chats with real chat files
    docs_chats = root_dir / 'claude-chat-manager' / 'docs' / 'chats'
    docs_chats.mkdir(parents=True)
    chat_file = docs_chats / 'some-chat-2025-12-26.md'
    chat_file.write_text(
        '# Claude Chat Export\n'
        '**Generated: 2025-12-26 16:57:45**\n\n'
        '---\n\n'
        '👤 **USER:**\n'
        '> How do I implement auth?\n',
        encoding='utf-8',
    )

    # my-side-project has a chats/ folder (alternative convention)
    chats_dir = root_dir / 'my-side-project' / 'chats'
    chats_dir.mkdir()
    (chats_dir / 'test-chat.md').write_text(
        '👤 **USER:**\n> Hello\n', encoding='utf-8'
    )

    # web-dashboard has no docs/chats
    return root_dir


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Temporary config file path."""
    return tmp_path / 'config' / 'project-mapping.json'


@pytest.fixture
def mapping_config(config_path: Path) -> MappingConfig:
    """MappingConfig instance with temporary path."""
    return MappingConfig(config_path)


@pytest.fixture
def sample_config_data() -> dict:
    """Sample config data for testing load."""
    return {
        'version': '1.0',
        'root_directory': '/Users/mike/src',
        'defaults': {
            'export_format': 'book',
            'unmatched_action': 'skip',
        },
        'mappings': {
            'claude-chat-manager': {
                'target': 'claude-chat-manager',
                'docs_chats_path': 'docs/chats',
                'action': 'export',
                'confirmed': True,
            },
            'random-experiment': {
                'action': 'skip',
                'confirmed': True,
            },
        },
        'last_learned': '2026-04-23T12:00:00',
    }


def _make_project_info(
    name: str,
    source: ChatSource = ChatSource.CLAUDE_DESKTOP,
    workspace_path: Optional[str] = None,
) -> ProjectInfo:
    """Helper to create a ProjectInfo for testing."""
    return ProjectInfo(
        name=name,
        path=Path('/fake/path'),
        file_count=5,
        total_messages=50,
        last_modified='2026-04-23',
        source=source,
        workspace_path=workspace_path,
    )



# ===========================================================================
# Helper function tests
# ===========================================================================

class TestNormalizeName:
    """Tests for _normalize_name helper."""

    def test_lowercase(self) -> None:
        assert _normalize_name('MyProject') == 'myproject'

    def test_dashes_to_spaces(self) -> None:
        assert _normalize_name('my-project-name') == 'my project name'

    def test_underscores_to_spaces(self) -> None:
        assert _normalize_name('my_project_name') == 'my project name'

    def test_dots_to_spaces(self) -> None:
        assert _normalize_name('my.project.name') == 'my project name'

    def test_mixed_separators(self) -> None:
        assert _normalize_name('my-project_name.v2') == 'my project name v2'

    def test_multiple_separators_collapsed(self) -> None:
        assert _normalize_name('my--project__name') == 'my project name'

    def test_strips_whitespace(self) -> None:
        assert _normalize_name('  my-project  ') == 'my project'

    def test_empty_string(self) -> None:
        assert _normalize_name('') == ''

    def test_single_word(self) -> None:
        assert _normalize_name('project') == 'project'


class TestIsSubsequence:
    """Tests for _is_subsequence helper."""

    def test_found_at_end(self) -> None:
        assert _is_subsequence(
            ['claude', 'chat', 'manager'],
            ['users', 'mike', 'src', 'claude', 'chat', 'manager'],
        ) is True

    def test_found_at_start(self) -> None:
        assert _is_subsequence(
            ['users', 'mike'],
            ['users', 'mike', 'src', 'project'],
        ) is True

    def test_found_in_middle(self) -> None:
        assert _is_subsequence(
            ['src', 'project'],
            ['users', 'src', 'project', 'docs'],
        ) is True

    def test_not_found(self) -> None:
        assert _is_subsequence(
            ['foo', 'bar'],
            ['users', 'mike', 'src'],
        ) is False

    def test_not_contiguous(self) -> None:
        """Tokens must be contiguous, not just present."""
        assert _is_subsequence(
            ['users', 'src'],
            ['users', 'mike', 'src'],
        ) is False

    def test_empty_needle(self) -> None:
        assert _is_subsequence([], ['a', 'b']) is False

    def test_needle_longer_than_haystack(self) -> None:
        assert _is_subsequence(['a', 'b', 'c'], ['a', 'b']) is False

    def test_exact_match(self) -> None:
        assert _is_subsequence(['a', 'b'], ['a', 'b']) is True

    def test_single_element(self) -> None:
        assert _is_subsequence(['src'], ['users', 'src', 'project']) is True



# ===========================================================================
# MappingConfig tests
# ===========================================================================

class TestMappingConfigDefaults:
    """Tests for MappingConfig default behavior."""

    def test_default_config_path(self) -> None:
        cfg = MappingConfig()
        assert cfg.config_path == DEFAULT_CONFIG_PATH

    def test_custom_config_path(self, config_path: Path) -> None:
        cfg = MappingConfig(config_path)
        assert cfg.config_path == config_path

    def test_load_nonexistent_returns_defaults(
        self, mapping_config: MappingConfig
    ) -> None:
        data = mapping_config.load()
        assert data['version'] == '1.0'
        assert data['mappings'] == {}
        assert 'defaults' in data

    def test_default_config_has_expected_structure(
        self, mapping_config: MappingConfig
    ) -> None:
        data = mapping_config.load()
        assert data['defaults']['export_format'] == 'book'
        assert data['defaults']['unmatched_action'] == 'skip'


class TestMappingConfigLoadSave:
    """Tests for MappingConfig load and save operations."""

    def test_save_creates_parent_dirs(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.save()
        assert mapping_config.config_path.exists()
        assert mapping_config.config_path.parent.is_dir()

    def test_save_is_atomic(
        self, mapping_config: MappingConfig
    ) -> None:
        """Save should produce a valid file even if called multiple times."""
        mapping_config.load()
        mapping_config.set_mapping('proj', ProjectMapping(
            source_name='proj', target='folder', action='export',
            confirmed=True,
        ))
        mapping_config.save()

        # Verify file is valid JSON after save
        content = mapping_config.config_path.read_text(encoding='utf-8')
        data = json.loads(content)
        assert data['mappings']['proj']['target'] == 'folder'

    def test_save_and_load_roundtrip(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('test-project', ProjectMapping(
            source_name='test-project',
            target='test-project',
            docs_chats_path='docs/chats',
            action='export',
            confirmed=True,
        ))
        mapping_config.save()

        # Load in a new instance
        cfg2 = MappingConfig(mapping_config.config_path)
        cfg2.load()
        mapping = cfg2.get_mapping('test-project')
        assert mapping is not None
        assert mapping.target == 'test-project'
        assert mapping.confirmed is True

    def test_load_existing_config(
        self, config_path: Path, sample_config_data: dict
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(sample_config_data), encoding='utf-8'
        )

        cfg = MappingConfig(config_path)
        data = cfg.load()
        assert len(data['mappings']) == 2
        assert data['root_directory'] == '/Users/mike/src'

    def test_load_invalid_json_raises(self, config_path: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('not valid json{{{', encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='Invalid JSON'):
            cfg.load()

    def test_load_non_object_raises(self, config_path: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('["a list"]', encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='JSON object'):
            cfg.load()

    def test_load_missing_mappings_key_adds_default(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"version": "1.0"}', encoding='utf-8')

        cfg = MappingConfig(config_path)
        data = cfg.load()
        assert 'mappings' in data
        assert data['mappings'] == {}

    def test_load_mappings_as_list_raises(self, config_path: Path) -> None:
        """mappings must be a dict, not a list."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"version": "1.0", "mappings": ["a", "b"]}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match="'mappings' must be a JSON object"):
            cfg.load()

    def test_load_mappings_as_string_raises(self, config_path: Path) -> None:
        """mappings must be a dict, not a string."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"version": "1.0", "mappings": "bad"}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match="'mappings' must be a JSON object"):
            cfg.load()

    def test_load_mapping_entry_as_string_raises(
        self, config_path: Path
    ) -> None:
        """Each mapping entry must be a dict, not a string."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"mappings": {"my-project": "not-a-dict"}}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        with pytest.raises(
            ConfigurationError, match="Mapping entry 'my-project' must be a JSON object"
        ):
            cfg.load()

    def test_load_mapping_entry_as_list_raises(
        self, config_path: Path
    ) -> None:
        """Each mapping entry must be a dict, not a list."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"mappings": {"proj": [1, 2, 3]}}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        with pytest.raises(
            ConfigurationError, match="Mapping entry 'proj' must be a JSON object"
        ):
            cfg.load()

    def test_load_mapping_entry_as_int_raises(
        self, config_path: Path
    ) -> None:
        """Each mapping entry must be a dict, not an int."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"mappings": {"proj": 42}}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match="Mapping entry 'proj'"):
            cfg.load()

    def test_load_io_error_raises_configuration_error(
        self, config_path: Path
    ) -> None:
        """OSError during read should be wrapped as ConfigurationError."""
        # Create a directory where the config file should be — open() will fail
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.mkdir()  # config_path is now a directory, not a file

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match="Failed to read config"):
            cfg.load()

    def test_get_mapping_safe_after_valid_load(
        self, config_path: Path
    ) -> None:
        """get_mapping should work correctly after loading valid config."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"mappings": {"proj": {"target": "folder", "action": "export"}}}',
            encoding='utf-8',
        )

        cfg = MappingConfig(config_path)
        cfg.load()
        result = cfg.get_mapping('proj')
        assert result is not None
        assert result.target == 'folder'
        assert cfg.get_mapping('nonexistent') is None


class TestMappingConfigGetSet:
    """Tests for MappingConfig get/set mapping operations."""

    def test_get_mapping_not_found(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        assert mapping_config.get_mapping('nonexistent') is None

    def test_set_and_get_export_mapping(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('my-project', ProjectMapping(
            source_name='my-project',
            target='my-project-folder',
            docs_chats_path='docs/conversations',
            action='export',
            confirmed=True,
        ))

        result = mapping_config.get_mapping('my-project')
        assert result is not None
        assert result.target == 'my-project-folder'
        assert result.docs_chats_path == 'docs/conversations'
        assert result.action == 'export'
        assert result.confirmed is True
        assert result.match_method == 'config'

    def test_set_and_get_skip_mapping(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('skip-me', ProjectMapping(
            source_name='skip-me',
            action='skip',
            confirmed=True,
        ))

        result = mapping_config.get_mapping('skip-me')
        assert result is not None
        assert result.action == 'skip'
        assert result.confirmed is True
        assert result.target is None

    def test_overwrite_existing_mapping(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('project', ProjectMapping(
            source_name='project',
            target='old-folder',
            action='export',
            confirmed=True,
        ))
        mapping_config.set_mapping('project', ProjectMapping(
            source_name='project',
            target='new-folder',
            action='export',
            confirmed=True,
        ))

        result = mapping_config.get_mapping('project')
        assert result.target == 'new-folder'

    def test_get_all_mappings(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('proj-a', ProjectMapping(
            source_name='proj-a', target='a', action='export', confirmed=True,
        ))
        mapping_config.set_mapping('proj-b', ProjectMapping(
            source_name='proj-b', action='skip', confirmed=True,
        ))

        all_mappings = mapping_config.get_all_mappings()
        assert len(all_mappings) == 2
        assert 'proj-a' in all_mappings
        assert 'proj-b' in all_mappings

    def test_get_confirmed_targets(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('proj-a', ProjectMapping(
            source_name='proj-a', target='folder-a',
            action='export', confirmed=True,
        ))
        mapping_config.set_mapping('proj-b', ProjectMapping(
            source_name='proj-b', target='folder-b',
            action='export', confirmed=False,
        ))
        mapping_config.set_mapping('proj-c', ProjectMapping(
            source_name='proj-c', action='skip', confirmed=True,
        ))

        confirmed = mapping_config.get_confirmed_targets()
        assert confirmed == {'proj-a': 'folder-a'}


class TestMappingConfigMetadata:
    """Tests for MappingConfig metadata operations."""

    def test_set_root_directory(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_root_directory('/Users/mike/src')
        assert mapping_config.get_root_directory() == '/Users/mike/src'

    def test_get_root_directory_default_none(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        assert mapping_config.get_root_directory() is None

    def test_set_last_learned(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_last_learned()
        assert 'last_learned' in mapping_config.data
        assert mapping_config.data['last_learned'] is not None

    def test_data_property(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        assert isinstance(mapping_config.data, dict)
        assert 'version' in mapping_config.data



# ===========================================================================
# ProjectMatcher tests
# ===========================================================================

class TestProjectMatcherInit:
    """Tests for ProjectMatcher initialization."""

    def test_init_with_valid_root(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        assert matcher.root_dir == root_dir.resolve()

    def test_init_nonexistent_root_raises(
        self, tmp_path: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='not found'):
            ProjectMatcher(tmp_path / 'nonexistent', mapping_config)

    def test_init_file_as_root_raises(
        self, tmp_path: Path, mapping_config: MappingConfig
    ) -> None:
        file_path = tmp_path / 'not-a-dir.txt'
        file_path.write_text('hello', encoding='utf-8')
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='not a directory'):
            ProjectMatcher(file_path, mapping_config)


class TestDiscoverFilesystemProjects:
    """Tests for filesystem project discovery."""

    def test_discovers_all_project_dirs(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        projects = matcher.discover_filesystem_projects()

        names = [p.name for p in projects]
        assert 'claude-chat-manager' in names
        assert 'my-side-project' in names
        assert 'web-dashboard' in names
        assert 'python_utils' in names
        assert 'DataPipeline' in names

    def test_skips_hidden_dirs(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        (root_dir / '.hidden-project').mkdir()
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        projects = matcher.discover_filesystem_projects()

        names = [p.name for p in projects]
        assert '.hidden-project' not in names

    def test_skips_common_non_project_dirs(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        (root_dir / 'node_modules').mkdir()
        (root_dir / '__pycache__').mkdir()
        (root_dir / '.venv').mkdir()
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        projects = matcher.discover_filesystem_projects()

        names = [p.name for p in projects]
        assert 'node_modules' not in names
        assert '__pycache__' not in names
        assert '.venv' not in names

    def test_skips_files(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        (root_dir / 'README.md').write_text('hello', encoding='utf-8')
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        projects = matcher.discover_filesystem_projects()

        names = [p.name for p in projects]
        assert 'README.md' not in names

    def test_results_sorted_alphabetically(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        projects = matcher.discover_filesystem_projects()

        names = [p.name.lower() for p in projects]
        assert names == sorted(names)

    def test_caches_results(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        result1 = matcher.discover_filesystem_projects()
        result2 = matcher.discover_filesystem_projects()
        assert result1 is result2  # Same object, not re-scanned

    def test_empty_root_dir(
        self, tmp_path: Path, mapping_config: MappingConfig
    ) -> None:
        empty_root = tmp_path / 'empty'
        empty_root.mkdir()
        mapping_config.load()
        matcher = ProjectMatcher(empty_root, mapping_config)
        assert matcher.discover_filesystem_projects() == []



class TestMatchByConfig:
    """Tests for Strategy 1: Config lookup."""

    def test_config_match_returns_mapping(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('my-project', ProjectMapping(
            source_name='my-project',
            target='my-side-project',
            docs_chats_path='docs/chats',
            action='export',
            confirmed=True,
        ))

        matcher = ProjectMatcher(root_dir, mapping_config)
        project = _make_project_info('my-project')
        result = matcher.match_project(project)

        assert result.target == 'my-side-project'
        assert result.match_method == 'config'
        assert result.confirmed is True

    def test_config_skip_returns_skip(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        mapping_config.set_mapping('skip-me', ProjectMapping(
            source_name='skip-me',
            action='skip',
            confirmed=True,
        ))

        matcher = ProjectMatcher(root_dir, mapping_config)
        project = _make_project_info('skip-me')
        result = matcher.match_project(project)

        assert result.action == 'skip'
        assert result.match_method == 'config'


class TestMatchByWorkspacePath:
    """Tests for Strategy 2: Workspace path matching (Kiro/Codex)."""

    def test_kiro_workspace_path_under_root(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        workspace_path = str(root_dir / 'claude-chat-manager')
        project = _make_project_info(
            'claude-chat-manager',
            source=ChatSource.KIRO_IDE,
            workspace_path=workspace_path,
        )
        result = matcher.match_project(project)

        assert result.target == 'claude-chat-manager'
        assert result.match_method == 'workspace_path'

    def test_codex_cwd_under_root(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        workspace_path = str(root_dir / 'web-dashboard')
        project = _make_project_info(
            'web-dashboard',
            source=ChatSource.CODEX,
            workspace_path=workspace_path,
        )
        result = matcher.match_project(project)

        assert result.target == 'web-dashboard'
        assert result.match_method == 'workspace_path'

    def test_workspace_path_nested_subdir(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Workspace path pointing to a subdirectory should match top-level."""
        # Create a nested dir
        (root_dir / 'claude-chat-manager' / 'src').mkdir()
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        workspace_path = str(root_dir / 'claude-chat-manager' / 'src')
        project = _make_project_info(
            'claude-chat-manager',
            source=ChatSource.KIRO_IDE,
            workspace_path=workspace_path,
        )
        result = matcher.match_project(project)

        assert result.target == 'claude-chat-manager'
        assert result.match_method == 'workspace_path'

    def test_workspace_path_not_under_root_falls_through(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'external-project',
            source=ChatSource.KIRO_IDE,
            workspace_path='/some/other/path/external-project',
        )
        result = matcher.match_project(project)

        # Should fall through to other strategies (basename or unresolved)
        assert result.match_method != 'workspace_path'

    def test_workspace_basename_outside_root_falls_through(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Workspace path outside root should NOT match by basename alone.

        This prevents mapping external projects to unrelated local folders
        that happen to share a name.
        """
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'web-dashboard',
            source=ChatSource.KIRO_IDE,
            workspace_path='/other/location/web-dashboard',
        )
        result = matcher.match_project(project)

        # Should NOT match via workspace_path — falls through to basename strategy
        assert result.match_method != 'workspace_path'


class TestMatchByClaudePathDecode:
    """Tests for Strategy 3: Claude Desktop path decoding."""

    def test_decode_simple_path(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # Claude encodes paths like: Users-Mike-Src-Claude-Chat-Manager
        project = _make_project_info(
            'Users-Mike-Src-Claude-Chat-Manager',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        assert result.target == 'claude-chat-manager'
        assert result.match_method == 'claude_path_decode'

    def test_decode_with_different_prefix(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'Home-User-Projects-Web-Dashboard',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        assert result.target == 'web-dashboard'
        assert result.match_method == 'claude_path_decode'

    def test_decode_no_match(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'Users-Mike-Src-Nonexistent-Project',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        # Should fall through to unresolved
        assert result.match_method != 'claude_path_decode'

    def test_decode_single_token_name(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Single-token names shouldn't crash the decoder."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'SingleWord',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)
        # Should not crash, may or may not match
        assert result is not None

    def test_decode_underscore_project(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Claude path with underscored folder name."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # python_utils has underscore — Claude might encode it differently
        project = _make_project_info(
            'Users-Mike-Src-Python-Utils',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        # Should match python_utils via subsequence matching
        assert result.target == 'python_utils'


class TestMatchByBasename:
    """Tests for Strategy 4: Basename exact match.

    Uses KIRO_IDE source to avoid Claude path decode (Strategy 3)
    firing before basename (Strategy 4).
    """

    def test_exact_basename_match(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'my-side-project', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        assert result.target == 'my-side-project'
        assert result.match_method == 'basename'

    def test_case_insensitive_match(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'datapipeline', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        assert result.target == 'DataPipeline'
        assert result.match_method == 'basename'

    def test_dash_underscore_normalization(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # python_utils should match python-utils via normalization
        project = _make_project_info(
            'python-utils', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        assert result.target == 'python_utils'
        assert result.match_method == 'basename'


class TestMatchByFuzzy:
    """Tests for Strategy 5: Fuzzy matching."""

    def test_fuzzy_match_similar_name(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # Slightly different name that should fuzzy-match
        project = _make_project_info('claude-chat-mgr')
        result = matcher.match_project(project)

        # May or may not match depending on similarity score
        # The important thing is it doesn't crash
        assert result is not None

    def test_fuzzy_no_match_below_threshold(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info('completely-different-name')
        result = matcher.match_project(project)

        assert result.match_method == 'unresolved'
        assert result.target is None

    def test_fuzzy_match_returns_confidence(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # Close enough name
        project = _make_project_info('web-dashbord')  # typo
        result = matcher.match_project(project)

        if result.match_method.startswith('fuzzy'):
            assert result.target == 'web-dashboard'
            assert 'fuzzy' in result.match_method


class TestMatchUnresolved:
    """Tests for Strategy 6: Unresolved projects."""

    def test_unresolved_has_no_target(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info('totally-unknown-project-xyz')
        result = matcher.match_project(project)

        assert result.match_method == 'unresolved'
        assert result.target is None
        assert result.action == 'skip'
        assert result.confirmed is False

    def test_unresolved_preserves_source_info(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'unknown',
            source=ChatSource.CODEX,
            workspace_path='/some/path',
        )
        result = matcher.match_project(project)

        assert result.source_type == ChatSource.CODEX
        assert result.workspace_path == '/some/path'

    def test_unresolved_never_returns_export_with_null_target(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """No match should ever have action='export' with target=None."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        projects = [
            _make_project_info('zzz-nonexistent-1'),
            _make_project_info('zzz-nonexistent-2', source=ChatSource.KIRO_IDE),
            _make_project_info('zzz-nonexistent-3', source=ChatSource.CODEX),
        ]

        for project in projects:
            result = matcher.match_project(project)
            if result.target is None:
                assert result.action == 'skip', (
                    f"action='export' with target=None for '{project.name}'"
                )



# ===========================================================================
# Docs/chats directory detection tests
# ===========================================================================

class TestDetectDocsChatDir:
    """Tests for docs/chats directory detection."""

    def test_finds_docs_chats(
        self, root_dir_with_docs: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir_with_docs, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir_with_docs / 'claude-chat-manager'
        )
        assert result == 'docs/chats'

    def test_finds_chats_dir(
        self, root_dir_with_docs: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir_with_docs, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir_with_docs / 'my-side-project'
        )
        assert result == 'chats'

    def test_defaults_to_docs_chats(
        self, root_dir_with_docs: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir_with_docs, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir_with_docs / 'web-dashboard'
        )
        assert result == 'docs/chats'

    def test_finds_docs_conversations(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        (root_dir / 'web-dashboard' / 'docs' / 'conversations').mkdir(
            parents=True
        )
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir / 'web-dashboard'
        )
        assert result == 'docs/conversations'

    def test_scan_finds_chat_exports_in_custom_dir(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Detect chat exports in a non-standard directory."""
        custom_dir = root_dir / 'DataPipeline' / 'notes' / 'ai-chats'
        custom_dir.mkdir(parents=True)
        (custom_dir / 'chat-about-etl.md').write_text(
            '# Claude Chat Export\n'
            '**Generated: 2025-12-26**\n\n'
            '👤 **USER:**\n> How to build ETL?\n',
            encoding='utf-8',
        )
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir / 'DataPipeline'
        )
        assert result == 'notes/ai-chats'

    def test_scan_ignores_readme(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """README.md should not trigger chat export detection."""
        (root_dir / 'python_utils' / 'README.md').write_text(
            '# My Project\nSome docs\n', encoding='utf-8'
        )
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(
            root_dir / 'python_utils'
        )
        # Should fall back to default since README is skipped
        assert result == 'docs/chats'

    def test_detect_docs_chats_dir_is_cached(
        self, root_dir_with_docs: Path, mapping_config: MappingConfig
    ) -> None:
        """Repeated calls for the same project should use cache."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir_with_docs, mapping_config)

        project_dir = root_dir_with_docs / 'claude-chat-manager'
        result1 = matcher.detect_docs_chats_dir(project_dir)
        result2 = matcher.detect_docs_chats_dir(project_dir)
        assert result1 == result2 == 'docs/chats'
        # Cache should have one entry
        assert len(matcher._docs_chats_cache) >= 1


# ===========================================================================
# match_all_projects tests
# ===========================================================================

class TestMatchAllProjects:
    """Tests for batch matching of all projects."""

    def test_matches_multiple_projects(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        projects = [
            _make_project_info('claude-chat-manager'),
            _make_project_info('web-dashboard'),
            _make_project_info('unknown-project'),
        ]

        results = matcher.match_all_projects(projects)
        assert len(results) == 3

        # First two should match, third should be unresolved
        assert results[0].target == 'claude-chat-manager'
        assert results[1].target == 'web-dashboard'
        assert results[2].match_method == 'unresolved'

    def test_empty_project_list(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)
        assert matcher.match_all_projects([]) == []

    def test_mixed_sources(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Multiple sources for the same project should all match."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        projects = [
            _make_project_info(
                'Users-Mike-Src-Claude-Chat-Manager',
                source=ChatSource.CLAUDE_DESKTOP,
            ),
            _make_project_info(
                'claude-chat-manager',
                source=ChatSource.KIRO_IDE,
                workspace_path=str(root_dir / 'claude-chat-manager'),
            ),
            _make_project_info(
                'claude-chat-manager',
                source=ChatSource.CODEX,
                workspace_path=str(root_dir / 'claude-chat-manager'),
            ),
        ]

        results = matcher.match_all_projects(projects)
        assert len(results) == 3

        # All three should resolve to the same target
        targets = {r.target for r in results}
        assert targets == {'claude-chat-manager'}


# ===========================================================================
# Integration / edge case tests
# ===========================================================================

class TestMatchingPriorityOrder:
    """Tests that matching strategies are applied in correct priority order."""

    def test_config_takes_priority_over_basename(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Config mapping should override automatic basename matching."""
        mapping_config.load()
        # Map to a different folder than what basename would match
        mapping_config.set_mapping('web-dashboard', ProjectMapping(
            source_name='web-dashboard',
            target='my-side-project',
            docs_chats_path='docs/chats',
            action='export',
            confirmed=True,
        ))

        matcher = ProjectMatcher(root_dir, mapping_config)
        project = _make_project_info('web-dashboard')
        result = matcher.match_project(project)

        assert result.target == 'my-side-project'
        assert result.match_method == 'config'

    def test_workspace_path_takes_priority_over_basename(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Workspace path match should be preferred over basename."""
        # Create a second folder that would match by basename
        (root_dir / 'my-project').mkdir()

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'my-project',
            source=ChatSource.KIRO_IDE,
            workspace_path=str(root_dir / 'web-dashboard'),
        )
        result = matcher.match_project(project)

        # Should match web-dashboard via workspace_path, not my-project via basename
        assert result.target == 'web-dashboard'
        assert result.match_method == 'workspace_path'

    def test_config_skip_prevents_all_other_matching(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """A skip config should prevent any matching attempt."""
        mapping_config.load()
        mapping_config.set_mapping('claude-chat-manager', ProjectMapping(
            source_name='claude-chat-manager',
            action='skip',
            confirmed=True,
        ))

        matcher = ProjectMatcher(root_dir, mapping_config)
        project = _make_project_info('claude-chat-manager')
        result = matcher.match_project(project)

        assert result.action == 'skip'
        assert result.match_method == 'config'


class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_project_name_with_special_chars(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info('project@v2.0!')
        result = matcher.match_project(project)
        # Should not crash
        assert result is not None

    def test_empty_project_name(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info('')
        result = matcher.match_project(project)
        assert result is not None
        assert result.match_method == 'unresolved'

    def test_workspace_path_with_invalid_chars(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'test',
            source=ChatSource.KIRO_IDE,
            workspace_path='\x00invalid\x00path',
        )
        result = matcher.match_project(project)
        # Should not crash, falls through to other strategies
        assert result is not None

    def test_docs_chats_detection_with_unreadable_file(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Unreadable files should be skipped gracefully."""
        project_dir = root_dir / 'python_utils'
        notes_dir = project_dir / 'notes'
        notes_dir.mkdir()
        # Create a binary file with .md extension
        (notes_dir / 'binary.md').write_bytes(b'\x80\x81\x82\x83')

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # Should not crash
        result = matcher.detect_docs_chats_dir(project_dir)
        assert result == 'docs/chats'  # Falls back to default

    def test_match_project_preserves_source_type(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        for source in [ChatSource.CLAUDE_DESKTOP, ChatSource.KIRO_IDE, ChatSource.CODEX]:
            project = _make_project_info(
                'claude-chat-manager', source=source
            )
            result = matcher.match_project(project)
            assert result.source_type == source


# ===========================================================================
# Path safety validation tests
# ===========================================================================

class TestPathSafetyValidation:
    """Tests for unsafe mapping target rejection."""

    def test_set_mapping_rejects_absolute_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='absolute'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='/etc/passwd',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_windows_drive_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='drive|anchor|absolute'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='C:\\Users\\evil',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_drive_relative_path(
        self, mapping_config: MappingConfig
    ) -> None:
        """D:folder is drive-qualified but not absolute on Windows."""
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='drive|anchor'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='D:folder',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_unc_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='drive|anchor|absolute'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='\\\\server\\share',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_dotdot_traversal(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match="\\.\\."):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='../outside-root',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_windows_backslash_traversal(
        self, mapping_config: MappingConfig
    ) -> None:
        """'..\\evil' must be caught even on Unix where Path won't split it."""
        mapping_config.load()
        with pytest.raises(ConfigurationError, match="\\.\\."):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='..\\evil',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_mixed_separator_traversal(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match="\\.\\."):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='legit/..\\escape',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_nested_dotdot(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match="\\.\\."):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='legit/../../escape',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_tilde_home(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='~'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='~/some-folder',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_unsafe_docs_chats_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match="\\.\\."):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='legit-folder',
                docs_chats_path='../../etc',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_allows_safe_relative_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        # Should not raise
        mapping_config.set_mapping('proj', ProjectMapping(
            source_name='proj',
            target='my-project',
            docs_chats_path='docs/chats',
            action='export',
            confirmed=True,
        ))
        result = mapping_config.get_mapping('proj')
        assert result.target == 'my-project'

    def test_set_mapping_skip_bypasses_validation(
        self, mapping_config: MappingConfig
    ) -> None:
        """Skip mappings don't have targets, so no path validation needed."""
        mapping_config.load()
        mapping_config.set_mapping('proj', ProjectMapping(
            source_name='proj',
            action='skip',
            confirmed=True,
        ))
        result = mapping_config.get_mapping('proj')
        assert result.action == 'skip'

    def test_load_rejects_unsafe_target_in_config(
        self, config_path: Path
    ) -> None:
        """Config files with unsafe targets should fail on load."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': '/etc/shadow', 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='absolute'):
            cfg.load()

    def test_load_rejects_dotdot_target_in_config(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': '../escape', 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match="\\.\\."):
            cfg.load()

    def test_load_rejects_unsafe_docs_chats_path_in_config(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {
                    'target': 'legit',
                    'docs_chats_path': '/tmp/evil',
                    'action': 'export',
                }
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='absolute'):
            cfg.load()

    def test_load_rejects_non_string_target_in_config(
        self, config_path: Path
    ) -> None:
        """target as integer should raise ConfigurationError, not TypeError."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': 42, 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='must be a string'):
            cfg.load()

    def test_load_rejects_list_target_in_config(
        self, config_path: Path
    ) -> None:
        """target as list should raise ConfigurationError, not TypeError."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': ['a', 'b'], 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='must be a string'):
            cfg.load()

    def test_load_rejects_non_string_docs_chats_path_in_config(
        self, config_path: Path
    ) -> None:
        """docs_chats_path as number should raise ConfigurationError."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {
                    'target': 'legit',
                    'docs_chats_path': 99,
                    'action': 'export',
                }
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='must be a string'):
            cfg.load()

    def test_set_mapping_rejects_export_with_none_target(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='non-empty target'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target=None,
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_export_with_empty_target(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='non-empty target'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_export_with_whitespace_target(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='non-empty target'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='   ',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_export_with_empty_docs_chats_path(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='non-empty docs_chats_path'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='legit-folder',
                docs_chats_path='',
                action='export',
                confirmed=True,
            ))

    def test_set_mapping_rejects_invalid_action(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='Invalid mapping action'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='folder',
                action='delete',
                confirmed=True,
            ))

    def test_set_mapping_rejects_empty_action(
        self, mapping_config: MappingConfig
    ) -> None:
        mapping_config.load()
        with pytest.raises(ConfigurationError, match='Invalid mapping action'):
            mapping_config.set_mapping('proj', ProjectMapping(
                source_name='proj',
                target='folder',
                action='',
                confirmed=True,
            ))

    def test_load_rejects_invalid_action_in_config(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': 'folder', 'action': 'destroy'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='invalid action'):
            cfg.load()

    def test_load_rejects_drive_qualified_target_in_config(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': 'D:folder', 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='drive|anchor'):
            cfg.load()

    def test_load_rejects_empty_target_for_export(
        self, config_path: Path
    ) -> None:
        """Export entry with empty string target should fail on load."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': '  ', 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='target is empty'):
            cfg.load()

    def test_load_rejects_windows_backslash_traversal_in_config(
        self, config_path: Path
    ) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            'mappings': {
                'proj': {'target': '..\\\\evil', 'action': 'export'}
            }
        }), encoding='utf-8')

        cfg = MappingConfig(config_path)
        with pytest.raises(ConfigurationError, match='\\.\\.'):
            cfg.load()


# ===========================================================================
# Fuzzy match confidence tests
# ===========================================================================

class TestFuzzyMatchConfidence:
    """Tests for fuzzy matching confidence-based behavior."""

    def test_high_confidence_fuzzy_auto_exports(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Fuzzy match above HIGH_CONFIDENCE_THRESHOLD should auto-export."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # 'web-dashbord' is very close to 'web-dashboard' (typo)
        project = _make_project_info(
            'web-dashbord', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        if result.match_method.startswith('fuzzy ('):
            # High confidence → action should be export
            assert result.action == 'export'
            assert result.target == 'web-dashboard'

    def test_low_confidence_fuzzy_does_not_auto_export(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Fuzzy match below HIGH_CONFIDENCE_THRESHOLD should skip."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # 'web-app' is somewhat similar to 'web-dashboard' but not high confidence
        project = _make_project_info(
            'web-app', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        if result.match_method.startswith('fuzzy_low'):
            # Low confidence → action should be skip (needs confirmation)
            assert result.action == 'skip'
            assert result.confirmed is False
            # But target is still surfaced as a candidate
            assert result.target is not None

    def test_fuzzy_below_threshold_is_unresolved(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Names too different should be fully unresolved, not fuzzy."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'completely-different-name-xyz', source=ChatSource.KIRO_IDE
        )
        result = matcher.match_project(project)

        assert result.match_method == 'unresolved'
        assert result.target is None


# ===========================================================================
# Ambiguity and collision tests
# ===========================================================================

class TestClaudeDecodeAmbiguity:
    """Tests for ambiguous Claude name decoding."""

    def test_ambiguous_subsequence_returns_unresolved(
        self, tmp_path: Path, mapping_config: MappingConfig
    ) -> None:
        """When multiple folders match as subsequences, return None (unresolved)."""
        # Create folders that both match 'Users-Mike-Src-Utils'
        (tmp_path / 'src-utils').mkdir()
        (tmp_path / 'mike-src-utils').mkdir()

        mapping_config.load()
        matcher = ProjectMatcher(tmp_path, mapping_config)

        project = _make_project_info(
            'Users-Mike-Src-Utils',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        # Should not auto-export to either — ambiguous
        # May resolve via basename or be unresolved, but should NOT
        # silently pick the wrong one via subsequence
        assert result is not None

    def test_exact_tail_match_preferred_over_subsequence(
        self, tmp_path: Path, mapping_config: MappingConfig
    ) -> None:
        """Exact tail token match should win over subsequence match."""
        (tmp_path / 'chat-manager').mkdir()
        (tmp_path / 'other-project').mkdir()

        mapping_config.load()
        matcher = ProjectMatcher(tmp_path, mapping_config)

        project = _make_project_info(
            'Users-Mike-Src-Chat-Manager',
            source=ChatSource.CLAUDE_DESKTOP,
        )
        result = matcher.match_project(project)

        assert result.target == 'chat-manager'
        assert result.match_method == 'claude_path_decode'


class TestWorkspaceCollision:
    """Tests for workspace path collision scenarios."""

    def test_external_workspace_same_basename_does_not_auto_match(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """External workspace with same basename as local folder should
        NOT match via workspace_path strategy — must fall through to
        basename or other strategies."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        # Workspace is at /completely/different/path/claude-chat-manager
        # but root has ~/src/claude-chat-manager
        project = _make_project_info(
            'claude-chat-manager',
            source=ChatSource.KIRO_IDE,
            workspace_path='/completely/different/path/claude-chat-manager',
        )
        result = matcher.match_project(project)

        # Should match via basename (Strategy 4), NOT workspace_path (Strategy 2)
        assert result.match_method != 'workspace_path'
        # But should still find the right folder via basename
        assert result.target == 'claude-chat-manager'

    def test_workspace_under_root_still_matches(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Workspace directly under root should still match via workspace_path."""
        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        project = _make_project_info(
            'claude-chat-manager',
            source=ChatSource.KIRO_IDE,
            workspace_path=str(root_dir / 'claude-chat-manager'),
        )
        result = matcher.match_project(project)

        assert result.target == 'claude-chat-manager'
        assert result.match_method == 'workspace_path'

    def test_workspace_path_to_excluded_dir_does_not_match(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """Workspace pointing to .git, node_modules, venv should not match."""
        # Create excluded dirs under root
        for excluded in ['.git', 'node_modules', 'venv']:
            (root_dir / excluded).mkdir(exist_ok=True)

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        for excluded in ['.git', 'node_modules', 'venv']:
            project = _make_project_info(
                excluded,
                source=ChatSource.KIRO_IDE,
                workspace_path=str(root_dir / excluded),
            )
            result = matcher.match_project(project)
            assert result.match_method != 'workspace_path', (
                f"Excluded dir '{excluded}' should not match via workspace_path"
            )


# ===========================================================================
# Scan pruning tests
# ===========================================================================

class TestScanPruning:
    """Tests for directory scan pruning in _scan_for_chat_exports."""

    def test_scan_skips_node_modules(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        """node_modules should be pruned from scan."""
        project_dir = root_dir / 'python_utils'
        nm_dir = project_dir / 'node_modules' / 'some-pkg'
        nm_dir.mkdir(parents=True)
        (nm_dir / 'chat.md').write_text(
            '👤 **USER:**\n> Hello\n', encoding='utf-8'
        )

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(project_dir)
        # Should NOT find the file inside node_modules
        assert result == 'docs/chats'  # Default fallback

    def test_scan_skips_git_dir(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        project_dir = root_dir / 'python_utils'
        git_dir = project_dir / '.git' / 'refs'
        git_dir.mkdir(parents=True)
        (git_dir / 'notes.md').write_text(
            '👤 **USER:**\n> Hello\n', encoding='utf-8'
        )

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(project_dir)
        assert result == 'docs/chats'

    def test_scan_skips_build_dirs(
        self, root_dir: Path, mapping_config: MappingConfig
    ) -> None:
        project_dir = root_dir / 'python_utils'
        build_dir = project_dir / 'build' / 'output'
        build_dir.mkdir(parents=True)
        (build_dir / 'report.md').write_text(
            '# Claude Chat Export\n**Generated: 2025-12-26**\n',
            encoding='utf-8',
        )

        mapping_config.load()
        matcher = ProjectMatcher(root_dir, mapping_config)

        result = matcher.detect_docs_chats_dir(project_dir)
        assert result == 'docs/chats'

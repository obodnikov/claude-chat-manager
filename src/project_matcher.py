"""Project matching and mapping configuration for auto-export.

This module provides smart matching between conversation project names
(from Claude Desktop, Kiro IDE, Codex CLI) and filesystem project folders.
It also manages the persistent mapping configuration file.

Matching strategy (priority order):
1. Config lookup — already mapped in config
2. Exact path match — Kiro/Codex workspace_path resolves under root
3. Claude path decode — encoded project name decoded to filesystem path
4. Basename exact match — case-insensitive folder name comparison
5. Fuzzy match — token-based similarity with confidence threshold
6. Unresolved — skip or fallback per config
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .exceptions import ConfigurationError
from .models import ChatSource, ProjectInfo

logger = logging.getLogger(__name__)

# Default config file location
DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'claude-chat-manager'
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / 'project-mapping.json'

# Matching confidence thresholds
FUZZY_MATCH_THRESHOLD = 0.7
HIGH_CONFIDENCE_THRESHOLD = 0.85

# Chat export fingerprint patterns (to detect docs/chats directories)
CHAT_EXPORT_PATTERNS = [
    r'👤 \*\*USER:\*\*',
    r'🤖 \*\*ASSISTANT:\*\*',
    r'^# Claude Chat Export',
    r'^# Chat:',
    r'^\*\*Generated:',
]


@dataclass
class ProjectMapping:
    """Single project mapping entry.

    Attributes:
        source_name: Conversation project name as discovered by sources.
        target: Folder name relative to root directory, or None if unresolved.
        docs_chats_path: Relative path to docs/chats inside target folder.
        action: What to do: 'export' or 'skip'.
        confirmed: Whether user confirmed this mapping in learn mode.
        match_method: How the match was determined (for debugging/display).
        source_type: Which chat source this came from.
        workspace_path: Original workspace path from Kiro/Codex (optional).
    """

    source_name: str
    target: Optional[str] = None
    docs_chats_path: str = "docs/chats"
    action: str = "export"
    confirmed: bool = False
    match_method: str = "unresolved"
    source_type: ChatSource = ChatSource.UNKNOWN
    workspace_path: Optional[str] = None


def _validate_target_path(target: Optional[str]) -> None:
    """Validate that a mapping target is a safe relative path.

    Rejects absolute paths, drive-qualified paths, anchored paths,
    '..' traversal segments, non-string types, and other patterns
    that could escape the root directory boundary.

    Args:
        target: Target folder name to validate.

    Raises:
        ConfigurationError: If target is unsafe or wrong type.
    """
    if target is None:
        return

    # Reject non-string types
    if not isinstance(target, str):
        raise ConfigurationError(
            f"Mapping target must be a string, "
            f"got {type(target).__name__}: {target!r}"
        )

    # Reject absolute paths (covers Unix /path and Windows C:\path)
    if os.path.isabs(target):
        raise ConfigurationError(
            f"Mapping target must be a relative path, got absolute: '{target}'"
        )

    # Reject drive-qualified or anchored paths (e.g., 'D:folder', '\\server')
    # pathlib.PurePosixPath won't detect Windows drives on Unix, so also
    # check with PureWindowsPath for cross-platform safety
    from pathlib import PureWindowsPath
    win_path = PureWindowsPath(target)
    if win_path.drive or win_path.anchor:
        raise ConfigurationError(
            f"Mapping target must not contain a drive or anchor: '{target}'"
        )

    # Reject '..' traversal segments using both Posix and Windows parsing
    # On Unix, Path('..\\evil').parts won't split on backslash, so we
    # must also check PureWindowsPath to catch Windows-style traversal
    from pathlib import PurePosixPath
    posix_parts = PurePosixPath(target).parts
    win_parts = win_path.parts
    if '..' in posix_parts or '..' in win_parts:
        raise ConfigurationError(
            f"Mapping target must not contain '..' traversal: '{target}'"
        )

    # Reject paths starting with '~' (home expansion)
    if target.startswith('~'):
        raise ConfigurationError(
            f"Mapping target must not start with '~': '{target}'"
        )



class MappingConfig:
    """Manages project mapping configuration file.

    Handles loading, saving, and querying the JSON config that stores
    project-to-folder mappings for auto-export.

    Attributes:
        config_path: Path to the JSON configuration file.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize mapping config manager.

        Args:
            config_path: Path to config file. Uses default if not provided.
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._data: Dict = {}

    def load(self) -> Dict:
        """Load config from JSON file.

        Returns:
            Parsed config dictionary.

        Raises:
            ConfigurationError: If config file exists but is malformed,
                has invalid schema types, or cannot be read.
        """
        if not self.config_path.exists():
            logger.debug(f"No config file found at {self.config_path}")
            self._data = self._default_config()
            return self._data

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)

            # Validate top-level structure
            if not isinstance(self._data, dict):
                raise ConfigurationError(
                    f"Config file must contain a JSON object: {self.config_path}"
                )

            # Ensure required keys exist with correct types
            if 'mappings' not in self._data:
                self._data['mappings'] = {}
            if 'version' not in self._data:
                self._data['version'] = '1.0'

            # Validate mappings is a dict
            if not isinstance(self._data['mappings'], dict):
                raise ConfigurationError(
                    f"'mappings' must be a JSON object, "
                    f"got {type(self._data['mappings']).__name__}: "
                    f"{self.config_path}"
                )

            # Validate each mapping entry is a dict
            for key, entry in self._data['mappings'].items():
                if not isinstance(entry, dict):
                    raise ConfigurationError(
                        f"Mapping entry '{key}' must be a JSON object, "
                        f"got {type(entry).__name__}: {self.config_path}"
                    )
                # Validate action value if present
                action = entry.get('action')
                if action is not None and action not in ('export', 'skip'):
                    raise ConfigurationError(
                        f"Mapping entry '{key}' has invalid action "
                        f"'{action}'. Must be 'export' or 'skip': "
                        f"{self.config_path}"
                    )
                # Validate target path safety
                target = entry.get('target')
                if target is not None:
                    _validate_target_path(target)
                docs_path = entry.get('docs_chats_path')
                if docs_path is not None:
                    _validate_target_path(docs_path)

                # Enforce export schema: non-skip entries need valid target
                effective_action = action or 'export'
                if effective_action != 'skip':
                    if target is not None and isinstance(target, str) and not target.strip():
                        raise ConfigurationError(
                            f"Mapping entry '{key}' has action '{effective_action}' "
                            f"but target is empty: {self.config_path}"
                        )

            logger.info(
                f"Loaded config with {len(self._data['mappings'])} mappings "
                f"from {self.config_path}"
            )
            return self._data

        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in config file {self.config_path}: {e}"
            )
        except OSError as e:
            raise ConfigurationError(
                f"Failed to read config file {self.config_path}: {e}"
            )

    def save(self) -> None:
        """Save current config to JSON file atomically.

        Writes to a temporary file first, then replaces the target to
        prevent corruption from interrupted writes.
        Creates parent directories if they don't exist.

        Raises:
            ConfigurationError: If save operation fails.
        """
        import tempfile

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: temp file → flush/fsync → replace
            fd, tmp_path = tempfile.mkstemp(
                dir=self.config_path.parent,
                prefix='.project-mapping-',
                suffix='.tmp',
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.config_path)
            except BaseException:
                # Clean up temp file on any failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info(f"Saved config to {self.config_path}")

        except OSError as e:
            raise ConfigurationError(f"Failed to save config: {e}")

    def get_mapping(self, project_name: str) -> Optional[ProjectMapping]:
        """Look up mapping for a project name.

        Args:
            project_name: Conversation project name to look up.

        Returns:
            ProjectMapping if found, None otherwise.
        """
        mappings = self._data.get('mappings', {})
        entry = mappings.get(project_name)

        if entry is None:
            return None

        # Handle skip action
        if entry.get('action') == 'skip':
            return ProjectMapping(
                source_name=project_name,
                action='skip',
                confirmed=entry.get('confirmed', True),
                match_method='config',
            )

        return ProjectMapping(
            source_name=project_name,
            target=entry.get('target'),
            docs_chats_path=entry.get('docs_chats_path', 'docs/chats'),
            action=entry.get('action', 'export'),
            confirmed=entry.get('confirmed', False),
            match_method='config',
        )

    # Valid action values
    VALID_ACTIONS = {'export', 'skip'}

    def set_mapping(self, project_name: str, mapping: ProjectMapping) -> None:
        """Set or update mapping for a project name.

        Args:
            project_name: Conversation project name.
            mapping: ProjectMapping to store.

        Raises:
            ConfigurationError: If mapping action is invalid, target is
                unsafe, or action is 'export' but target is missing/empty.
        """
        # Validate action
        if mapping.action not in self.VALID_ACTIONS:
            raise ConfigurationError(
                f"Invalid mapping action '{mapping.action}' for '{project_name}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_ACTIONS))}"
            )

        if mapping.action != 'skip':
            # Export mappings require a valid non-empty target
            if not mapping.target or not mapping.target.strip():
                raise ConfigurationError(
                    f"Export mapping for '{project_name}' requires "
                    f"a non-empty target folder"
                )
            if not mapping.docs_chats_path or not mapping.docs_chats_path.strip():
                raise ConfigurationError(
                    f"Export mapping for '{project_name}' requires "
                    f"a non-empty docs_chats_path"
                )
            # Validate path safety
            _validate_target_path(mapping.target)
            _validate_target_path(mapping.docs_chats_path)

        if 'mappings' not in self._data:
            self._data['mappings'] = {}

        entry: Dict = {}

        if mapping.action == 'skip':
            entry['action'] = 'skip'
            entry['confirmed'] = mapping.confirmed
        else:
            entry['target'] = mapping.target
            entry['docs_chats_path'] = mapping.docs_chats_path
            entry['action'] = mapping.action
            entry['confirmed'] = mapping.confirmed

        self._data['mappings'][project_name] = entry

    def set_root_directory(self, root_dir: str) -> None:
        """Set the root directory in config.

        Args:
            root_dir: Root directory path string.
        """
        self._data['root_directory'] = root_dir

    def get_root_directory(self) -> Optional[str]:
        """Get the root directory from config.

        Returns:
            Root directory path string, or None if not set.
        """
        return self._data.get('root_directory')

    def set_last_learned(self) -> None:
        """Update the last_learned timestamp to now."""
        self._data['last_learned'] = datetime.now().isoformat()

    def get_all_mappings(self) -> Dict[str, ProjectMapping]:
        """Get all mappings as ProjectMapping objects.

        Returns:
            Dictionary of project_name → ProjectMapping.
        """
        result = {}
        for name in self._data.get('mappings', {}):
            mapping = self.get_mapping(name)
            if mapping:
                result[name] = mapping
        return result

    def get_confirmed_targets(self) -> Dict[str, str]:
        """Get all confirmed target folder names.

        Returns:
            Dictionary of project_name → target folder name.
        """
        result = {}
        for name, entry in self._data.get('mappings', {}).items():
            if entry.get('confirmed') and entry.get('target'):
                result[name] = entry['target']
        return result

    @property
    def data(self) -> Dict:
        """Access raw config data.

        Returns:
            The internal config dictionary.
        """
        return self._data

    def _default_config(self) -> Dict:
        """Create default config structure.

        Returns:
            Default config dictionary.
        """
        return {
            'version': '1.0',
            'root_directory': None,
            'defaults': {
                'export_format': 'book',
                'unmatched_action': 'skip',
            },
            'mappings': {},
        }


class ProjectMatcher:
    """Smart project name → filesystem folder matching.

    Matches conversation project names from various sources (Claude Desktop,
    Kiro IDE, Codex CLI) to actual project directories on the filesystem.

    Attributes:
        root_dir: Root directory containing project folders.
        config: MappingConfig for persistent mapping storage.
    """

    def __init__(self, root_dir: Path, config: MappingConfig) -> None:
        """Initialize project matcher.

        Args:
            root_dir: Root directory containing project folders.
            config: MappingConfig instance for persistent storage.

        Raises:
            ConfigurationError: If root_dir doesn't exist or isn't a directory.
        """
        if not root_dir.exists():
            raise ConfigurationError(f"Root directory not found: {root_dir}")
        if not root_dir.is_dir():
            raise ConfigurationError(f"Root path is not a directory: {root_dir}")

        self.root_dir = root_dir.resolve()
        self.config = config
        self._fs_projects: Optional[List[Path]] = None
        self._docs_chats_cache: Dict[Path, str] = {}

    def discover_filesystem_projects(self) -> List[Path]:
        """Scan root directory for project folders.

        Returns immediate subdirectories of root that look like project
        directories (skips hidden dirs and common non-project dirs).

        Returns:
            Sorted list of project directory paths.
        """
        if self._fs_projects is not None:
            return self._fs_projects

        skip_names = {
            '.git', '.svn', '.hg', '__pycache__', 'node_modules',
            '.venv', 'venv', '.env', '.cache', '.tmp',
            '_unmatched',
        }

        projects = []
        for entry in self.root_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith('.') and entry.name not in ('.git',):
                continue
            if entry.name in skip_names:
                continue
            projects.append(entry)

        projects.sort(key=lambda p: p.name.lower())
        self._fs_projects = projects

        logger.debug(f"Found {len(projects)} project folders in {self.root_dir}")
        return projects

    def match_project(self, project_info: ProjectInfo) -> ProjectMapping:
        """Match a conversation project to a filesystem folder.

        Runs through matching strategies in priority order and returns
        the best match found.

        Args:
            project_info: ProjectInfo from source discovery.

        Returns:
            ProjectMapping with match result (may be unresolved).
        """
        project_name = project_info.name
        source_type = project_info.source

        # Strategy 1: Config lookup
        config_mapping = self.config.get_mapping(project_name)
        if config_mapping is not None:
            config_mapping.source_type = source_type
            config_mapping.workspace_path = project_info.workspace_path
            logger.debug(f"Config match for '{project_name}': {config_mapping.target}")
            return config_mapping

        # Strategy 2: Exact path match (Kiro/Codex workspace_path)
        if project_info.workspace_path:
            match = self._match_by_workspace_path(project_info.workspace_path)
            if match:
                docs_path = self.detect_docs_chats_dir(match)
                return ProjectMapping(
                    source_name=project_name,
                    target=match.name,
                    docs_chats_path=docs_path,
                    action='export',
                    confirmed=False,
                    match_method='workspace_path',
                    source_type=source_type,
                    workspace_path=project_info.workspace_path,
                )

        # Strategy 3: Claude path decode
        if source_type == ChatSource.CLAUDE_DESKTOP:
            match = self._decode_claude_project_name(project_name)
            if match:
                docs_path = self.detect_docs_chats_dir(match)
                return ProjectMapping(
                    source_name=project_name,
                    target=match.name,
                    docs_chats_path=docs_path,
                    action='export',
                    confirmed=False,
                    match_method='claude_path_decode',
                    source_type=source_type,
                    workspace_path=project_info.workspace_path,
                )

        # Strategy 4: Basename exact match
        match = self._match_by_basename(project_name)
        if match:
            docs_path = self.detect_docs_chats_dir(match)
            return ProjectMapping(
                source_name=project_name,
                target=match.name,
                docs_chats_path=docs_path,
                action='export',
                confirmed=False,
                match_method='basename',
                source_type=source_type,
                workspace_path=project_info.workspace_path,
            )

        # Strategy 5: Fuzzy match
        fuzzy_result = self._match_fuzzy(project_name)
        if fuzzy_result:
            match_path, confidence = fuzzy_result
            docs_path = self.detect_docs_chats_dir(match_path)

            # High confidence: safe for automatic export
            # Low confidence: mark as unresolved to require confirmation
            if confidence >= HIGH_CONFIDENCE_THRESHOLD:
                return ProjectMapping(
                    source_name=project_name,
                    target=match_path.name,
                    docs_chats_path=docs_path,
                    action='export',
                    confirmed=False,
                    match_method=f'fuzzy ({confidence:.0%})',
                    source_type=source_type,
                    workspace_path=project_info.workspace_path,
                )
            else:
                # Low-confidence fuzzy: surface the candidate but don't
                # auto-export — requires user confirmation in learn mode
                logger.debug(
                    f"Low-confidence fuzzy match for '{project_name}': "
                    f"{match_path.name} ({confidence:.0%})"
                )
                return ProjectMapping(
                    source_name=project_name,
                    target=match_path.name,
                    docs_chats_path=docs_path,
                    action='skip',
                    confirmed=False,
                    match_method=f'fuzzy_low ({confidence:.0%})',
                    source_type=source_type,
                    workspace_path=project_info.workspace_path,
                )

        # Strategy 6: Unresolved
        logger.debug(f"No match found for '{project_name}'")
        return ProjectMapping(
            source_name=project_name,
            target=None,
            action='skip',
            confirmed=False,
            match_method='unresolved',
            source_type=source_type,
            workspace_path=project_info.workspace_path,
        )

    def _match_by_workspace_path(self, workspace_path: str) -> Optional[Path]:
        """Match by Kiro/Codex workspace_path or cwd.

        Only matches when the workspace path resolves to a directory
        that is directly under root_dir. Does NOT fall back to basename
        matching to avoid mapping external projects to unrelated local
        folders that happen to share a name.

        Args:
            workspace_path: Full workspace path from Kiro/Codex.

        Returns:
            Matched project directory Path, or None.
        """
        try:
            ws_path = Path(workspace_path).resolve()
        except (ValueError, OSError):
            return None

        # Direct match: workspace_path is under root_dir
        try:
            if ws_path.is_relative_to(self.root_dir) and ws_path.exists():
                # Find the immediate child of root_dir
                relative = ws_path.relative_to(self.root_dir)
                top_level = self.root_dir / relative.parts[0]
                if top_level.is_dir():
                    # Validate against project discovery exclusion rules
                    # to prevent matching .git, node_modules, venv, etc.
                    valid_projects = self.discover_filesystem_projects()
                    if top_level in valid_projects:
                        return top_level
                    logger.debug(
                        f"Workspace path resolved to excluded dir: "
                        f"{top_level.name}"
                    )
        except (ValueError, IndexError):
            pass

        return None

    def _decode_claude_project_name(self, name: str) -> Optional[Path]:
        """Decode Claude Desktop encoded project name to filesystem path.

        Claude encodes project paths as directory names. The encoding
        replaces path separators with dashes and title-cases segments.
        Example: 'Users-Mike-Src-Claude-Chat-Manager'

        This method tries to reconstruct the original path and match
        it against root directory contents. If multiple candidates are
        found, returns None to avoid ambiguous auto-mapping.

        Args:
            name: Claude Desktop project name (may be encoded path).

        Returns:
            Matched project directory Path, or None if no match or ambiguous.
        """
        # Split the name into tokens
        tokens = name.split('-')
        if len(tokens) < 2:
            return None

        fs_projects = self.discover_filesystem_projects()
        fs_names = {p.name.lower(): p for p in fs_projects}

        candidates: List[Path] = []

        # Try matching the last N tokens as a project folder name
        # Start from longer matches (more specific) to shorter
        for length in range(min(len(tokens), 5), 0, -1):
            candidate = '-'.join(tokens[-length:]).lower()
            if candidate in fs_names:
                # Longer match is more specific — return immediately
                return fs_names[candidate]

        # Try joining last N tokens with different separators
        for length in range(min(len(tokens), 5), 1, -1):
            tail_tokens = tokens[-length:]

            for separator in ['-', '_', '']:
                candidate = separator.join(tail_tokens).lower()
                if candidate in fs_names and fs_names[candidate] not in candidates:
                    candidates.append(fs_names[candidate])

        # If exactly one candidate from separator variations, use it
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            logger.debug(
                f"Ambiguous Claude decode for '{name}': "
                f"{[c.name for c in candidates]}"
            )
            return None

        # Try matching folder name tokens as contiguous subsequence
        # Collect all matches — if ambiguous, return None
        subseq_candidates: List[Path] = []
        for fs_name_lower, fs_path in fs_names.items():
            folder_tokens = re.split(r'[-_]', fs_name_lower)
            name_tokens_lower = [t.lower() for t in tokens]

            if _is_subsequence(folder_tokens, name_tokens_lower):
                subseq_candidates.append(fs_path)

        if len(subseq_candidates) == 1:
            return subseq_candidates[0]
        if len(subseq_candidates) > 1:
            logger.debug(
                f"Ambiguous Claude subsequence decode for '{name}': "
                f"{[c.name for c in subseq_candidates]}"
            )
            return None

        return None

    def _match_by_basename(self, name: str) -> Optional[Path]:
        """Case-insensitive basename matching.

        Compares the project name against filesystem folder names,
        normalizing dashes, underscores, and spaces.

        Args:
            name: Project name to match.

        Returns:
            Matched project directory Path, or None.
        """
        normalized_name = _normalize_name(name)

        for project_dir in self.discover_filesystem_projects():
            normalized_dir = _normalize_name(project_dir.name)
            if normalized_name == normalized_dir:
                return project_dir

        return None

    def _match_fuzzy(self, name: str) -> Optional[Tuple[Path, float]]:
        """Token-based fuzzy matching with confidence score.

        Uses SequenceMatcher on normalized names to find the best
        fuzzy match above the confidence threshold.

        Args:
            name: Project name to match.

        Returns:
            Tuple of (matched Path, confidence score), or None if no match.
        """
        normalized_name = _normalize_name(name)
        best_match: Optional[Path] = None
        best_score: float = 0.0

        for project_dir in self.discover_filesystem_projects():
            normalized_dir = _normalize_name(project_dir.name)
            score = SequenceMatcher(
                None, normalized_name, normalized_dir
            ).ratio()

            if score > best_score:
                best_score = score
                best_match = project_dir

        if best_match and best_score >= FUZZY_MATCH_THRESHOLD:
            return (best_match, best_score)

        return None

    def detect_docs_chats_dir(self, project_dir: Path) -> str:
        """Find the docs/chats directory inside a project folder.

        Results are cached per project_dir to avoid repeated filesystem scans.

        Args:
            project_dir: Path to the project directory.

        Returns:
            Relative path string to the docs/chats directory.
        """
        resolved = project_dir.resolve()
        if resolved in self._docs_chats_cache:
            return self._docs_chats_cache[resolved]

        result = self._detect_docs_chats_dir_uncached(project_dir)
        self._docs_chats_cache[resolved] = result
        return result

    def _detect_docs_chats_dir_uncached(self, project_dir: Path) -> str:
        """Find the docs/chats directory (uncached implementation).

        Args:
            project_dir: Path to the project directory.

        Returns:
            Relative path string to the docs/chats directory.
        """
        # Check common conventions in priority order
        candidates = [
            'docs/chats',
            'docs/conversations',
            'chats',
        ]

        for candidate in candidates:
            candidate_path = project_dir / candidate
            if candidate_path.is_dir():
                logger.debug(
                    f"Found docs/chats dir: {candidate} in {project_dir.name}"
                )
                return candidate

        # Scan for directories containing chat export markdown files
        detected = self._scan_for_chat_exports(project_dir)
        if detected:
            return detected

        # Default fallback
        return 'docs/chats'

    def _scan_for_chat_exports(
        self, project_dir: Path, max_depth: int = 3, max_files: int = 50
    ) -> Optional[str]:
        """Scan project for directories containing chat export files.

        Uses os.walk with directory pruning to avoid traversing heavy
        directories (node_modules, .git, build outputs, etc.).
        Caps the number of files scanned for performance.

        Args:
            project_dir: Project directory to scan.
            max_depth: Maximum directory depth to scan.
            max_files: Maximum number of markdown files to inspect.

        Returns:
            Relative path to directory with chat exports, or None.
        """
        compiled_patterns = [re.compile(p) for p in CHAT_EXPORT_PATTERNS]
        files_scanned = 0

        # Directories to prune during walk
        prune_dirs = {
            '.git', '.svn', '.hg', '__pycache__', 'node_modules',
            '.venv', 'venv', '.env', '.cache', '.tmp', '.tox',
            'build', 'dist', '.next', '.nuxt', 'target',
            'coverage', 'htmlcov', '.mypy_cache', '.pytest_cache',
        }

        skip_filenames = {'README.md', 'CHANGELOG.md', 'LICENSE.md'}

        for dirpath, dirnames, filenames in os.walk(project_dir):
            current = Path(dirpath)

            # Check depth
            try:
                relative = current.relative_to(project_dir)
                depth = len(relative.parts)
            except ValueError:
                continue

            if depth > max_depth:
                dirnames.clear()  # Stop descending
                continue

            # Prune heavy directories in-place (modifying dirnames
            # prevents os.walk from descending into them)
            dirnames[:] = [
                d for d in dirnames
                if d not in prune_dirs and not d.startswith('.')
            ]

            # Check markdown files in this directory
            for filename in filenames:
                if not filename.endswith('.md'):
                    continue
                if filename in skip_filenames:
                    continue

                if files_scanned >= max_files:
                    logger.debug(
                        f"Scan cap reached ({max_files} files) "
                        f"for {project_dir.name}"
                    )
                    return None
                files_scanned += 1

                md_file = current / filename
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        head = f.read(500)

                    for pattern in compiled_patterns:
                        if pattern.search(head):
                            chat_dir = current.relative_to(project_dir)
                            return str(chat_dir)
                except (OSError, UnicodeDecodeError):
                    continue

        return None

    def match_all_projects(
        self, projects: List[ProjectInfo]
    ) -> List[ProjectMapping]:
        """Match all conversation projects to filesystem folders.

        Args:
            projects: List of ProjectInfo from source discovery.

        Returns:
            List of ProjectMapping results.
        """
        results = []
        for project_info in projects:
            mapping = self.match_project(project_info)
            results.append(mapping)
        return results


def _normalize_name(name: str) -> str:
    """Normalize a project name for comparison.

    Lowercases, replaces separators (dashes, underscores, spaces, dots)
    with a single space, and strips whitespace.

    Args:
        name: Name to normalize.

    Returns:
        Normalized name string.
    """
    normalized = name.lower()
    normalized = re.sub(r'[-_.\s]+', ' ', normalized)
    return normalized.strip()


def _is_subsequence(needle: List[str], haystack: List[str]) -> bool:
    """Check if needle tokens appear as a contiguous subsequence in haystack.

    Args:
        needle: Tokens to find (e.g., ['claude', 'chat', 'manager']).
        haystack: Tokens to search in (e.g., ['users', 'mike', 'src', 'claude', 'chat', 'manager']).

    Returns:
        True if needle appears as contiguous subsequence in haystack.
    """
    if not needle:
        return False
    if len(needle) > len(haystack):
        return False

    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i:i + len(needle)] == needle:
            return True

    return False

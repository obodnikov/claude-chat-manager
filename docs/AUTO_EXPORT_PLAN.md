# Auto-Export Implementation Plan

## 1. Overview

### Problem Statement

Exporting chats from all sources (Claude Desktop, Kiro IDE, Codex CLI) and placing them into the correct project's `docs/chats/` folder is a tedious multi-step manual process:

1. Run `claude-chat-manager.py "project" -f book -o tmp/` for each project
2. Run `merge-chats.py --source tmp/ --target ~/src/project/docs/chats/ --auto` for each project
3. Repeat for every project × every source

This feature automates the entire pipeline with a single command.

### Solution

A standalone script `auto-export.py` that:

1. Discovers all conversations across all sources (claude, kiro, codex)
2. Discovers all project directories under a user-provided root (e.g., `~/src`)
3. Smartly maps conversation projects → filesystem folders
4. Exports conversations to a temporary directory
5. Merges exported files into each project's `docs/chats/` folder using existing ChatMerger
6. Reports results

### Design Principles

- **Maximum reuse**: No new export/merge/parse logic. All heavy lifting done by existing `src/` modules
- **Standalone script**: `auto-export.py` at project root, imports from `src/`, same pattern as `merge-chats.py`
- **Learn-then-run**: A `--learn` mode builds project mappings interactively before any export happens
- **Safe by default**: `--dry-run` shows what would happen without making changes
- **Config-driven**: Mappings saved to JSON config so subsequent runs are fast and predictable

### Architecture Fit

```
auto-export.py                    # CLI entry point (like merge-chats.py)
    │
    ├── src/project_matcher.py    # NEW: Project matching + config management
    └── src/auto_exporter.py      # NEW: Pipeline orchestrator
         │
         ├── src/projects.py          # EXISTING: list_all_projects()
         ├── src/kiro_projects.py     # EXISTING: discover_kiro_workspaces()
         ├── src/codex_projects.py    # EXISTING: discover_codex_workspaces()
         ├── src/exporters.py         # EXISTING: export_project_chats()
         ├── src/chat_merger.py       # EXISTING: ChatMerger
         ├── src/config.py            # EXISTING: all export settings
         ├── src/models.py            # EXISTING: ProjectInfo, ChatSource
         └── src/formatters.py        # EXISTING: clean_project_name()
```

---

## 2. Mapping Config File

### Location

Default: `~/.config/claude-chat-manager/project-mapping.json`

Override via `--config` flag or `AUTO_EXPORT_CONFIG` env var.

### Schema

```json
{
  "version": "1.0",
  "root_directory": "~/src",
  "defaults": {
    "export_format": "book",
    "unmatched_action": "skip"
  },
  "mappings": {
    "Users-Mike-Src-Claude-Chat-Manager": {
      "target": "claude-chat-manager",
      "docs_chats_path": "docs/chats",
      "confirmed": true
    },
    "random-experiment": {
      "action": "skip"
    },
    "old-project": {
      "target": "renamed-project",
      "docs_chats_path": "docs/chats",
      "confirmed": true
    },
    "personal-notes": {
      "target": "_unmatched/personal-notes",
      "docs_chats_path": ".",
      "confirmed": true
    }
  },
  "last_learned": "2026-04-23T12:00:00"
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Config schema version |
| `root_directory` | string | Root directory for project lookup |
| `defaults.export_format` | string | Export format: `book` (default), `markdown` |
| `defaults.unmatched_action` | string | What to do with unmatched projects: `skip` or folder name under root |
| `mappings` | object | Key = conversation project name (as discovered by sources) |
| `mappings.*.target` | string | Folder name relative to root_directory |
| `mappings.*.docs_chats_path` | string | Path to docs/chats inside the target folder (relative) |
| `mappings.*.action` | string | `skip` to ignore this project entirely |
| `mappings.*.confirmed` | bool | Whether user confirmed this mapping in learn mode |
| `last_learned` | string | ISO timestamp of last learn run |

### Mapping Resolution Rules

When multiple conversation projects (from different sources) point to the same filesystem folder, they share the target. For example:

- Claude project `Users-Mike-Src-Claude-Chat-Manager` → `claude-chat-manager`
- Kiro workspace `claude-chat-manager` (workspace_path: `/Users/mike/src/claude-chat-manager`) → `claude-chat-manager`
- Codex project `claude-chat-manager` (cwd: `/Users/mike/src/claude-chat-manager`) → `claude-chat-manager`

All three merge into `~/src/claude-chat-manager/docs/chats/`.

---

## 3. Project Matching Strategy

### Priority Order (highest to lowest)

1. **Config lookup** — Already in mapping config? Use it directly
2. **Exact path match** — Kiro `workspace_path` or Codex `cwd` resolves to a folder under root
3. **Claude path decode** — Decode `Users-Mike-Src-Project` → `/Users/Mike/Src/Project` → match against root dirs
4. **Basename exact match** — Case-insensitive folder name comparison
5. **Fuzzy match** — Token-based similarity (split on `-`, `_`, case boundaries), threshold ≥ 0.8
6. **Unresolved** — In learn mode: ask user. Otherwise: apply `defaults.unmatched_action`

### Claude Project Name Decoding

Claude Desktop encodes project paths as directory names with `-` separators:
- `Users-Mike-Src-Claude-Chat-Manager` → path segments `Users/Mike/Src/Claude-Chat-Manager`
- Match against root subdirectories by comparing the tail segments

Algorithm:
1. Split project name by `-` to get tokens
2. For each root subdirectory, split its path into segments
3. Try to match the last N segments of the decoded path against root subdirectory paths
4. Score by number of matching segments

### Docs/Chats Directory Detection

Given a matched project folder, find where chat exports should go:

1. Check `docs/chats/` — most common convention
2. Check `docs/conversations/`
3. Check `chats/`
4. Scan for any directory containing `.md` files with chat export fingerprints
   (look for patterns like `👤 **USER:**`, `🤖 **ASSISTANT:**`, or book format headers)
5. If nothing found — default to `docs/chats/` (will be created on first export)

In learn mode, show the detected path and let user confirm or override.

---

## 4. CLI Interface

### Commands

```bash
# Learn mode — build/update mapping config interactively
python auto-export.py --root ~/src --learn

# Re-learn — update mappings (keeps existing confirmed mappings, adds new projects)
python auto-export.py --root ~/src --learn --update

# Dry run — show what would happen without making changes
python auto-export.py --root ~/src --dry-run

# Execute — run the full export+merge pipeline
python auto-export.py --root ~/src

# Filter by source
python auto-export.py --root ~/src --source kiro

# Custom config
python auto-export.py --root ~/src --config ./my-mapping.json

# Keep temporary export files (default: clean up after merge)
python auto-export.py --root ~/src --keep-tmp

# Verbose logging
python auto-export.py --root ~/src -v
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--root` | Yes | — | Root directory containing project folders |
| `--learn` | No | — | Interactive mode: build/update mapping config |
| `--update` | No | — | With `--learn`: keep existing confirmed mappings |
| `--dry-run` | No | — | Preview mode: show plan without executing |
| `--source` | No | `all` | Filter: `claude`, `kiro`, `codex`, or `all` |
| `--config` | No | `~/.config/claude-chat-manager/project-mapping.json` | Path to mapping config |
| `--keep-tmp` | No | — | Don't clean up temporary export directory |
| `--format` | No | `book` | Export format: `book` or `markdown` |
| `-v` / `--verbose` | No | — | Enable debug logging |

---

## 5. Pipeline Flow

### Full Pipeline (Execute Mode)

```
1. Load mapping config
   └── If not found → error: "Run --learn first"

2. Discover all conversation projects (all sources)
   └── Uses: src/projects.py → list_all_projects()

3. For each conversation project:
   a. Look up mapping config
   b. Skip if action == "skip"
   c. Resolve target directory (root + target + docs_chats_path)
   d. Export chats to tmp/<project-name>/
      └── Uses: src/exporters.py → export_project_chats()
   e. Merge tmp/<project-name>/ → target docs/chats/
      └── Uses: src/chat_merger.py → ChatMerger.analyze_directories() + auto merge
   f. Record results

4. Print summary report

5. Clean up tmp/ (unless --keep-tmp)
```

### Learn Mode Flow

```
1. Discover all conversation projects (all sources)
   └── Uses: src/projects.py → list_all_projects()

2. Scan root directory for project folders
   └── List immediate subdirectories of --root

3. Load existing config (if --update, preserve confirmed mappings)

4. For each conversation project:
   a. If --update and already confirmed → skip
   b. Run matching strategy (Section 3)
   c. If match found with high confidence:
      - Show: "claude-chat-manager [Claude] → ~/src/claude-chat-manager/docs/chats/"
      - Ask: "Confirm? (y/n/custom path/skip)"
   d. If no match or low confidence:
      - Show: "random-experiment [Claude] → ??? (no match found)"
      - Ask: "Enter folder name, 'skip', or press Enter to use _unmatched/"
   e. Detect docs/chats path in matched folder
   f. Save to config

5. Write config file

6. Print summary of all mappings
```

### Dry Run Flow

```
1. Load mapping config
2. Discover all conversation projects
3. For each mapped project:
   a. Count chats to export
   b. Count existing files in target
   c. Run ChatMerger.analyze_directories() on a hypothetical basis
      (or just count source vs target files for estimation)
   d. Show: project name, source, chat count, target path, estimated new/update/skip
4. Print summary totals
```

---

## 6. Implementation Phases

### Phase 1: Project Matcher + Mapping Config

**Goal:** Build the matching engine and config management. Testable independently.

**New files:**
- `src/project_matcher.py` (~250 lines)
- `tests/test_project_matcher.py`

**What to implement:**

```python
# src/project_matcher.py

@dataclass
class ProjectMapping:
    """Single project mapping entry."""
    source_name: str          # Conversation project name
    target: Optional[str]     # Folder name relative to root, or None
    docs_chats_path: str      # Relative path to docs/chats inside target
    action: str               # "export" or "skip"
    confirmed: bool           # User-confirmed in learn mode
    match_method: str         # How it was matched (for debugging)
    source_type: ChatSource   # Which source this came from
    workspace_path: Optional[str]  # Original workspace path (Kiro/Codex)

class MappingConfig:
    """Manages project mapping configuration file."""
    
    def __init__(self, config_path: Path):
        ...
    
    def load(self) -> dict:
        """Load config from JSON file."""
        ...
    
    def save(self, config: dict) -> None:
        """Save config to JSON file."""
        ...
    
    def get_mapping(self, project_name: str) -> Optional[ProjectMapping]:
        """Look up mapping for a project name."""
        ...
    
    def set_mapping(self, project_name: str, mapping: ProjectMapping) -> None:
        """Set/update mapping for a project name."""
        ...

class ProjectMatcher:
    """Smart project name → filesystem folder matching."""
    
    def __init__(self, root_dir: Path, config: MappingConfig):
        ...
    
    def discover_filesystem_projects(self) -> List[Path]:
        """Scan root directory for project folders."""
        ...
    
    def match_project(self, project_info: ProjectInfo) -> Optional[ProjectMapping]:
        """Match a conversation project to a filesystem folder."""
        ...
    
    def _match_by_workspace_path(self, project_info: ProjectInfo) -> Optional[Path]:
        """Match Kiro/Codex projects by their workspace_path/cwd."""
        ...
    
    def _decode_claude_project_name(self, name: str) -> Optional[Path]:
        """Decode Claude Desktop encoded project name to path."""
        ...
    
    def _match_by_basename(self, name: str) -> Optional[Path]:
        """Case-insensitive basename matching."""
        ...
    
    def _match_fuzzy(self, name: str) -> Optional[Tuple[Path, float]]:
        """Token-based fuzzy matching with confidence score."""
        ...
    
    def detect_docs_chats_dir(self, project_dir: Path) -> str:
        """Find docs/chats directory inside a project folder."""
        ...
```

**Reuses:**
- `src/models.py` → `ProjectInfo`, `ChatSource`
- `src/formatters.py` → `clean_project_name()`
- `src/config.py` → `config` (for source directories)

**Testing focus:**
- Claude name decoding: `Users-Mike-Src-Project` → path matching
- Kiro/Codex workspace_path matching
- Basename matching (case-insensitive)
- Fuzzy matching with confidence thresholds
- Config load/save/lookup
- Docs/chats directory detection heuristics
- Edge cases: empty root, no matches, duplicate targets

---

### Phase 2: Learn Mode CLI

**Goal:** Interactive mapping builder. User can run `--learn` and get a config file ready.

**New files:**
- `auto-export.py` (~150 lines, learn mode only — export mode added in Phase 3)

**What to implement:**

```python
# auto-export.py (Phase 2 — learn mode only)

def learn_mode(root_dir: Path, config_path: Path, update: bool = False) -> None:
    """Interactive mapping builder.
    
    1. Discover all conversation projects from all sources
    2. Scan root directory for filesystem projects
    3. For each conversation project:
       - Run matching strategy
       - Show match result to user
       - Ask for confirmation/correction
       - Save to config
    """
    ...

def print_learn_summary(config: MappingConfig) -> None:
    """Print summary of all mappings after learn mode."""
    ...

def main() -> int:
    """CLI entry point with argparse."""
    ...
```

**Interactive prompts example:**

```
🔍 Learning project mappings...

Root directory: ~/src (15 project folders found)
Conversation projects: 8 (Claude: 4, Kiro: 3, Codex: 1)

[1/8] claude-chat-manager [Claude]
  Auto-matched: ~/src/claude-chat-manager/ (path decode, high confidence)
  Docs target:  ~/src/claude-chat-manager/docs/chats/ (found, 16 files)
  → Confirm? [Y/n/custom/skip]: y
  ✅ Confirmed

[2/8] claude-chat-manager [Kiro]
  Auto-matched: ~/src/claude-chat-manager/ (workspace path exact match)
  → Same target as [1/8]. Confirm? [Y/n]: y
  ✅ Confirmed (merged with existing mapping)

[3/8] my-side-project [Codex]
  Auto-matched: ~/src/my-side-project/ (basename match)
  Docs target:  ~/src/my-side-project/docs/chats/ (not found, will create)
  → Confirm? [Y/n/custom/skip]: y
  ✅ Confirmed

[4/8] random-experiment [Claude]
  ⚠️  No match found in ~/src/
  → Enter folder name, 'skip', or press Enter for _unmatched/:
  > skip
  ⏭️  Skipped

...

📋 Mapping Summary
═══════════════════════════════════════════
  ✅ Mapped:  6 projects → 4 folders
  ⏭️  Skipped: 2 projects
  Config saved: ~/.config/claude-chat-manager/project-mapping.json
```

**Reuses:**
- `src/projects.py` → `list_all_projects()`
- `src/project_matcher.py` → `ProjectMatcher`, `MappingConfig` (from Phase 1)

**Testing focus:**
- Learn mode with mocked input (confirm, skip, custom path)
- Update mode preserving existing confirmed mappings
- Config file creation and update
- Multiple sources mapping to same target

---

### Phase 3: Auto-Export Pipeline

**Goal:** The actual export + merge orchestrator.

**New files:**
- `src/auto_exporter.py` (~350 lines)
- `tests/test_auto_exporter.py`

**Update:**
- `auto-export.py` — add execute mode and dry-run mode

**What to implement:**

```python
# src/auto_exporter.py

@dataclass
class ExportResult:
    """Result of exporting and merging one project."""
    project_name: str
    source: ChatSource
    target_dir: Path
    chats_exported: int
    new_files: int
    updated_files: int
    skipped_files: int
    errors: List[str]

class AutoExporter:
    """Orchestrates the full auto-export pipeline."""
    
    def __init__(
        self,
        root_dir: Path,
        mapping_config: MappingConfig,
        source_filter: Optional[ChatSource] = None,
        export_format: str = 'book',
        dry_run: bool = False,
        keep_tmp: bool = False
    ):
        ...
    
    def run(self) -> List[ExportResult]:
        """Execute the full pipeline.
        
        1. Load mappings
        2. Discover conversation projects
        3. Group by target (multiple sources → same folder)
        4. For each target:
           a. Export all source projects to tmp/
           b. Merge tmp/ → target docs/chats/
           c. Record results
        5. Clean up tmp
        6. Return results
        """
        ...
    
    def dry_run_report(self) -> None:
        """Show what would happen without executing."""
        ...
    
    def _export_project(
        self,
        project_info: ProjectInfo,
        tmp_dir: Path
    ) -> List[Path]:
        """Export a single project's chats to tmp directory.
        
        Uses: src/exporters.py → export_project_chats()
        """
        ...
    
    def _merge_to_target(
        self,
        source_dir: Path,
        target_dir: Path
    ) -> Tuple[int, int, int]:
        """Merge exported files into target directory.
        
        Uses: src/chat_merger.py → ChatMerger
        Returns: (new_count, update_count, skip_count)
        """
        ...
    
    def _group_projects_by_target(
        self,
        projects: List[ProjectInfo],
        mappings: MappingConfig
    ) -> Dict[Path, List[ProjectInfo]]:
        """Group conversation projects that map to the same target folder."""
        ...

def print_results(results: List[ExportResult]) -> None:
    """Print formatted summary of export results."""
    ...
```

**Pipeline detail — grouping by target:**

Multiple sources may map to the same folder. The pipeline groups them:

```
Target: ~/src/claude-chat-manager/docs/chats/
  Sources:
    - [Claude] Users-Mike-Src-Claude-Chat-Manager (12 chats)
    - [Kiro] claude-chat-manager (5 chats)
    - [Codex] claude-chat-manager (3 chats)
  
  Step 1: Export all 20 chats to tmp/claude-chat-manager/
  Step 2: Merge tmp/claude-chat-manager/ → ~/src/claude-chat-manager/docs/chats/
  Result: 4 new, 1 updated, 15 skipped
```

**Reuses:**
- `src/projects.py` → `list_all_projects()`, `get_project_chat_files()`
- `src/exporters.py` → `export_project_chats()`
- `src/chat_merger.py` → `ChatMerger`, `MergeAction`
- `src/config.py` → export settings (book format, sanitization, etc.)
- `src/models.py` → `ProjectInfo`, `ChatSource`
- `src/project_matcher.py` → `MappingConfig`, `ProjectMapping` (from Phase 1)

**Testing focus:**
- Full pipeline with mocked filesystem and sources
- Grouping multiple sources to same target
- Tmp directory creation and cleanup
- Error handling (export failure, merge failure, permission errors)
- Dry run output accuracy
- Empty projects, no mappings, all skipped

---

### Phase 4: Documentation + Architecture Update

**Goal:** Complete documentation and update existing docs.

**New files:**
- `docs/AUTO_EXPORT.md` — user guide

**Updated files:**
- `docs/ARCHITECTURE.md` — add auto-export components to architecture diagram, repository structure, component descriptions, and stability zones
- `README.md` — add auto-export section with quick-start examples
- `.env.example` — add `AUTO_EXPORT_CONFIG` if needed

**`docs/AUTO_EXPORT.md` outline:**

```markdown
# Auto-Export Guide

## Quick Start
## Prerequisites  
## Learn Mode (First Time Setup)
## Running Auto-Export
## Dry Run
## Configuration File
  ### Location
  ### Schema Reference
  ### Manual Editing
## Matching Strategy
  ### How Projects Are Matched
  ### Claude Desktop Name Decoding
  ### Handling Multiple Sources
## Troubleshooting
  ### Common Issues
  ### Re-learning Mappings
## Examples
  ### First Time Setup
  ### Regular Usage
  ### Adding New Projects
  ### Changing Target Directories
```

---

## 7. Dependency Map

Shows what each phase depends on and what it produces:

```
Phase 1: Project Matcher
  Depends on: src/models.py, src/formatters.py, src/config.py
  Produces:   src/project_matcher.py (ProjectMatcher, MappingConfig)
  Testable:   Yes, independently

Phase 2: Learn Mode CLI
  Depends on: Phase 1, src/projects.py, src/kiro_projects.py, src/codex_projects.py
  Produces:   auto-export.py (learn mode), mapping config file
  Testable:   Yes, produces config file that can be inspected

Phase 3: Auto-Export Pipeline
  Depends on: Phase 1, Phase 2 (config file), src/exporters.py, src/chat_merger.py
  Produces:   src/auto_exporter.py, auto-export.py (full), exported+merged files
  Testable:   Yes, with mocked filesystem

Phase 4: Documentation
  Depends on: Phases 1-3 complete
  Produces:   docs/AUTO_EXPORT.md, updated ARCHITECTURE.md, README.md
  Testable:   N/A (documentation review)
```

---

## 8. File Inventory

### New Files

| File | Phase | Lines (est.) | Purpose |
|------|-------|-------------|---------|
| `src/project_matcher.py` | 1 | ~250 | Matching engine + config management |
| `tests/test_project_matcher.py` | 1 | ~300 | Matcher unit tests |
| `auto-export.py` | 2-3 | ~250 | CLI entry point |
| `src/auto_exporter.py` | 3 | ~350 | Pipeline orchestrator |
| `tests/test_auto_exporter.py` | 3 | ~250 | Pipeline tests |
| `docs/AUTO_EXPORT.md` | 4 | ~200 | User guide |

### Modified Files

| File | Phase | Changes |
|------|-------|---------|
| `docs/ARCHITECTURE.md` | 4 | Add auto-export components |
| `README.md` | 4 | Add auto-export section |
| `.env.example` | 4 | Add AUTO_EXPORT_CONFIG (if needed) |

### Existing Files Reused (No Changes)

| File | Used By | Functions Used |
|------|---------|---------------|
| `src/projects.py` | Phase 2, 3 | `list_all_projects()`, `get_project_chat_files()` |
| `src/kiro_projects.py` | Phase 1 | `discover_kiro_workspaces()` (via projects.py) |
| `src/codex_projects.py` | Phase 1 | `discover_codex_workspaces()` (via projects.py) |
| `src/exporters.py` | Phase 3 | `export_project_chats()` |
| `src/chat_merger.py` | Phase 3 | `ChatMerger`, `MergeAction`, `MergeDecision` |
| `src/config.py` | All | `config` singleton (export settings) |
| `src/models.py` | All | `ProjectInfo`, `ChatSource` |
| `src/formatters.py` | Phase 1 | `clean_project_name()` |
| `src/exceptions.py` | All | Custom exception classes |
| `src/colors.py` | Phase 2, 3 | Terminal colors |

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude name decoding ambiguity | Wrong project match | Learn mode confirmation; config overrides |
| Multiple sources → same target race condition | Duplicate exports in tmp | Group by target before exporting; merge all at once |
| Large projects slow export | Long runtime | Progress indicators; per-project status |
| Existing docs/chats has non-chat .md files | Merge confusion | ChatMerger fingerprinting already handles this |
| Config file corruption | Lost mappings | JSON validation on load; backup before write |
| Permission errors on target dirs | Failed merge | Catch and report per-project; continue with others |
| Tmp directory not cleaned on crash | Disk space waste | Use tempfile module; document manual cleanup |

---

## 10. Implementation Notes for AI Assistants

### Before Starting Any Phase

1. Read `CLAUDE.md` and `AI.md` for coding rules
2. Read `docs/ARCHITECTURE.md` for system context
3. Read this plan document for feature context
4. Propose solution approach before coding

### Coding Standards (from AI.md)

- PEP8 style, type hints on all functions
- Google-style docstrings
- Custom exceptions (not raw Exception)
- Logging module (not print) for internal messages
- Print only for user-facing CLI output
- Modules under 800 lines
- Tests with pytest

### Key Patterns to Follow

- **CLI pattern**: See `merge-chats.py` for standalone script structure
- **Config pattern**: See `src/config.py` for environment variable handling
- **Discovery pattern**: See `src/projects.py` → `list_all_projects()` for multi-source discovery
- **Export pattern**: See `src/exporters.py` → `export_project_chats()` for batch export
- **Merge pattern**: See `src/chat_merger.py` → `ChatMerger` for intelligent merging
- **Color output**: See `merge-chats.py` for terminal color usage in CLI scripts

### Testing Patterns

- Mock filesystem with `tmp_path` fixture
- Mock `list_all_projects()` to return controlled ProjectInfo objects
- Mock `export_project_chats()` to create known files
- Test matching strategies independently with various project name formats
- Test config load/save round-trip

---

**Document Version:** 1.0
**Created:** 2026-04-23
**Status:** Approved for implementation

# Pi Coding Agent Chat Source — Implementation Guide

## 1. Overview

This document describes how the **pi coding agent** is integrated into
claude-chat-manager as a chat source, alongside Claude Desktop, Kiro IDE,
OpenAI Codex CLI, and the Cline VS Code extension.

**Goal:** Full feature parity with the other sources — project discovery,
interactive browsing, all export formats (pretty, markdown, book, wiki),
source filtering via `--source pi`, and the auto-export pipeline, with tests.

**Branch:** `feat/pi`

**Design reference:** [docs/design/pi-coding-agent-support.md](design/pi-coding-agent-support.md)
(this guide documents **Feature A — Pi source**; Feature B, the optional wingman
title sync, is tracked separately).

**Closest analog:** **Codex CLI** — both store JSONL with a metadata header line
followed by message lines, and both group sessions into projects by `cwd`. The
pi implementation mirrors `codex_parser.py` / `codex_projects.py` end-to-end.

---

## 2. What is the Pi Coding Agent?

Pi is a terminal-based coding agent installed as `@earendil-works/pi-coding-agent`
(verified against **v0.80.2**).

- **Home directory:** `~/.pi/agent/` (override via `PI_DATA_DIR`)
- **Session format:** JSONL session files under `<data_dir>/sessions/`

---

## 3. Pi Data Storage Structure

```
~/.pi/agent/
└── sessions/
    ├── --<path-with-slashes-as-dashes>--/
    │   └── <timestamp>_<uuid>.jsonl       # one file per session
    └── .wingman-titles.json               # sidecar (owned by sqowe-wingman)
```

**Key observations:**
- The directory slug encodes the working directory, but we do **not** parse it —
  `cwd` is read from the session header (more robust).
- Sessions sharing the same `cwd` belong to the same logical "project".
- `.wingman-titles.json` is **not** a session file. The `*.jsonl` discovery glob
  excludes it naturally (wrong extension), and discovery never treats any sidecar
  as a session.

---

## 4. Pi JSONL Session Format

Each session file is JSONL (one JSON object per line).

### 4.1 Session header (line 1)

```json
{"type":"session","version":3,"id":"019ef0c5-fdf8-7626-ad4d-da7ee350c408",
 "timestamp":"2026-06-22T19:19:27.993Z","cwd":"/Users/eobomik/src/sqowe-wingman"}
```

**Fields extracted:**
- `id` — session uuid (stored as `execution_id` on each `ChatMessage`)
- `cwd` — working directory (project grouping key)
- `timestamp` — session start time (ISO-8601)
- `version` — pi session format version (1/2/3; tolerated, defaults to 1 if absent/invalid)

### 4.2 Message entries

```json
{"type":"message","id":"6fd99a80","parentId":"d1819595",
 "timestamp":"2026-06-27T13:17:02.847Z",
 "message":{"role":"user","content":[{"type":"text","text":"…"}]}}
```

Entries carry `id`/`parentId` forming a tree. We read `type:"message"` entries in
**file order** (the main append path) and ignore branching — pragmatic parity with
Codex/Cline; full tree-walk is out of scope.

### 4.3 Roles and content shapes

- **Roles kept:** `user`, `assistant`. All other roles (`toolResult`,
  `bashExecution`, `custom`, `branchSummary`, `compactionSummary`) are skipped.
- **Other entry types skipped:** `model_change`, `thinking_level_change`,
  `compaction`, `branch_summary`, `custom`, `custom_message`, `label`,
  `session_info`.
- **Content** is either a bare **string** or a list of typed blocks:
  - `{type:"text",text}` — kept
  - `{type:"thinking",…}`, `{type:"toolCall",…}`, `{type:"image",…}` — dropped

---

## 5. Normalization Rules (`normalize_pi_content`)

- `str` → returned as-is.
- `list` → join the `text` of every `type:"text"` block with `\n`; drop
  `thinking`/`toolCall`/`image` blocks.
- Anything else → `str(content)` if truthy, else `""`.
- A message that is **empty after normalization** (e.g. image-only) is skipped
  by `extract_pi_messages`.

---

## 6. Modules

### 6.1 `src/pi_parser.py`

| Symbol | Purpose |
| --- | --- |
| `PiSession` (dataclass) | `session_id`, `cwd`, `timestamp`, `version`, `messages`, `file_path` |
| `parse_pi_session_meta(path)` | Read **only** line 1; assert `type=="session"`; return header dict. Tolerates leading blank lines/BOM. Raises `ChatFileNotFoundError` / `InvalidChatFileError`. |
| `parse_pi_session_file(path)` | Stream the file → `PiSession`. Captures header, collects `user`/`assistant` message entries, skips malformed lines (log + continue). |
| `normalize_pi_content(content)` | See §5. |
| `extract_pi_messages(session)` | → `List[ChatMessage]` with `source=ChatSource.PI`, `execution_id=session.session_id`; drops empties. |

### 6.2 `src/pi_projects.py`

| Symbol | Purpose |
| --- | --- |
| `PiSessionInfo` (dataclass) | Lightweight discovery record: `session_id`, `file_path`, `cwd`, `timestamp` |
| `PiWorkspace` (dataclass) | One per unique `cwd`: `workspace_path`, `workspace_name`, `sessions`, `session_count`, `last_modified`, `pi_data_dir` |
| `discover_pi_workspaces(pi_data_dir, use_cache=True)` | `rglob("*.jsonl")` under `<dir>/sessions/`; read header per file; group by `cwd`; `last_modified` from newest header timestamp; sort newest-first. **Process-scoped cache** keyed by resolved `pi_data_dir`. |
| `clear_pi_workspace_cache()` | Invalidate the discovery cache (tests / long-running processes). |
| `get_pi_session_files(workspace)` | Existing session file paths, sorted by mtime desc. |

**Discovery cache.** `discover_pi_workspaces` caches results per resolved
`pi_data_dir` for the process lifetime, avoiding a redundant full rglob on repeat
calls within one CLI invocation. Pass `use_cache=False` or call
`clear_pi_workspace_cache()` to force a fresh scan.

**Robustness.** A `_safe_mtime` helper returns `0.0` on `OSError` so a single
unreadable/deleted file never aborts a sort; sessions whose header lacks `cwd`
fall back to their parent directory name so they stay discoverable.

---

## 7. Wiring Touchpoints (file-by-file)

| File | Change |
| --- | --- |
| `src/models.py` | `ChatSource.PI = "pi"` |
| `src/config.py` | `_pi_dir` (from `PI_DATA_DIR` else `~/.pi/agent`); `pi_data_dir` property; `validate_pi_directory()` (dir exists + `sessions/` subdir exists) |
| `src/cli_utils.py` | `'pi'` added to `SOURCE_CHOICES`; `parse_source_filter` maps `'pi' → ChatSource.PI` |
| `src/projects.py` | `_pi_workspace_to_project_info()`; `scan_pi`/`search_pi` blocks in `list_all_projects()` + `find_project_by_name()`; `PI` branch in `get_project_chat_files()` (absolute session paths via `session_ids`) |
| `src/parser.py` | `count_pi_messages_in_file()` (counts `type:"message"` lines with role user/assistant) |
| `src/exporters.py` | `_detect_chat_source()` PI branch; `_convert_pi_to_dict()`; PI branch in `_load_chat_data()` |
| `src/cli.py` | `_source_label()` → `"[Pi]    "`; `_source_icon()` → `"🥧 Pi"`; `_detect_available_sources()`; list/count/title dispatch branches |
| `src/auto_exporter.py` | `ChatSource.PI: "Pi"` in `SOURCE_LABELS` |
| `claude-chat-manager.py` | `--source pi` examples in help epilog |
| `.env.example` | document `PI_DATA_DIR` |

### 7.1 `_detect_chat_source` disambiguation

In the `.jsonl` branch, the first-line `type` distinguishes the three JSONL
sources. The pi check runs **first** and additionally requires at least one pi
header field (`id`/`version`/`cwd`/`timestamp`) to avoid false-positives:

| First-line `type` | Source |
| --- | --- |
| `"session"` (+ a pi header field) | **Pi** |
| `"session_meta"` | Codex |
| `"message"` / other | Claude Desktop |

### 7.2 ProjectInfo mapping (`_pi_workspace_to_project_info`)

- `source = ChatSource.PI`
- `path = Path(workspace.workspace_path)` — the real project dir (for display)
- `workspace_path = workspace.workspace_path` — used by auto-export matching
- `session_ids = [str(s.file_path) …]` — **absolute** session paths, resolved by
  `get_project_chat_files()` (same pattern as Codex)

---

## 8. Configuration

- **`PI_DATA_DIR`** — pi data directory. Default `~/.pi/agent`. Sessions read from
  `<PI_DATA_DIR>/sessions/`.
- `config.validate_pi_directory()` returns `True` only when the data dir exists,
  is a directory, and contains a `sessions/` subdirectory.

---

## 9. Tests

| File | Coverage |
| --- | --- |
| `tests/test_pi_parser.py` | header parse (id/cwd/version/timestamp); rejects non-`session` first line; `normalize_pi_content` (bare string, text blocks, mixed text+thinking+toolCall, image-only → empty); `parse_pi_session_file` keeps user+assistant, skips lifecycle entries, tolerates a malformed line; `extract_pi_messages` sets `source=PI` + `execution_id`, drops empties |
| `tests/test_pi_projects.py` | discovery groups by cwd; `last_modified` = newest header; sorted newest-first; ignores non-session files; empty/absent dir → `[]` |
| `tests/test_cli_source_flag.py` | `--source pi` parses to `ChatSource.PI`; invalid values stay rejected |
| `tests/test_models.py` | `ChatSource.PI` enum value |

Run: `venv/bin/python -m pytest`, then `mypy` and `black` per
[docs/DEVELOPMENT.md](DEVELOPMENT.md).

---

## 10. AI.md / ARCHITECTURE Compliance

- New modules use type hints + Google-style docstrings; PEP8; reuse the
  `exceptions.py` hierarchy; use `logging` (no `print`); no hardcoded paths
  (all via `config`).
- Changes to the Stable zones (`models.py`, `config.py`, `parser.py`,
  `projects.py`) are additive only, per ARCHITECTURE §7.
- See ARCHITECTURE §4.2.4 for the data-layer summary.

---

## 11. Out of Scope (Feature A)

- Tree/branch-aware export (currently file-order linear, matching Codex/Cline).
- **Feature B** — wingman title sync (`.wingman-titles.json`). Optional, off by
  default; depends on Feature A. See the design doc.

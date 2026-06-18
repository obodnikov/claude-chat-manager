# Cline (VS Code extension) Chat Source — Implementation Guide

## 1. Overview

This document is the implementation guide for the **Cline VS Code extension**
chat source in claude-chat-manager, alongside Claude Desktop, Kiro IDE, and
Codex CLI.

Cline ships in two hosts that store data **differently**, so the project treats
them as **two distinct sources**:

| Source | Enum | Storage | Container | Guide |
|--------|------|---------|-----------|-------|
| Cline VS Code extension | `ChatSource.CLINE_VSCODE` (`"cline-vscode"`) | `globalStorage/saoudrizwan.claude-dev/` | per-task JSON files | **this doc** |
| Cline CLI | `ChatSource.CLINE_CLI` (`"cline-cli"`) | `~/.cline/data/` | SQLite session DB | [CLINE_CLI_IMPLEMENTATION.md](CLINE_CLI_IMPLEMENTATION.md) |

The two hosts share an **identical message schema** (`say`/`ask`/`text`/`ts`),
so the schema logic lives in a shared module, `src/cline_messages.py`, reused by
both source adapters. Only the discovery + storage layers differ.

### Design decisions (approved)

1. **Conversation source = `ui_messages.json` primary, `api_conversation_history.json` fallback.** If `ui_messages.json` is missing, unreadable, or yields zero conversation messages, fall back to the raw Anthropic-API transcript (heavier stripping).
2. **Editor scope = stable VS Code only**, overridable via `CLINE_VSCODE_DATA_DIR`. To read a VS Code fork (Cursor / Windsurf / VSCodium / Insiders), point that env var at the fork's `globalStorage/saoudrizwan.claude-dev` directory.
3. **Two sources, shared schema.** `cline-vscode` and `cline-cli` are separate `ChatSource` values and `--source` values; `cline_messages.py` holds the host-agnostic logic. `cline` is accepted as a back-compat alias for `cline-vscode` (and becomes an umbrella for both once the CLI source lands).

---

## 2. Implementation Status

| Step | Area | Status |
|------|------|--------|
| 1 | `ChatSource.CLINE_VSCODE` enum (+ `test_models`) | ✅ Done |
| 2 | `src/cline_messages.py` (shared schema) | ✅ Done |
| 2 | `src/cline_vscode_parser.py` (+ unit tests) | ✅ Done |
| 3 | `src/cline_vscode_projects.py` (+ unit tests) | ✅ Done |
| 4 | `src/config.py` (`CLINE_VSCODE_DATA_DIR`, validation, filter; + `TestClineConfig`) | ✅ Done |
| 5 | `src/projects.py` wiring (+ unit tests) | ⏳ TODO |
| 6 | `src/exporters.py` wiring (+ unit tests) | ⏳ TODO |
| 7 | `claude-chat-manager.py` `--source` flag (+ unit tests) | ⏳ TODO |
| 8 | `.env.example` | ⏳ TODO |
| E2E | Integration / end-to-end tests | ⏳ TODO |
| 12 | README.md + ARCHITECTURE.md | ⏳ TODO |

Each step ships its own unit tests in the same commit (see the testing convention
in §6). Steps 1–4 + their tests landed in commit `feat(cline): add VS Code parser,
discovery, and config (steps 1+4)`.

---

## 3. Storage Structure (VS Code extension)

**Base path by OS** (extension id `saoudrizwan.claude-dev`):

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/` |
| Windows | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\` |
| Linux | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/` |

```
saoudrizwan.claude-dev/
├── state/
│   └── taskHistory.json              # Index of ALL tasks (array) — discovery reads this
├── tasks/
│   └── <task-id>/                    # epoch-ms id; one dir per task = one chat
│       ├── ui_messages.json          # PRIMARY conversation source
│       ├── api_conversation_history.json  # FALLBACK transcript
│       └── task_metadata.json        # files-in-context, model usage, environment
└── checkpoints/                      # (ignore)
```

A **task** = one conversation = one exported `.md`. Tasks are grouped into
"projects" by `cwdOnTaskInitialization` from `taskHistory.json` (the analogue of
Codex's `cwd`), which also feeds the auto-export `ProjectMatcher`.

---

## 4. File Format Specifications

Verified against real data (Cline v3.89.2, 2026-06-17). Treat every field as
optional/defensive.

### 4.1 `state/taskHistory.json` (discovery index)

Array of task summaries. Key fields:

| Field | Use |
|-------|-----|
| `id` | Task id → session id; also `tasks/<id>/` dir name |
| `ts` | Timestamp (epoch ms) → sorting + `last_modified` |
| `task` | First user message / title |
| `cwdOnTaskInitialization` | **Project grouping key** → `workspace_path` |
| `modelId` | Model (display) |
| `totalCost`, `tokensIn/Out` | Optional metadata |

**Edge case:** a task listed in `taskHistory.json` may lack a `tasks/<id>/`
directory (deleted/cleaned) → discovery skips tasks with no dir or no
conversation file.

### 4.2 `tasks/<id>/ui_messages.json` (PRIMARY)

Array of `{ts, type:"say"|"ask", say/ask:<subtype>, text, ...}`.

Classification lives in `src/cline_messages.py`:

- `USER_SAY_SUBTYPES = {task, user_feedback}` → user
- `ASSISTANT_SAY_SUBTYPES = {text, completion_result}` → assistant
- `ASSISTANT_ASK_SUBTYPES = {plan_mode_respond, followup, completion_result}` → assistant
- Everything else (`reasoning`, `api_req_started`, `checkpoint_created`, `task_progress`, `tool`, `use_mcp_server`, `mcp_server_*`, `command`, `resume_task`, …) is skipped (logged at DEBUG).

`ask` entries store JSON in `text` — `decode_ask_text()` extracts the display
field (`plan_mode_respond.response`, `followup.question` + options, etc.).

### 4.3 `tasks/<id>/api_conversation_history.json` (FALLBACK)

Anthropic-API array `[{role, content:[blocks]}]`. Fallback parsing keeps only
`{"type":"text"}` blocks, drops `tool_use`/`tool_result`/`image`/`thinking`,
strips `<task>` (unwrap) and `<environment_details>` (drop) from user text, and
skips user turns that are empty after stripping (pure tool-result turns).

### 4.4 `tasks/<id>/task_metadata.json` (metadata, optional)

`model_usage[0].model_id`, `environment_history[0].cline_version`. Best-effort.

---

## 5. Implemented Modules (reference)

### `src/cline_messages.py` (shared, host-agnostic)
- `USER_SAY_SUBTYPES`, `ASSISTANT_SAY_SUBTYPES`, `ASSISTANT_ASK_SUBTYPES`
- `classify_say(subtype) -> role|""`, `classify_ask(subtype) -> role|""`
- `decode_ask_text(ask_subtype, raw_text) -> str`
- `normalize_cline_content(content) -> str`

### `src/cline_vscode_parser.py`
- `ClineVscodeSession` dataclass
- `parse_cline_vscode_task(task_dir, ...) -> ClineVscodeSession` (primary/fallback orchestrator)
- `_parse_ui_messages()`, `_parse_api_history()`, `_strip_api_wrapper_noise()` (private, VS-Code-file-specific)
- `extract_cline_vscode_messages(session) -> List[ChatMessage]` (source=`ChatSource.CLINE_VSCODE`)

### `src/cline_vscode_projects.py`
- `ClineVscodeTaskInfo`, `ClineVscodeWorkspace` dataclasses
- `discover_cline_vscode_workspaces(cline_data_dir) -> List[ClineVscodeWorkspace]` (reads `state/taskHistory.json`, groups by cwd)
- `get_cline_vscode_session_files(workspace) -> List[Path]` (returns task **directory** paths; the parser derives files from the dir)

### `src/config.py`
- `CLINE_VSCODE_DATA_DIR` env var + `_get_default_cline_vscode_dir()` (OS-specific)
- `cline_vscode_data_dir` property, `validate_cline_vscode_directory()` (requires `state/taskHistory.json`)
- `chat_source_filter` maps `cline-vscode` (and alias `cline`) → `ChatSource.CLINE_VSCODE`

---

## 6. Remaining Steps (5–12)

> **Testing convention:** unit tests ship **within** each step (same commit as the
> code they cover), never as a separate phase. The only dedicated test phase is
> **Phase E2E** (integration / end-to-end). Steps 1–4 already followed this — their
> unit tests (`test_cline_vscode_parser.py`, `test_cline_vscode_projects.py`,
> `TestClineConfig`) landed in the same commit as the code.

### Step 5 — `src/projects.py`
Mirror the Codex blocks. In `list_all_projects()` add a `scan_cline_vscode`
flag and append `ProjectInfo(source=ChatSource.CLINE_VSCODE, workspace_path=ws.workspace_path, path=cline_vscode_data_dir / 'tasks', session_ids=[str(t.task_dir) for t in ws.tasks], ...)`.
In `find_project_by_name()` match `workspace_name` / `Path(workspace_path).name`.
In `get_project_chat_files()` add a `ChatSource.CLINE_VSCODE` branch returning the
task-dir paths from `session_ids` that still exist.

> Note: for Cline the "chat file" stored in `session_ids` is the **task directory**
> (`get_cline_vscode_session_files` returns dirs). The exporter passes the dir to
> `parse_cline_vscode_task`, which selects ui/api internally.

**Unit tests (this step)** — extend `tests/test_projects.py`: a `CLINE_VSCODE`
project appears in `list_all_projects()` with the right `workspace_path` and
`session_ids`; `find_project_by_name()` matches by basename; `get_project_chat_files()`
returns existing task dirs and skips deleted ones. Use a temp globalStorage fixture.

### Step 6 — `src/exporters.py`
1. Import `parse_cline_vscode_task`, `extract_cline_vscode_messages`.
2. `_detect_chat_source()`: a path whose name is `ui_messages.json` **or** a directory containing one ⇒ `ChatSource.CLINE_VSCODE` (check before the `.jsonl`/`.json` logic).
3. Add `_convert_cline_vscode_to_dict()` (mirror `_convert_codex_to_dict()`).
4. `_load_chat_data()`: `ChatSource.CLINE_VSCODE` branch → `session = parse_cline_vscode_task(task_dir); messages = extract_cline_vscode_messages(session)` (resolve `task_dir` from the passed path: it's the dir, or `path.parent` if a file).
5. `export_project_chats()`: Cline file handling (`session_ids` are task dirs; or `project_path.rglob('ui_messages.json')` → `.parent`).

**Unit tests (this step)** — extend `tests/test_exporters.py`: `_detect_chat_source()`
returns `CLINE_VSCODE` for a task dir / `ui_messages.json`; `_load_chat_data()` routes a
Cline task dir through `parse_cline_vscode_task`; `_convert_cline_vscode_to_dict()` shape
is export-compatible. Reuse the parser test fixtures.

### Step 7 — `claude-chat-manager.py`
- `--source` choices → add `cline-vscode` (and `cline` alias, `cline-cli` reserved for the CLI guide).
- Source→enum mapping → `cline-vscode`/`cline` → `ChatSource.CLINE_VSCODE`.
- Epilog examples for `--source cline-vscode`.

**Unit tests (this step)** — extend `tests/test_cli_source_flag.py`: `--source cline-vscode`
and the `cline` alias both resolve to `ChatSource.CLINE_VSCODE`; the argparse choice is accepted.

### Step 8 — `.env.example`
(Documentation only — no unit tests.)
```
# Cline (VS Code extension) data directory — globalStorage/saoudrizwan.claude-dev.
# Point at a VS Code fork's globalStorage to read Cursor/Windsurf/VSCodium/Insiders.
# CLINE_VSCODE_DATA_DIR=/path/to/globalStorage/saoudrizwan.claude-dev
#
# Chat source filter options: claude, kiro, codex, cline-vscode, cline-cli, cline, all
# CHAT_SOURCE=claude
```

### Phase E2E — Integration / End-to-end tests
The only dedicated test phase. After steps 5–7 are wired, add cross-module tests
(e.g. `tests/test_cline_vscode_export_integration.py`):
- Build a realistic temp globalStorage (state/taskHistory.json + one or more
  `tasks/<id>/` with ui_messages.json) and run a full **export** for each format
  (pretty / markdown / book / wiki); assert clean conversation, no tool noise.
- Rename `ui_messages.json` away → assert the api fallback still exports.
- `--source all` lists Claude + Kiro + Codex + Cline VS Code together, date-sorted.
- `auto-export.py --dry-run` maps the Cline project to a target folder via `workspace_path`.

### Step 12 — Docs
- `docs/ARCHITECTURE.md`: new **4.2.3 Data Layer (Cline VS Code)**; add `cline_messages.py`, `cline_vscode_parser.py`, `cline_vscode_projects.py`, tests; add `CLINE_VSCODE_DATA_DIR`; stability zones; multi-source diagrams `[Cline/VSC]`.
- `README.md`: sources list + `--source cline-vscode` usage.
- `docs/chats/` entry for this conversation.

---

## 7. Auto-Export Integration

No matcher changes required. `ProjectInfo.workspace_path` is populated from
`cwdOnTaskInitialization`, so the matcher's workspace-path exact match maps Cline
projects to filesystem folders automatically. Verify with `auto-export.py --dry-run`.

---

## 8. Verification Checklist (post steps 5–11)

```
□ python claude-chat-manager.py --source cline-vscode            # lists projects
□ python claude-chat-manager.py --source cline-vscode "<name>"   # browses a project
□ Export each format (pretty/markdown/book/wiki) for a Cline chat
□ ui_messages.json primary produces clean conversation (no tool noise)
□ Rename ui_messages.json away → api_conversation_history.json fallback works
□ CLINE_VSCODE_DATA_DIR override respected; default path resolves per-OS
□ --source all includes Claude + Kiro + Codex + Cline VS Code, sorted by date
□ auto-export.py --dry-run maps Cline projects via workspace_path
□ pytest tests/test_cline_vscode_*.py + TestClineConfig  # green
```

---

**Document Version:** 2.0
**Updated:** 2026-06-17
**Status:** Steps 1–4 + tests implemented; steps 5–11 pending.
**Format verified against:** Cline v3.89.2, VS Code 1.124.2, macOS

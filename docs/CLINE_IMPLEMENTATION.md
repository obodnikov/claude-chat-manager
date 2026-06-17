# Cline Chat Source — Implementation Guide

## 1. Overview

This document is a complete, self-contained implementation guide for adding **Cline** (the VS Code AI coding agent) as a fourth chat source to claude-chat-manager, alongside the existing Claude Desktop, Kiro IDE, and Codex CLI sources.

It is written so a fresh chat session can implement the feature **without re-researching** Cline's storage format. All file-format details below were verified against real local Cline data (Cline v3.89.2) on 2026-06-17.

**Goal:** Full feature parity with the Claude, Kiro, and Codex sources — project discovery, interactive browsing, all export formats (pretty, markdown, book, wiki), source filtering via `--source cline`, auto-export integration, and comprehensive tests.

**Suggested branch:** `feat/cline`

### Design decisions (already approved)

1. **Conversation source = `ui_messages.json` primary, `api_conversation_history.json` fallback.**
   `ui_messages.json` is the clean UI-facing event log and is used normally. If it is missing, empty, or corrupt, the parser falls back to `api_conversation_history.json` (the raw Anthropic-API transcript, which requires heavier stripping).
2. **Editor scope = stable VS Code only**, overridable via the `CLINE_DATA_DIR` environment variable. No automatic scanning of Cursor / Windsurf / VSCodium / Insiders (a user can point `CLINE_DATA_DIR` at those manually).

### Why Cline fits the existing architecture cleanly

- Cline groups work into **tasks**, and `state/taskHistory.json` is a lightweight index containing **`cwdOnTaskInitialization`** (the workspace path) for every task. This is the direct analogue of Codex's `cwd` grouping key, so discovery reads **one** file and groups by cwd — cheaper than Codex (which must open every rollout file).
- `cwdOnTaskInitialization` plugs straight into the auto-export `ProjectMatcher`, which already matches on `workspace_path`. No matcher changes are required.
- Conversation filtering follows the same "keep messages, drop tool/lifecycle noise" philosophy already used for Codex.

---

## 2. What is Cline?

Cline (formerly "Claude Dev") is an open-source autonomous coding agent that runs **inside VS Code** as an extension.

- **Repository:** [github.com/cline/cline](https://github.com/cline/cline) (Apache-2.0)
- **VS Code extension ID:** `saoudrizwan.claude-dev`
- **Data location:** VS Code **globalStorage** (see §3)
- **Models:** any provider the user configures (Anthropic Claude, OpenAI, OpenRouter, local, etc.) — the model id is stored per task.
- **Session format:** one directory per task, with JSON files (not JSONL).

---

## 3. Cline Data Storage Structure

Cline stores everything under the VS Code globalStorage directory for its extension ID.

**Base path by OS:**

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/` |
| Windows | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\` |
| Linux | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/` |

**Directory layout:**

```
saoudrizwan.claude-dev/
├── state/
│   └── taskHistory.json              # Index of ALL tasks (array) — discovery reads this
├── tasks/
│   └── <task-id>/                    # One directory per task; task-id is an epoch-ms string
│       ├── ui_messages.json          # Rich UI event log (PRIMARY conversation source)
│       ├── api_conversation_history.json  # Raw Anthropic-API transcript (FALLBACK)
│       ├── task_metadata.json        # Files-in-context, model usage, environment
│       └── focus_chain_taskid_<id>.md     # Optional task_progress checklist (ignore)
├── checkpoints/                      # Git-style checkpoints (ignore)
├── settings/                         # User settings, mcp config (ignore)
└── cache/                            # (ignore)
```

**Key observations:**

- A **task** = one logical conversation = the unit we export as a single `.md` "chat".
- `<task-id>` is an **epoch-milliseconds string** (e.g. `1781697826685`); it doubles as the session id and sorts chronologically.
- Tasks are **not** organized by project on disk — they are grouped into "projects" by `cwdOnTaskInitialization` from `taskHistory.json` (same pattern as Codex's `cwd`).
- `state/taskHistory.json` is the **only** file discovery needs to read. It already contains the title, timestamp, cost, model, and cwd of every task.

---

## 4. File Format Specifications

All structures below were observed in real data. Treat every field as optional/defensive — handle missing keys gracefully.

### 4.1 `state/taskHistory.json` (discovery index)

A JSON **array** of task summary objects:

```json
[
  {
    "id": "1781697826685",
    "ulid": "01KVAPWJMM9WEZY8DS34HD148H",
    "ts": 1781697367782,
    "task": "Investigate for me how to adapt KIRO hook ...",
    "tokensIn": 144325,
    "tokensOut": 3986,
    "cacheWrites": 0,
    "cacheReads": 21632,
    "totalCost": 0.053978572,
    "size": 231197,
    "cwdOnTaskInitialization": "/Users/eobomik/src/open-cowork",
    "isFavorited": false,
    "modelId": "claude-opus-4.6"
  }
]
```

**Fields to extract:**

| Field | Use |
|-------|-----|
| `id` | Task id → session id; also the `tasks/<id>/` directory name |
| `ts` | Timestamp (epoch ms) → sorting + `last_modified` |
| `task` | First user message / task title → chat title fallback |
| `cwdOnTaskInitialization` | **Project grouping key** (→ `ProjectInfo.workspace_path`) |
| `modelId` | Model used (display only) |
| `totalCost`, `tokensIn/Out` | Optional metadata (display only) |
| `isFavorited` | Optional (could drive filtering later; not required) |

**Edge case:** A task in `taskHistory.json` may not have a `tasks/<id>/` directory (deleted/cleaned). Discovery must tolerate this — skip tasks whose directory or conversation files are absent.

### 4.2 `tasks/<id>/ui_messages.json` (PRIMARY source)

A JSON **array** of UI event objects. Each object:

```json
{
  "ts": 1781697826689,
  "type": "say",            // "say" | "ask"
  "say": "task",            // present when type == "say"
  "ask": null,              // present when type == "ask"
  "text": "Investigate for me how to adapt KIRO hook ...",
  "conversationHistoryIndex": 0,
  "files": [],
  "images": [],
  "modelInfo": { ... }      // present on some entries
}
```

**`say` subtypes observed (and how to treat them):**

| `say` value | Meaning | Export action |
|-------------|---------|---------------|
| `task` | Initial user task | **KEEP** → role `user` |
| `user_feedback` | Subsequent user message | **KEEP** → role `user` |
| `text` | Assistant text response | **KEEP** → role `assistant` |
| `reasoning` | Assistant chain-of-thought | SKIP (like Codex reasoning) |
| `api_req_started` | API request metadata (JSON in `text`) | SKIP |
| `checkpoint_created` | Git checkpoint marker | SKIP |
| `task_progress` | Todo-list checklist | SKIP |
| `tool` | Tool invocation (JSON in `text`) | SKIP for book; `[Tool: <tool>]` for verbose |
| `use_mcp_server` | MCP tool call | SKIP for book; `[Tool: mcp]` for verbose |
| `mcp_server_request_started` | MCP lifecycle | SKIP |
| `mcp_server_response` | MCP result | SKIP |
| `completion_result` | Final completion text (standard Cline) | **KEEP** → role `assistant` (verify in data) |

**`ask` subtypes observed (text is JSON-encoded — must `json.loads` it):**

| `ask` value | `text` JSON shape | Export action |
|-------------|-------------------|---------------|
| `plan_mode_respond` | `{"response": "...", "options"?: [...]}` | **KEEP** → role `assistant`, use `.response` |
| `followup` | `{"question": "...", "options"?: [...]}` | **KEEP** → role `assistant`, use `.question` (standard Cline `ask_followup_question`; verify) |
| `tool` | `{"tool": "...", "path": "...", "content": "..."}` | SKIP for book; `[Tool: <tool>]` for verbose |
| `command` | `{"command": "..."}` | SKIP for book; `[Tool: command]` for verbose |
| `completion_result` | `{"response"?: "..."}` or string | **KEEP** → role `assistant` (verify) |
| `resume_task` | resume marker | SKIP |
| `resume_completed_task` | resume marker | SKIP |

> Implementation note: subtypes marked "verify" were not present in the single sample task inspected but are documented Cline message types. The parser must treat the subtype lists as **allow/deny sets** and default-skip unknown subtypes, logging them at DEBUG so new types surface without breaking exports.

**Important:** For `ask` entries, `text` is a JSON string. Decode defensively:

```python
def _decode_ask_text(ask_subtype: str, raw_text: str) -> str:
    """Decode the JSON-encoded text of an `ask` entry into display text."""
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return raw_text  # already plain text
    if not isinstance(data, dict):
        return str(data)
    if ask_subtype == "plan_mode_respond":
        return data.get("response", "")
    if ask_subtype == "followup":
        q = data.get("question", "")
        options = data.get("options") or []
        if options:
            opts = "\n".join(f"- {o}" for o in options)
            return f"{q}\n\n{opts}" if q else opts
        return q
    if ask_subtype == "completion_result":
        return data.get("response", raw_text)
    return raw_text
```

### 4.3 `tasks/<id>/api_conversation_history.json` (FALLBACK source)

A JSON **array** of Anthropic-API message objects:

```json
[
  {
    "role": "user",
    "content": [
      { "type": "text", "text": "<task>\nInvestigate ...\n</task>" },
      { "type": "text", "text": "\n# task_progress List ..." },
      { "type": "text", "text": "<environment_details>\n# VSCode Visible Files\n...\n</environment_details>" }
    ]
  },
  {
    "role": "assistant",
    "content": [
      { "type": "text", "text": "..." },
      { "type": "tool_use", "id": "...", "name": "read_file", "input": { ... } }
    ]
  }
]
```

**Fallback parsing rules** (only used when `ui_messages.json` is unusable):

- `role`: `"user"` or `"assistant"`.
- `content`: array of blocks. Keep only `{"type": "text"}` blocks; drop `tool_use`, `tool_result`, `image`, `thinking` blocks.
- **Strip wrapper noise** from user text blocks — remove any block (or the portion) that is wholly:
  - wrapped in `<task>...</task>` → unwrap to inner text (this is the real user message)
  - wrapped in `<environment_details>...</environment_details>` → drop entirely
  - the literal `task_progress` instruction preamble → drop entirely
  - tool-result feedback blocks (often start with `[<tool> for '...'] Result:`) → drop entirely
- A `user` turn that, after stripping, has **no** remaining text is a pure tool-result turn → skip it.
- Join surviving text blocks in a message with `\n\n`.

This fallback is intentionally lossier; it exists for robustness, not fidelity.

### 4.4 `tasks/<id>/task_metadata.json` (metadata, optional)

```json
{
  "files_in_context": [
    { "path": ".kiro/hooks/review-fix-loop.kiro.hook", "record_state": "active", "record_source": "read_tool", "cline_read_date": 1781697834567, "cline_edit_date": null, "user_edit_date": null }
  ],
  "model_usage": [
    { "ts": 1781697826694, "model_id": "claude-opus-4.6", "model_provider_id": "openai", "mode": "plan" }
  ],
  "environment_history": [
    { "ts": 1781697826694, "os_name": "darwin", "os_version": "25.5.0", "os_arch": "arm64", "host_name": "Visual Studio Code", "host_version": "1.124.2", "cline_version": "3.89.2" }
  ]
}
```

Not required for conversation export. Optionally read `model_usage[0].model_id` / `environment_history[0].cline_version` for richer metadata. Treat as best-effort.

---

## 5. Filtering Rules Summary

### For Book / Markdown / Wiki export (conversation only)

**INCLUDE (from `ui_messages.json`):**
- `say == "task"` → user
- `say == "user_feedback"` → user
- `say == "text"` → assistant
- `say == "completion_result"` → assistant
- `ask == "plan_mode_respond"` → assistant (use decoded `.response`)
- `ask == "followup"` → assistant (use decoded `.question` [+ options])
- `ask == "completion_result"` → assistant

**EXCLUDE everything else**, notably: `reasoning`, `api_req_started`, `checkpoint_created`, `task_progress`, `tool`, `use_mcp_server`, `mcp_server_request_started`, `mcp_server_response`, `command`, `resume_task`, `resume_completed_task`, and any unknown subtype (logged at DEBUG).

### For Verbose / Raw export

Additionally include tool activity as indicators:
- `say == "tool"` / `ask == "tool"` → `[Tool: <tool-name>]`
- `say == "use_mcp_server"` → `[Tool: mcp:<server>]`
- `ask == "command"` → `[Command: <command>]`

### Content normalization

- `say` entries: `text` is already a plain string → use as-is.
- `ask` entries: `text` is a JSON string → decode via `_decode_ask_text()` (§4.2).
- Skip messages whose normalized content is empty/whitespace.

---

## 6. Conversation Source Strategy (primary + fallback)

```
parse_cline_task(task_dir):
    ui_path  = task_dir / "ui_messages.json"
    api_path = task_dir / "api_conversation_history.json"

    messages = []
    if ui_path exists:
        try:
            messages = _parse_ui_messages(ui_path)   # §4.2 rules
        except Exception as e:
            log.warning("ui_messages parse failed for %s: %s", task_dir, e)
            messages = []

    if not messages and api_path exists:              # fallback trigger
        log.info("Falling back to api_conversation_history for %s", task_dir)
        try:
            messages = _parse_api_history(api_path)    # §4.3 rules
        except Exception as e:
            log.warning("api_history parse failed for %s: %s", task_dir, e)

    return ClineSession(... messages=messages ...)
```

Fallback triggers when `ui_messages.json` is missing, unreadable, or yields **zero** conversation messages.

---

## 7. Implementation Steps — Detailed

> Follow the exact same structure as `docs/CODEX_IMPLEMENTATION.md`. Each step below names the file and the change. Honor `AI.md`: PEP8, type hints, Google-style docstrings, custom exceptions, `logging` (no `print`), modules < 800 lines, tests in `tests/`, docs in `docs/`.

### Step 1 — `src/models.py`: add the enum value

```python
class ChatSource(Enum):
    CLAUDE_DESKTOP = "claude"
    KIRO_IDE = "kiro"
    CODEX = "codex"
    CLINE = "cline"        # NEW
    UNKNOWN = "unknown"
```

No other changes — `ChatMessage` and `ProjectInfo` already have `source`, `workspace_path`, `session_ids`.

### Step 2 — `src/cline_parser.py` (NEW)

Pattern: `src/codex_parser.py`. Provide:

```python
@dataclass
class ClineSession:
    task_id: str
    cwd: str
    title: str                       # from taskHistory.task or first user msg
    timestamp: str                   # ISO or epoch-ms string
    model: str = ""
    cline_version: str = ""
    total_cost: float = 0.0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    task_dir: Optional[Path] = None

# Functions:
def parse_cline_task(task_dir: Path) -> ClineSession            # §6 orchestrator
def _parse_ui_messages(ui_path: Path) -> List[Dict[str, Any]]   # §4.2 + §5
def _parse_api_history(api_path: Path) -> List[Dict[str, Any]]  # §4.3 fallback
def _decode_ask_text(ask_subtype: str, raw_text: str) -> str    # §4.2
def normalize_cline_content(text: Any) -> str                   # trim/guard
def extract_cline_messages(session: ClineSession) -> List[ChatMessage]
```

`extract_cline_messages` mirrors `extract_codex_messages`: build `ChatMessage(role=..., content=..., timestamp=..., source=ChatSource.CLINE, execution_id=session.task_id)`, skipping empty content.

Raise `ChatFileNotFoundError` / `InvalidChatFileError` (from `src/exceptions.py`) on hard errors, consistent with the Codex/Kiro parsers.

### Step 3 — `src/cline_projects.py` (NEW)

Pattern: `src/codex_projects.py`, but **discovery reads `state/taskHistory.json`** instead of scanning files.

```python
@dataclass
class ClineTaskInfo:
    task_id: str
    task_dir: Path
    cwd: str
    timestamp: str
    title: str = ""
    model: str = ""

@dataclass
class ClineWorkspace:
    workspace_path: str
    workspace_name: str               # Path(cwd).name
    tasks: List[ClineTaskInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    cline_data_dir: Optional[Path] = None

def discover_cline_workspaces(cline_data_dir: Path) -> List[ClineWorkspace]:
    """Read state/taskHistory.json, group tasks by cwdOnTaskInitialization."""
    # 1. Load <cline_data_dir>/state/taskHistory.json  (array)
    # 2. For each entry:
    #       task_id = entry["id"]; cwd = entry.get("cwdOnTaskInitialization")
    #       task_dir = cline_data_dir / "tasks" / task_id
    #       skip if not cwd OR not task_dir.exists()
    #       skip if neither ui_messages.json nor api_conversation_history.json exists
    #    Build ClineTaskInfo (timestamp from entry["ts"]).
    # 3. Group by cwd → ClineWorkspace (last_modified = max ts, formatted).
    # 4. Sort workspaces newest-first.

def get_cline_session_files(workspace: ClineWorkspace) -> List[Path]:
    """Return the ui_messages.json path for each task (the 'chat file')."""
    return [t.task_dir / "ui_messages.json" for t in workspace.tasks
            if (t.task_dir / "ui_messages.json").exists()
            or (t.task_dir / "api_conversation_history.json").exists()]
```

**The "chat file" convention:** like Codex stores absolute paths in `session_ids`, Cline stores the **`ui_messages.json` path** (or the task dir) per task. The parser derives the task dir as `file_path.parent`. Keep this consistent across `projects.py` and `exporters.py`.

### Step 4 — `src/config.py`

1. `self._cline_dir: Optional[Path] = None` in `__init__`.
2. In `_load_config()`:

```python
cline_dir_env = os.getenv('CLINE_DATA_DIR')
if cline_dir_env:
    self._cline_dir = Path(cline_dir_env)
else:
    self._cline_dir = _default_cline_dir()   # OS-specific globalStorage path
```

3. Helper for the OS-specific default (stable VS Code only):

```python
def _default_cline_dir() -> Path:
    ext = 'saoudrizwan.claude-dev'
    home = Path.home()
    if sys.platform == 'darwin':
        base = home / 'Library' / 'Application Support' / 'Code' / 'User' / 'globalStorage'
    elif sys.platform.startswith('win'):
        appdata = os.getenv('APPDATA')
        base = Path(appdata) / 'Code' / 'User' / 'globalStorage' if appdata \
               else home / 'AppData' / 'Roaming' / 'Code' / 'User' / 'globalStorage'
    else:
        base = home / '.config' / 'Code' / 'User' / 'globalStorage'
    return base / ext
```

4. `cline_data_dir` property + `validate_cline_directory()` (must contain `state/taskHistory.json` OR a non-empty `tasks/` dir).
5. Extend `chat_source_filter` to map `'cline'` → `ChatSource.CLINE`.

### Step 5 — `src/projects.py`

Mirror the Codex blocks in:
- `list_all_projects()` — add `scan_cline` flag and a Cline discovery block that appends `ProjectInfo(source=ChatSource.CLINE, workspace_path=ws.workspace_path, path=cline_data_dir / 'tasks', session_ids=[str(t.task_dir / 'ui_messages.json') for t in ws.tasks], ...)`.
- `find_project_by_name()` — match against `workspace_name` and `Path(workspace_path).name`.
- `get_project_chat_files()` — add a `ChatSource.CLINE` branch returning the `session_ids` paths that exist (same shape as the Codex branch).

### Step 6 — `src/exporters.py`

1. Import the Cline parser functions.
2. `_detect_chat_source()`: a file named `ui_messages.json` (or `api_conversation_history.json`) ⇒ `ChatSource.CLINE`. Check filename **before** the `.jsonl`/`.json` extension logic, since Cline files are `.json`.
3. Add `_convert_cline_to_dict()` (mirror `_convert_codex_to_dict()`).
4. `_load_chat_data()`: add a `ChatSource.CLINE` branch →
   `session = parse_cline_task(file_path.parent); messages = extract_cline_messages(session)`.
5. `export_project_chats()`: add Cline file handling (the files come from `session_ids`; if globbing, use `project_path.rglob('ui_messages.json')`).

### Step 7 — `claude-chat-manager.py`

- `--source` choices → add `'cline'`.
- Source→enum mapping → add `cline` → `ChatSource.CLINE`.
- Epilog examples:

```
%(prog)s --source cline                 # List Cline projects
%(prog)s --source cline "my-project"    # Browse a Cline project
%(prog)s --source all                   # Claude + Kiro + Codex + Cline
```

### Step 8 — `.env.example`

```
# ============================================================================
# Cline (VS Code) Settings
# ============================================================================
# Cline data directory (VS Code globalStorage for extension saoudrizwan.claude-dev).
# Default (stable VS Code):
#   macOS:   ~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev
#   Windows: %APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev
#   Linux:   ~/.config/Code/User/globalStorage/saoudrizwan.claude-dev
# To read Cline data from a VS Code fork (Cursor, Windsurf, VSCodium, Insiders),
# point this at that editor's globalStorage/saoudrizwan.claude-dev directory.
# CLINE_DATA_DIR=/path/to/globalStorage/saoudrizwan.claude-dev

# Chat source filter — add `cline` to the existing options:
# Options: claude, kiro, codex, cline, all
# CHAT_SOURCE=claude
```

### Step 9 — `tests/test_cline_parser.py` (NEW)

Pattern: `tests/test_codex_parser.py`. Use temp dirs and helper builders. Cover:

- `_parse_ui_messages`: keeps `say:task`/`user_feedback`/`text`; drops `reasoning`/`api_req_started`/`checkpoint_created`/`task_progress`/`tool`/`use_mcp_server`/`mcp_server_*`.
- `_decode_ask_text`: `plan_mode_respond` → `.response`; `followup` → `.question` (+ options); malformed JSON → raw text; non-dict JSON → str.
- `ask:plan_mode_respond` and `ask:followup` kept as assistant; `ask:tool`/`resume_task` dropped.
- **Fallback**: missing `ui_messages.json` → parses `api_conversation_history.json`; empty `ui_messages.json` (no convo) → triggers fallback.
- `api_history` stripping: `<task>` unwrapped, `<environment_details>` dropped, pure tool-result user turns skipped, `tool_use` blocks dropped.
- `extract_cline_messages`: roles/content/`source==ChatSource.CLINE`/`execution_id==task_id`; empty messages skipped.
- Error paths: missing task dir, both files absent.

### Step 10 — `tests/test_cline_projects.py` (NEW)

Pattern: `tests/test_codex_projects.py`. Cover:

- `discover_cline_workspaces`: groups tasks sharing a cwd into one workspace; multiple cwds → multiple workspaces.
- Tasks listed in `taskHistory.json` but missing their `tasks/<id>/` dir → skipped.
- Tasks with neither conversation file → skipped.
- `last_modified` = newest task `ts`; workspaces sorted newest-first.
- `get_cline_session_files` returns existing `ui_messages.json` paths (or tasks with only `api_conversation_history.json`).
- Empty/missing `taskHistory.json` → returns `[]` (no crash).

### Step 11 — Documentation

- Update `docs/ARCHITECTURE.md`:
  - Repo-structure listing: add `cline_parser.py`, `cline_projects.py`, the new tests, and this guide.
  - New section **4.2.3 Data Layer (Cline)** mirroring the Codex one.
  - Critical Paths + §6 env vars: add `CLINE_DATA_DIR` and the globalStorage default.
  - Stability Zones: add Cline parser/projects under ✅ Stable once tests pass.
  - Multi-source diagrams: add `[Cline]` alongside `[Codex]`.
  - Bump Document Version / Last Updated / Status.
- Update `README.md`: add Cline to the sources list, `--source cline` usage, and a short "Cline (VS Code) support" subsection.
- Add a `docs/chats/` entry for this implementation conversation (project convention).

---

## 8. Auto-Export Integration

No changes required to `src/project_matcher.py` or `src/auto_exporter.py`:

- `ProjectInfo.workspace_path` is populated from `cwdOnTaskInitialization`, so the matcher's **workspace-path exact match** strategy (priority 2) maps Cline projects to filesystem folders automatically.
- `AutoExporter` already iterates all sources returned by `list_all_projects()`; once Cline appears there, it participates in discover → group → export → merge with no extra wiring.

Verify after implementation: run `auto-export.py --dry-run` and confirm Cline projects appear with correct target folders and merge previews.

---

## 9. Verification Checklist

```
□ ChatSource.CLINE added; existing enum tests still pass
□ python claude-chat-manager.py --source cline            # lists Cline projects
□ python claude-chat-manager.py --source cline "<name>"   # browses a project
□ Export each format (pretty/markdown/book/wiki) for a Cline chat
□ ui_messages.json primary path produces clean conversation (no tool noise)
□ Rename/remove ui_messages.json → api_conversation_history.json fallback works
□ CLINE_DATA_DIR override respected; default path resolves per-OS
□ --source all includes Claude + Kiro + Codex + Cline, sorted by date
□ auto-export.py --dry-run maps Cline projects via workspace_path
□ pytest tests/test_cline_parser.py tests/test_cline_projects.py  # all green
□ black + mypy clean on new modules
□ Docs updated (ARCHITECTURE.md, README.md, docs/chats/ entry)
```

---

## 10. Quick Reference — Field Map

| Concept | Cline source | Field |
|---------|--------------|-------|
| Project grouping key | `state/taskHistory.json` | `cwdOnTaskInitialization` |
| Chat (session) id | `state/taskHistory.json` | `id` (also `tasks/<id>/`) |
| Chat title | `state/taskHistory.json` | `task` |
| Chat timestamp | `state/taskHistory.json` | `ts` (epoch ms) |
| User message | `ui_messages.json` | `say:task`, `say:user_feedback` |
| Assistant message | `ui_messages.json` | `say:text`, `ask:plan_mode_respond.response`, `ask:followup.question`, `say/ask:completion_result` |
| Fallback transcript | `api_conversation_history.json` | `role` + `content[].text` (stripped) |
| Model id | `taskHistory.json` / `task_metadata.json` | `modelId` / `model_usage[].model_id` |

---

**Document Version:** 1.0
**Created:** 2026-06-17
**Status:** 📋 Design complete — ready for implementation (branch `feat/cline`)
**Format verified against:** Cline v3.89.2, VS Code 1.124.2, macOS

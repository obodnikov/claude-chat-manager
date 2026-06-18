# Cline CLI Chat Source — Implementation Guide

## 1. Overview

This document is the design guide for adding the **Cline CLI** as a chat source,
a sibling of the [Cline VS Code extension source](CLINE_VSCODE_IMPLEMENTATION.md).

Cline ships in two hosts with **different storage**, so they are **two separate
sources** in this project:

| Source | Enum | Storage | Container |
|--------|------|---------|-----------|
| Cline VS Code extension | `ChatSource.CLINE_VSCODE` | `globalStorage/saoudrizwan.claude-dev/` | per-task JSON files |
| **Cline CLI** (this doc) | `ChatSource.CLINE_CLI` (`"cline-cli"`) | `~/.cline/data/` | **SQLite** session DB |

**Key reuse:** both hosts emit the **same message schema**
(`{type:"say"|"ask", say/ask, text, ts, reasoning, partial}`), so this source
**reuses `src/cline_messages.py`** (classification, `decode_ask_text`,
`normalize_cline_content`) exactly as the VS Code source does. Only the
**discovery + storage adapter** is new.

> ⚠️ **Status: BLOCKED ON GROUNDING.** The exact SQLite schema and the location
> of per-task history in CLI mode have **not yet been verified against real
> data** — at the time of writing `~/.cline/data/sessions/` did not exist
> because no CLI task had been run. Do §4 (Grounding) **first**, then implement.

---

## 2. What is the Cline CLI?

A terminal/TUI host for the same Cline core engine, installed separately from the
VS Code extension.

- **Docs:** https://docs.cline.bot/cli/cli-reference
- **Home dir:** `~/.cline` (override with `--data-dir` or the `CLINE_DATA_DIR`
  env var — **Cline's own** variable; see the naming note below)
- **JSON stream:** `cline task --json` emits one message object per line using
  the shared schema.

### ⚠️ Env-var naming collision

`CLINE_DATA_DIR` is **Cline CLI's own** environment variable (it replaces
`~/.cline/data/`). To avoid confusion, **this project uses a distinct variable**:

| Our config | Points at | Default |
|------------|-----------|---------|
| `CLINE_CLI_DATA_DIR` | the CLI data dir | `~/.cline/data` (or `~/.cline` — confirm in §4) |

Do **not** reuse `CLINE_DATA_DIR` in our `.env` — it would shadow/confuse the
real Cline CLI variable.

---

## 3. Observed Storage Layout (`~/.cline/`)

From the docs plus a real (task-less) install on 2026-06-17:

```
~/.cline/
  data/
    settings/
      providers.json          # API keys / provider config (ignore)
      rules/  skills/          # (ignore)
    teams/                     # team state (ignore)
    sessions/                  # ← SQLite session database (APPEARS AFTER FIRST TASK)
    workspaces/
      <hash>/workspaceState.json   # per-workspace state (observed)
    globalState.json           # global state — may hold taskHistory (observed; no taskHistory yet)
    secrets.json               # (ignore)
    logs/
  plugins/
```

Observed on the real install **before any CLI task**:
- `data/globalState.json` exists but has **no `taskHistory`** key yet (it shares
  the extension's state schema — note the `__vscodeMigrationVersion` key).
- `data/workspaces/<hash>/workspaceState.json` exist (hashed workspace ids).
- `data/sessions/` does **not** exist yet.

**Working hypothesis (verify in §4):** after a CLI task runs, conversation data
lands in `data/sessions/` (SQLite) and/or `data/globalState.json` gains a
`taskHistory` array analogous to the extension's `state/taskHistory.json`.

---

## 4. Grounding Procedure (DO THIS FIRST)

Run at least one real Cline CLI task, then inspect:

```bash
# 1. Run a task so storage is populated
cline task "say hello"        # or: cline   (interactive), then exit

# 2. Inspect what appeared
find ~/.cline/data -maxdepth 3 -newermt "-10 minutes" -type f

# 3. If sessions/ is SQLite, dump its schema + a sample
ls -la ~/.cline/data/sessions/
sqlite3 ~/.cline/data/sessions/*.db ".tables"
sqlite3 ~/.cline/data/sessions/*.db ".schema"
sqlite3 ~/.cline/data/sessions/*.db "SELECT * FROM <messages-table> LIMIT 5;"

# 4. Check whether globalState.json gained a taskHistory + cwd grouping key
jq '.taskHistory[0] // "absent"' ~/.cline/data/globalState.json
jq '.workspaceRoots, .primaryRootIndex' ~/.cline/data/globalState.json

# 5. Inspect a workspaceState.json for cwd / task references
jq 'keys' ~/.cline/data/workspaces/*/workspaceState.json
```

Record, for the implementation:
- **Where the task index lives** (SQLite table vs `globalState.taskHistory`).
- **The project grouping key** (the CLI analogue of `cwdOnTaskInitialization`).
- **The message table/columns** and how `say`/`ask`/`text`/`ts` are stored
  (one row per message? a JSON blob per task?).
- **How task ↔ workspace** is linked (the `workspaces/<hash>` mapping).

Update §3 and §5 with the verified facts before writing code.

---

## 5. Implementation Plan (mirror the VS Code source)

> Reuse `src/cline_messages.py` for all schema logic. Only discovery/storage is new.

### Step 1 — `src/models.py`
Add `CLINE_CLI = "cline-cli"` to `ChatSource`. Update `test_models.py`
(`"cline-cli" in sources`, member count).

### Step 2 — `src/cline_cli_parser.py` (NEW)
- `ClineCliSession` dataclass (task_id, cwd, title, timestamp, model, messages, source ref).
- `parse_cline_cli_task(...) -> ClineCliSession` — read the task's messages from
  SQLite (or the verified store), map rows → the same intermediate dicts the VS
  Code parser produces (`{role, content, timestamp, subtype}`), using
  `classify_say` / `classify_ask` / `decode_ask_text` from `cline_messages`.
- `extract_cline_cli_messages(session) -> List[ChatMessage]` with
  `source=ChatSource.CLINE_CLI` (mirror `extract_cline_vscode_messages`).

### Step 3 — `src/cline_cli_projects.py` (NEW)
- `ClineCliTaskInfo`, `ClineCliWorkspace` dataclasses.
- `discover_cline_cli_workspaces(cline_cli_data_dir) -> List[ClineCliWorkspace]`
  — read the task index (SQLite/`globalState`), group by the verified cwd key.
- `get_cline_cli_session_files(workspace)` — return per-task handles (a task id
  or a `(db_path, task_id)` pair, since there is no per-task file).

> Because CLI tasks live in a shared DB (not files), `session_ids` should carry a
> stable handle (e.g. `cline-cli://<task_id>`), and the exporter resolves it via
> `parse_cline_cli_task`. Decide the handle format during grounding.

### Step 4 — `src/config.py`
- `CLINE_CLI_DATA_DIR` env var + `_get_default_cline_cli_dir()` (`~/.cline/data`).
- `cline_cli_data_dir` property + `validate_cline_cli_directory()` (checks the
  verified store exists — e.g. `sessions/` or `globalState.json` with tasks).
- Extend `chat_source_filter` / `is_chat_source_set` for `cline-cli`. Once this
  lands, make `cline` an **umbrella** that yields both `CLINE_VSCODE` and
  `CLINE_CLI` (this requires `chat_source_filter` to return a set/None — coordinate
  with `projects.py`, which currently expects a single `ChatSource` or `None`).

### Steps 5–8 — `projects.py`, `exporters.py`, `claude-chat-manager.py`, `.env.example`
Mirror the VS Code wiring (see [CLINE_VSCODE_IMPLEMENTATION.md](CLINE_VSCODE_IMPLEMENTATION.md) §6),
substituting the `cline_cli_*` modules, `ChatSource.CLINE_CLI`, `--source cline-cli`,
and `CLINE_CLI_DATA_DIR`. In `exporters._detect_chat_source`, CLI sessions arrive
as `cline-cli://` handles rather than file paths, so detect by that scheme.

### Steps 9–10 — Tests
`tests/test_cline_cli_parser.py`, `tests/test_cline_cli_projects.py`. Build a
**temporary SQLite DB fixture** matching the verified schema. The schema-level
behavior (say/ask filtering, ask decoding) is already covered by the shared
`cline_messages` tests — focus these on the SQLite adapter and discovery/grouping.

### Step 11 — Docs
Update `docs/ARCHITECTURE.md` (new **4.2.4 Data Layer (Cline CLI)**), `README.md`,
and this file (flip status to implemented).

---

## 6. Auto-Export Integration

Same as the VS Code source: once `ProjectInfo.workspace_path` is populated from
the CLI's cwd grouping key, the auto-export `ProjectMatcher` maps CLI projects to
filesystem folders with no matcher changes. If a user runs the **same** project in
both VS Code and the CLI, both sources share the same `workspace_path`, so
auto-export merges them into one `docs/chats/` folder (dedup handled by
`ChatMerger`).

---

## 7. Open Questions (resolve during grounding)

1. SQLite vs `globalState.taskHistory` — which is authoritative for the task list?
2. Exact message table schema and how partial/streaming rows are finalized.
3. The cwd / workspace grouping key name in CLI mode.
4. Whether `data/sessions/` is one DB or one DB per session.
5. Final `session_ids` handle format for DB-backed tasks.

---

**Document Version:** 0.1 (design, pre-grounding)
**Created:** 2026-06-17
**Status:** 🔒 Blocked — run §4 grounding against real CLI data before implementing.
**Partial layout verified against:** Cline CLI install (task-less), macOS, 2026-06-17

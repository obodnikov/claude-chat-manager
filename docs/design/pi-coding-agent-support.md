# Pi Coding Agent — Source Support + Wingman Title Sync

Design + implementation plan for adding **`pi-coding-agent`** as a first-class chat
source in Claude Chat Manager (alongside Claude Desktop, Kiro IDE, Codex CLI, and
Cline VS Code), and for an **optional** feature that writes LLM-generated export
titles back into the sqowe-wingman session-title map.

> **Status: PLANNED — not yet implemented.** Authored 2026-06-28. Verified against the
> installed agent **`@earendil-works/pi-coding-agent` v0.80.2** and real session files
> under `~/.pi/agent/sessions/`.
>
> **Two features, deliberately sequenced (A → B):**
> - **Feature A — Pi source.** Discover, browse, and export pi sessions. Full parity
>   with the existing Codex/Kiro/Cline integrations. **Self-contained.**
> - **Feature B — Wingman title sync.** When book/wiki export generates an LLM title for
>   a pi session, also persist it to `~/.pi/agent/sessions/.wingman-titles.json`.
>   **Optional, off by default. Depends on Feature A.**
>
> **Read first:** [docs/ARCHITECTURE.md](../ARCHITECTURE.md) (system structure, stability
> zones, "Adding a new chat source" recipe in §9), [AI.md](../../AI.md) (Python coding
> rules), and the existing Codex implementation
> ([docs/CODEX_IMPLEMENTATION.md](../CODEX_IMPLEMENTATION.md),
> [src/codex_parser.py](../../src/codex_parser.py),
> [src/codex_projects.py](../../src/codex_projects.py)) — the template this plan mirrors.

---

## 1. Goal & scope

**Goal.** Make pi-coding-agent sessions browsable and exportable through the same unified
CLI surface as every other source: `--source pi`, interactive browser, list, search,
book/wiki/markdown export, and the auto-export pipeline.

**Feature A scope (full parity).** A `pi_parser` + `pi_projects` module pair plus all the
wiring touchpoints that Codex has, complete with tests and documentation
(ARCHITECTURE, README, this design doc).

**Feature B scope.** A single optional behavior layered on top of the existing LLM
title-generation path: persist the human-readable title into wingman's sidecar index,
keyed by pi session uuid, guarded so it never clobbers a user's manual rename.

**Non-goals.**
- Reconstructing pi's session **tree/branches** — we read message entries in file order
  (the main append path), exactly as the Codex/Cline parsers do.
- Modifying pi's own `.jsonl` session files (never ours to own).
- Implementing wingman's own UI (the VS Code extension is a separate project).
- A general "write titles for every source" feature — Feature B is pi-only because the
  wingman index is keyed by pi session uuid.

---

## 2. Background — the established "new source" pattern

ARCHITECTURE §9 ("How do I add support for a new chat source?") defines the recipe, and
Codex/Kiro/Cline are worked examples. Every source provides:

1. A **parser** module (`src/<src>_parser.py`) — file → structured session → `ChatMessage`s.
2. A **projects** module (`src/<src>_projects.py`) — discovery + grouping into projects.
3. A value in the **`ChatSource`** enum ([src/models.py](../../src/models.py)).
4. **Config** properties + validation ([src/config.py](../../src/config.py)).
5. Wiring into the **unified listing/search** ([src/projects.py](../../src/projects.py)),
   **export dispatch** ([src/exporters.py](../../src/exporters.py)), **CLI**
   ([src/cli.py](../../src/cli.py), [src/cli_utils.py](../../src/cli_utils.py)),
   **counting** ([src/parser.py](../../src/parser.py)), the **`--source` flag**
   ([claude-chat-manager.py](../../claude-chat-manager.py)), and the **auto-export label
   map** ([src/auto_exporter.py](../../src/auto_exporter.py)).

> **Note on Cline.** Cline was only *partially* wired into `cli.py` (its interactive
> source menu, `_source_label`, and `_source_icon` skip it). **Pi follows the fully-wired
> Codex pattern** so it appears everywhere, including the interactive browser.

**Why Codex is the closest analog.** Both pi and Codex store **JSONL** with a metadata
**header line** followed by **message lines**, and both group sessions into projects by
**working directory (`cwd`)**. The differences are localized to header shape and content-
block normalization (see §3).

---

## 3. Pi session format (verified against v0.80.2)

**Location:** `~/.pi/agent/sessions/--<path>--/<timestamp>_<uuid>.jsonl`, where `<path>`
is the working directory with `/` replaced by `-`. (We do **not** parse the slug; we read
`cwd` from the header — more robust.)

**First line — session header** (metadata only; not part of the entry tree):

```json
{"type":"session","version":3,"id":"019ef0c5-fdf8-7626-ad4d-da7ee350c408",
 "timestamp":"2026-06-22T19:19:27.993Z","cwd":"/Users/eobomik/src/sqowe-wingman"}
```

- `id` — the **session uuid** (stable; this is wingman's index key for Feature B).
- `cwd` — project grouping key.
- `version` — 1/2/3 (auto-migrated by pi; we tolerate any).

**Subsequent lines — entries** with `id`/`parentId` forming a tree. The relevant type:

```json
{"type":"message","id":"6fd99a80","parentId":"d1819595",
 "timestamp":"2026-06-27T13:17:02.847Z",
 "message":{"role":"user","content":[{"type":"text","text":"…"}]}}
```

Other entry types we **skip** for export: `model_change`, `thinking_level_change`,
`compaction`, `branch_summary`, `custom`, `custom_message`, `label`, `session_info`.

**Message roles** (`message.role`): `user`, `assistant`, `toolResult`, `bashExecution`,
`custom`, `branchSummary`, `compactionSummary`. We keep **`user` + `assistant`** (matching
Codex, which keeps user+assistant and drops reasoning/tool noise).

**Content shapes:**
- `user.content` — a bare **string**, OR an array of `{type:"text",text}` / `{type:"image",…}` blocks.
- `assistant.content` — an array of `{type:"text",text}` / `{type:"thinking",thinking}` /
  `{type:"toolCall",…}` blocks.

**Normalization rule (`normalize_pi_content`):** if string, return as-is; if list, join the
`text` of every `type:"text"` block with `\n`; **drop** `thinking`, `toolCall`, and `image`
blocks. Empty result → message skipped.

---

## 4. Settled decisions

| Topic | Decision | Rationale |
| --- | --- | --- |
| Template | Mirror **Codex** end-to-end. | Same JSONL-header-then-messages shape; same cwd grouping; fully wired (unlike Cline). |
| `ChatSource` value | `PI = "pi"`. | Matches the `--source pi` CLI token. |
| Data dir + override | Default `~/.pi/agent`; env **`PI_DATA_DIR`**. Sessions read from `<dir>/sessions/`. | Single override var; simplest correct default. |
| Project grouping | By header **`cwd`** (read header only during discovery). | Same as Codex; robust vs. parsing the dir slug. |
| Roles exported | `user` + `assistant`. | Matches Codex; drops tool/lifecycle noise. |
| Content normalize | Join `text` blocks; drop `thinking`/`toolCall`/`image`; tolerate bare strings. | Faithful, readable transcripts. |
| Tree handling | Read `message` entries in **file order** (main append path); ignore branching. | Pragmatic parity with Codex/Cline; full tree-walk is out of scope. |
| CLI parity | Wire into `cli.py` labels/icons/detect (the bit Cline skipped). | Pi shows up in the interactive browser too. |
| **Feature B** target | Write **wingman's** `~/.pi/agent/sessions/.wingman-titles.json` (v1 schema). | Documented shared sidecar; wingman anticipates external writers (its design §9.2-7). |
| **Feature B** switch | `PI_WRITE_WINGMAN_TITLES`, **off by default**. | Opt-in; cross-project write must be deliberate. |
| **Feature B** title form | The **raw** LLM title (spaces, no dashes) — *before* filename slugification. | Wingman wants a human-readable label, not a kebab filename. |
| **Feature B** guard | Never overwrite `source:"manual"`; **refresh** an existing `source:"llm"` entry. | "Populate only if a customer-defined name is not present"; keep llm titles current. |
| **Feature B** triggers | **Book and Wiki** LLM-title paths. | Maximum coverage of pi exports. |

---

## 5. Feature A — Pi source (detailed design)

### 5.1 `src/pi_parser.py` (new)

```python
@dataclass
class PiSession:
    session_id: str          # header `id` (uuid) — Feature B key
    cwd: str
    timestamp: str           # header timestamp (ISO-8601)
    version: int             # header `version` (1/2/3)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    file_path: Optional[Path] = None

def parse_pi_session_meta(file_path: Path) -> Dict[str, Any]: ...
    # Read ONLY line 1; assert type == "session"; return header dict.
    # Raises ChatFileNotFoundError / InvalidChatFileError (reuse exceptions.py).

def parse_pi_session_file(file_path: Path) -> PiSession: ...
    # Stream the file; capture header; collect type=="message" entries whose
    # message.role in (user, assistant); skip malformed lines (log + continue).

def normalize_pi_content(content: Any) -> str: ...
    # str -> str; list -> join text blocks; drop thinking/toolCall/image.

def extract_pi_messages(session: PiSession) -> List[ChatMessage]: ...
    # role, normalize_pi_content(content), timestamp, source=ChatSource.PI,
    # execution_id=session.session_id. Skip empty-after-normalize messages.
```

Mirrors `codex_parser.py` (header-only fast path + full parse + normalize + extract).

### 5.2 `src/pi_projects.py` (new)

```python
@dataclass
class PiSessionInfo:        # lightweight, for discovery
    session_id: str
    file_path: Path
    cwd: str
    timestamp: str

@dataclass
class PiWorkspace:          # one per unique cwd
    workspace_path: str
    workspace_name: str     # Path(cwd).name
    sessions: List[PiSessionInfo] = field(default_factory=list)
    session_count: int = 0
    last_modified: str = "Unknown"
    pi_data_dir: Optional[Path] = None

def discover_pi_workspaces(pi_data_dir: Path) -> List[PiWorkspace]: ...
    # rglob("*.jsonl") under <pi_data_dir>/sessions/; ignore dot-files
    # (so .wingman-titles.json is skipped); read header per file; group by cwd;
    # last_modified from newest header timestamp; sort newest-first.

def get_pi_session_files(workspace: PiWorkspace) -> List[Path]: ...
    # Existing file paths, sorted by mtime desc.
```

Mirrors `codex_projects.py`. **Important:** the `*.jsonl` glob must ignore the dot-prefixed
`.wingman-titles.json` (it is not a session file — and `rglob("*.jsonl")` already excludes
it since it ends in `.json`, but discovery must also never treat any sidecar as a session).

### 5.3 Wiring touchpoints (file-by-file)

| File | Change |
| --- | --- |
| [src/models.py](../../src/models.py) | Add `PI = "pi"` to `ChatSource`; docstring line. |
| [src/config.py](../../src/config.py) | `_pi_dir` (init from `PI_DATA_DIR` else `~/.pi/agent`); `pi_data_dir` property; `validate_pi_directory()` (dir exists + `sessions/` subdir exists). |
| [src/cli_utils.py](../../src/cli_utils.py) | Add `'pi'` to `SOURCE_CHOICES`; `parse_source_filter` case `'pi' -> ChatSource.PI`. |
| [src/projects.py](../../src/projects.py) | `_pi_workspace_to_project_info()` (sets `source=PI`, `workspace_path=cwd`, `session_ids=`abs file-path strings, `path=pi_data_dir/'sessions'`); add `scan_pi`/`search_pi` blocks in `list_all_projects()` + `search_projects_by_name()`; `PI` branch in `get_project_chat_files()` (resolve absolute session paths, like Codex). |
| [src/parser.py](../../src/parser.py) | `count_pi_messages_in_file()` (count lines starting `{"type":"message"`). |
| [src/exporters.py](../../src/exporters.py) | `_detect_chat_source()`: in the `.jsonl` branch, if header `type=="session"` → `ChatSource.PI` (add **before/alongside** the Codex `session_meta` check — distinct type values). `_convert_pi_to_dict()`. Parse dispatch: `source==PI` → `parse_pi_session_file` + `extract_pi_messages`. `get_project_chat_files`/scatter dispatch for PI (absolute paths). |
| [src/cli.py](../../src/cli.py) | `_source_label()` → `"[Pi]   "`; `_source_icon()` → `"🥧 Pi"`; `_detect_available_sources()` adds pi; list + count dispatch branches. |
| [src/auto_exporter.py](../../src/auto_exporter.py) | Add `ChatSource.PI: "Pi"` to the label map. (Auto-export matching works via existing `workspace_path`/cwd strategy — **no** `project_matcher.py` change.) |
| [claude-chat-manager.py](../../claude-chat-manager.py) | `--source pi` examples in the help epilog. |
| [.env.example](../../.env.example) | Document `PI_DATA_DIR`. |
| [docs/ARCHITECTURE.md](../ARCHITECTURE.md) | New §4.2.x "Data Layer (Pi Coding Agent)"; add pi to stability zones + status line. |
| [README.md](../../README.md) | Add pi to source list, `--source pi` usage, data-dir docs. |
| [docs/PI_IMPLEMENTATION.md](../PI_IMPLEMENTATION.md) | New implementation guide (like `CODEX_IMPLEMENTATION.md`). |

### 5.4 `_detect_chat_source` disambiguation (critical)

In the `.jsonl` branch of `_detect_chat_source`, the first-line `type` distinguishes all
three JSONL sources cleanly:

| First-line `type` | Source |
| --- | --- |
| `"session"` (+ has `version`/`cwd`) | **Pi** |
| `"session_meta"` | Codex |
| `"message"` / other (or per-line message objects) | Claude Desktop |

Add the pi check first; fall through to the existing Codex/Claude logic.

---

## 6. Feature B — Wingman title sync (detailed design)

### 6.1 The wingman index (owned by sqowe-wingman)

File: `~/.pi/agent/sessions/.wingman-titles.json`. Schema **v1**, keyed by pi session uuid:

```jsonc
{
  "version": 1,
  "titles": {
    "019eef5f-c83f-7f83-ba2a-29f541999380": {
      "title": "Phase 0 implementation",
      "source": "manual",          // "manual" | "llm"
      "generatedAt": "2026-06-28T09:56:57.545Z"
    }
  }
}
```

For `source:"llm"` entries, wingman's schema also carries `model`, `generatedAt`, and
`sourceMsgCount` (used for its staleness checks). We populate all three.

> **Why this is the right place.** Wingman's own design defers LLM titles (its §9) because
> pi exposes no clean raw-completion path and generating from inside the extension would
> pollute a session or re-implement model plumbing. Claude Chat Manager already has the LLM
> plumbing ([llm_client.py](../../src/llm_client.py) → OpenRouter) and never touches pi's
> `.jsonl`, so writing the title from here satisfies wingman's deferred Phase 2 cleanly.
> Wingman explicitly anticipates external/concurrent writers (its design §9.2-7).

### 6.2 `src/pi_title_index.py` (new)

```python
DEFAULT_INDEX = {"version": 1, "titles": {}}

def title_index_path(pi_data_dir: Path) -> Path:
    return pi_data_dir / "sessions" / ".wingman-titles.json"

def load_title_index(path: Path) -> dict:
    # Missing OR corrupt JSON -> deep copy of DEFAULT_INDEX. Never raises.

def upsert_llm_title(
    path: Path, session_id: str, title: str, model: str, msg_count: int,
    now: Callable[[], str] = _utc_now_iso,
) -> bool:
    # 1. load (read-modify-MERGE — preserve version + all other entries)
    # 2. existing = titles.get(session_id)
    # 3. if existing and existing.get("source") == "manual": return False  (guard)
    # 4. titles[session_id] = {title, source:"llm", model,
    #                          generatedAt: now(), sourceMsgCount: msg_count}
    # 5. atomic write: tempfile in same dir + os.replace(); return True
    # Any exception -> log warning, return False (NEVER break the export).
```

- **Atomic + merge:** load fresh, mutate the dict, write to a temp file in the same
  directory, `os.replace()` over the target. This tolerates a concurrently-rewritten file
  and never drops another writer's entries that were present at load time.
- **Injected `now`** for deterministic tests.
- **`title` is the raw LLM string** (spaces, punctuation) — *not* the slugified filename.

### 6.3 Config

[src/config.py](../../src/config.py): `PI_WRITE_WINGMAN_TITLES` (bool env, **default
`False`**), exposed as `config.pi_write_wingman_titles`. The index path derives from
`config.pi_data_dir`.

### 6.4 Hooks (book + wiki)

Both fire **only when** `config.pi_write_wingman_titles` **and** the session is pi.

- **Book:** [src/exporters.py `_generate_book_filename`](../../src/exporters.py) — right
  after `title = llm_client.generate_chat_title(excerpt, …)` and **before** slugification,
  call `upsert_llm_title(...)` with the raw `title`. Thread the pi `session_id` (header
  `id`) and message count into this call site (carried from the parsed session / the
  source+file context already available to `export_project_chats`).
- **Wiki:** [src/wiki_generator.py `_generate_title_with_llm`](../../src/wiki_generator.py)
  — same insertion after the `generate_chat_title` call.

The `session_id` and `msg_count` come from the pi session metadata; both export paths
already know the source and the chat file, so the plumbing is: pass `ChatSource` + the pi
`session_id` (parsed from the header) + `len(messages)` down to the title hook.

`.env.example` documents `PI_WRITE_WINGMAN_TITLES` (off by default; note it writes a file
owned by sqowe-wingman).

---

## 7. Testing plan

All tests under `tests/` (pytest), mirroring `test_codex_parser.py` /
`test_codex_projects.py`.

**`tests/test_pi_parser.py`**
- header parse (id/cwd/version/timestamp); rejects non-`session` first line.
- `normalize_pi_content`: bare string; array of text blocks; mixed text+thinking+toolCall
  (only text kept); image-only → empty.
- `parse_pi_session_file`: keeps user+assistant, skips tool/lifecycle entries; tolerates a
  malformed line without aborting; `extract_pi_messages` sets `source=PI`,
  `execution_id=session_id`, drops empties.

**`tests/test_pi_projects.py`**
- discovery groups by cwd; `last_modified` = newest header; sorted newest-first; ignores
  non-session files; empty/absent dir → `[]`.

**`tests/test_pi_title_index.py`**
- `load_title_index`: missing file → default; corrupt JSON → default (no throw).
- `upsert_llm_title`: writes llm entry with injected `now` + model + sourceMsgCount;
  **manual guard** (existing `source:"manual"` → returns `False`, file unchanged);
  **llm refresh** (existing `source:"llm"` → overwritten);
  **merge** (other sessions' entries + `version` preserved);
  atomic write leaves no partial file on simulated failure.

**Integration / regression**
- `tests/test_cli_source_flag.py`: `--source pi` parses to `ChatSource.PI`; invalid stays
  rejected.
- Keep the full existing suite green; run `pytest`, `mypy`, `black` (per
  [docs/DEVELOPMENT.md](../DEVELOPMENT.md)).

---

## 8. File-by-file checklist

**Feature A**

| File | New? | Change |
| --- | --- | --- |
| `src/pi_parser.py` | ✅ new | `PiSession`, header/full parse, normalize, extract |
| `src/pi_projects.py` | ✅ new | `PiSessionInfo`, `PiWorkspace`, discover, get-files |
| `src/models.py` | edit | `ChatSource.PI = "pi"` |
| `src/config.py` | edit | `_pi_dir`, `pi_data_dir`, `validate_pi_directory()`, `PI_DATA_DIR` |
| `src/cli_utils.py` | edit | `SOURCE_CHOICES` + `parse_source_filter` |
| `src/projects.py` | edit | discovery/search/get-files + `_pi_workspace_to_project_info` |
| `src/parser.py` | edit | `count_pi_messages_in_file` |
| `src/exporters.py` | edit | detect + convert + parse + scatter dispatch |
| `src/cli.py` | edit | label/icon/detect + list/count dispatch |
| `src/auto_exporter.py` | edit | `ChatSource.PI: "Pi"` label |
| `claude-chat-manager.py` | edit | `--source pi` help |
| `.env.example` | edit | `PI_DATA_DIR` |
| `docs/ARCHITECTURE.md` | edit | §4.2.x + stability zones |
| `README.md` | edit | pi usage |
| `docs/PI_IMPLEMENTATION.md` | ✅ new | implementation guide |
| `tests/test_pi_parser.py` | ✅ new | parser tests |
| `tests/test_pi_projects.py` | ✅ new | projects tests |

**Feature B**

| File | New? | Change |
| --- | --- | --- |
| `src/pi_title_index.py` | ✅ new | load/upsert/atomic-merge + path helper |
| `src/config.py` | edit | `PI_WRITE_WINGMAN_TITLES` (default off) |
| `src/exporters.py` | edit | hook in `_generate_book_filename` |
| `src/wiki_generator.py` | edit | hook in `_generate_title_with_llm` |
| `.env.example` | edit | document `PI_WRITE_WINGMAN_TITLES` |
| `tests/test_pi_title_index.py` | ✅ new | index tests |

---

## 9. AI.md / ARCHITECTURE compliance

- New modules well under **800 lines**; PEP8; **type hints** + Google-style **docstrings**.
- Reuse the **`exceptions.py`** hierarchy (`ChatFileNotFoundError`, `InvalidChatFileError`,
  `ExportError`); use **`logging`** (no `print`); **no hardcoded paths** (all via `config`).
- Tests in **`tests/`**, docs in **`docs/`** (except README); logs in `logs/`.
- Additive changes to **Stable** zones (`models.py`, `config.py`, `parser.py`) per
  ARCHITECTURE §7 ("changes should be additive only").
- **Flagged conflict (ARCHITECTURE §8):** Feature B writes a file **owned by another
  project** (sqowe-wingman). Approved by the user; uses wingman's documented v1 schema and
  its anticipated external-writer path. Guarded (never overwrites manual) and fully
  fail-safe (never breaks an export).

---

## 10. Sequencing & rollout

1. **Feature A** — implement parser + projects + all wiring; add tests; run
   `pytest`/`mypy`/`black`; update ARCHITECTURE/README/PI_IMPLEMENTATION.
2. **Verify A** standalone: `--source pi -l`, interactive browse, book/wiki/markdown export,
   auto-export dry-run.
3. **Feature B** — add `pi_title_index.py` + config flag (off) + book/wiki hooks + tests.
4. **Verify B** with `PI_WRITE_WINGMAN_TITLES=true`: export a pi project with LLM titles;
   confirm `.wingman-titles.json` gains `source:"llm"` entries, a pre-existing
   `source:"manual"` entry is untouched, and other entries + `version` are preserved.

---

## 11. Open questions

None blocking. Resolved decisions are captured in §4. Future considerations (not in scope):
- Tree/branch-aware export (currently file-order linear, matching Codex/Cline).
- A generic title-map writer for non-pi sources (would need per-source key schemes).
- Staleness-driven re-titling (wingman owns that policy via `sourceMsgCount`).

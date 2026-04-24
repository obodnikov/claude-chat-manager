# Auto-Export Guide

Automate the full chat export pipeline — discover conversations across all sources, match them to project folders on disk, export, and merge into each project's `docs/chats/` directory with a single command.

## Quick Start

```bash
# First time: build the mapping config interactively
python3 auto-export.py --root ~/src --learn

# Preview what would happen (safe, no writes)
python3 auto-export.py --root ~/src --dry-run

# Execute the full pipeline
python3 auto-export.py --root ~/src
```

## Prerequisites

- Python 3.9+
- At least one chat source populated:
  - Claude Desktop: `~/.claude/projects/`
  - Kiro IDE: OS-specific globalStorage path
  - Codex CLI: `~/.codex/sessions/`
- A root directory where your project folders live (e.g. `~/src`, `~/code`)

## What It Does

The utility runs a three-stage pipeline:

1. **Discover** — lists every conversation project across Claude Desktop, Kiro IDE, and Codex CLI using the existing `list_all_projects()` machinery.
2. **Match** — maps each conversation project to a filesystem folder under `--root`, using cached mappings when available.
3. **Export + Merge** — exports chats to a temporary directory, then uses `ChatMerger` to intelligently merge them into each project's `docs/chats/` folder (no duplicates, no overwrites of more-complete versions).

Multiple sources that resolve to the same folder (e.g. a Claude project and a Kiro workspace both tied to `~/src/my-app`) are grouped and merged together.

## Learn Mode (First Time Setup)

Before the pipeline can run, it needs to know which conversation project maps to which filesystem folder. Run `--learn` once to build that mapping interactively.

```bash
python3 auto-export.py --root ~/src --learn
```

Example session:

```
🔍 Learning project mappings...

Root directory: /Users/mike/src (15 project folders found)
Conversation projects: 8 (Claude: 4, Kiro: 3, Codex: 1)

[1/8] Users-Mike-Src-Claude-Chat-Manager [Claude]
  Auto-matched: ~/src/claude-chat-manager/docs/chats/ (claude_path_decode)
  Docs target:  ~/src/claude-chat-manager/docs/chats/ (found, 16 files)
  → Confirm? [Y/n/custom/skip]: y
  ✅ Confirmed

[2/8] claude-chat-manager [Kiro]
  Auto-matched: ~/src/claude-chat-manager/docs/chats/ (workspace_path)
  → Same target as previous mapping.
  → Confirm? [Y/n]: y
  ✅ Confirmed (merged with existing mapping)

[3/8] random-experiment [Claude]
  ⚠️  No match found in /Users/mike/src/
  → Enter folder name, 'skip', or press Enter for skip: skip
  ⏭️  Skipped
...

📋 Mapping Summary
══════════════════════════════════════════════════
  ✅ Mapped:  6 projects → 4 folders
  🔗 Merged:  2 projects (multiple sources → same folder)
  ⏭️  Skipped: 2 projects
  Config saved: /Users/mike/.config/claude-chat-manager/project-mapping.json
══════════════════════════════════════════════════
```

### Per-Project Answers

At each prompt you can:

| Input | Action |
|-------|--------|
| `y` or Enter | Accept the auto-matched mapping |
| `n` / `skip` / `s` | Skip this project (will not be exported) |
| Custom folder name | Override: map to `<root>/<folder>/` instead |

Custom folder names are validated to stay inside `--root` (no `..` escapes, no absolute paths). If the folder doesn't exist yet, you'll be asked whether to create it on first export.

### Re-Learning

As you add new conversation projects or rename folders, re-run learn mode to pick them up:

```bash
# Update: keep existing confirmed mappings, prompt only for new ones
python3 auto-export.py --root ~/src --learn --update

# Fresh start: re-confirm every mapping
python3 auto-export.py --root ~/src --learn
```

## Running Auto-Export

Once a mapping config exists, execute the full pipeline:

```bash
python3 auto-export.py --root ~/src
```

The pipeline:

1. Loads `~/.config/claude-chat-manager/project-mapping.json`
2. Groups conversation projects by target folder
3. For each target:
   - Exports all mapped sources to a temp directory (book format by default)
   - Merges temp files into the target `docs/chats/` using `ChatMerger` in auto mode
4. Prints a per-target summary with new/updated/skipped counts
5. Cleans up the temp directory (unless `--keep-tmp` is set)

### Filtering

```bash
# Only process one source
python3 auto-export.py --root ~/src --source kiro

# Use markdown format instead of book
python3 auto-export.py --root ~/src --format markdown

# Keep the temp export directory for inspection
python3 auto-export.py --root ~/src --keep-tmp

# Verbose logging
python3 auto-export.py --root ~/src -v
```

## Dry Run

Preview the plan before touching anything on disk:

```bash
python3 auto-export.py --root ~/src --dry-run
```

Output shows, per target:

- Source projects contributing to it
- Number of chats that would be exported
- Number of existing files in the target
- Estimated new / updated / skipped files

No files are written. Use this to verify mappings before a real run.

## CLI Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--root`, `-r` | **required** | Root directory containing project folders |
| `--learn` | off | Interactive mode: build/update mapping config |
| `--update` | off | With `--learn`: keep existing confirmed mappings |
| `--dry-run` | off | Preview mode: show plan without executing |
| `--source` | `all` | Filter: `claude`, `kiro`, `codex`, or `all` |
| `--config` | `~/.config/claude-chat-manager/project-mapping.json` | Path to mapping config |
| `--format` | `book` | Export format: `book` or `markdown` |
| `--keep-tmp` | off | Don't clean up temporary export directory |
| `-v`, `--verbose` | off | Enable debug logging |

## Configuration File

### Location

Default: `~/.config/claude-chat-manager/project-mapping.json`

Override order (highest wins):

1. `--config path/to/mapping.json`
2. `AUTO_EXPORT_CONFIG=/path/to/mapping.json` environment variable
3. Default path above

### Schema

```json
{
  "version": "1.0",
  "root_directory": "/Users/mike/src",
  "defaults": {
    "export_format": "book",
    "unmatched_action": "skip"
  },
  "mappings": {
    "claude:Users-Mike-Src-Claude-Chat-Manager": {
      "source_name": "Users-Mike-Src-Claude-Chat-Manager",
      "target": "claude-chat-manager",
      "docs_chats_path": "docs/chats",
      "action": "export",
      "confirmed": true,
      "match_method": "claude_path_decode",
      "source_type": "claude",
      "workspace_path": null
    },
    "kiro:claude-chat-manager": {
      "source_name": "claude-chat-manager",
      "target": "claude-chat-manager",
      "docs_chats_path": "docs/chats",
      "action": "export",
      "confirmed": true,
      "match_method": "workspace_path",
      "source_type": "kiro",
      "workspace_path": "/Users/mike/src/claude-chat-manager"
    },
    "claude:random-experiment": {
      "source_name": "random-experiment",
      "action": "skip",
      "confirmed": true,
      "match_method": "user_skip",
      "source_type": "claude"
    }
  },
  "last_learned": "2026-04-24T10:30:00"
}
```

### Key Format

Mapping keys are **source-qualified**: `<source>:<project_name>`. This prevents a Claude project named `my-app` from silently overwriting a Kiro workspace with the same name.

### Manual Editing

The config is plain JSON — safe to edit by hand. Common manual tweaks:

- Flip `"action": "export"` to `"action": "skip"` to exclude a project
- Change `target` to remap to a different folder
- Change `docs_chats_path` to use e.g. `docs/conversations` instead of `docs/chats`
- Set `"confirmed": false` to force re-prompting in `--learn --update`

Run `--dry-run` after manual edits to verify.

## Matching Strategy

When a project isn't already in the config, the matcher tries these methods in order:

1. **Workspace path exact match** (Kiro/Codex) — `workspace_path` / `cwd` resolves to a folder under `--root`
2. **Claude path decode** — `Users-Mike-Src-My-Project` decoded to path segments, matched tail-first against root subdirectories
3. **Basename exact match** — case-insensitive folder name comparison
4. **Fuzzy match** — token similarity on `-`/`_`/case boundaries, threshold ≥ 0.8
5. **No match** — falls through to user prompt in learn mode

The `match_method` field in the config records which strategy was used, for debugging.

### Claude Name Decoding

Claude Desktop encodes project paths as directory names separated by `-`:

```
Users-Mike-Src-Claude-Chat-Manager
  → path segments: [Users, Mike, Src, Claude-Chat-Manager]
  → matched against: /Users/mike/src/claude-chat-manager/
```

The matcher tries progressively shorter tails (last N segments) and picks the longest match.

### Docs/Chats Directory Detection

Once a project folder is matched, the matcher looks for the chat output directory in this order:

1. `docs/chats/`
2. `docs/conversations/`
3. `chats/`
4. Any subdirectory containing `.md` files that look like chat exports (fingerprint scan)
5. Default to `docs/chats/` (created on first export)

## Multi-Source Grouping

Multiple conversation projects can map to the same target folder. The pipeline groups them so exports don't overwrite each other:

```
Target: ~/src/claude-chat-manager/docs/chats/
  Sources:
    - [Claude] Users-Mike-Src-Claude-Chat-Manager (12 chats)
    - [Kiro]   claude-chat-manager (5 chats)
    - [Codex]  claude-chat-manager (3 chats)

  Step 1: Export all 20 chats to tmp/claude-chat-manager/
  Step 2: Merge tmp/claude-chat-manager/ → ~/src/claude-chat-manager/docs/chats/
  Result: 4 new, 1 updated, 15 skipped
```

`ChatMerger` uses content fingerprinting (not filenames), so LLM-generated titles that differ between sources don't cause duplicates.

## Troubleshooting

### "No mapping config found. Run --learn first"

The config file doesn't exist at the expected path. Run `--learn` to create it, or point at an existing one with `--config`.

### A project was skipped that I wanted to export

Edit the config and change `"action": "skip"` to `"action": "export"`, then add a `target` and `docs_chats_path`. Or re-run `--learn --update` and set `"confirmed": false` for that entry first.

### Wrong folder matched

Two fixes:

- Edit the config directly — change the `target` field
- Run `--learn` without `--update` and provide a custom folder name when prompted

### Merge didn't pick up my new chats

`ChatMerger` uses content fingerprinting from the first ~3 message pairs. If a new chat is nearly identical to an existing one, it may be classified as "skip" or "update" rather than "new". Check the merge action counts in the output, and run with `-v` for verbose logging.

### Temp files left behind

If a run crashes, the temp directory may stick around. It's created via `tempfile.mkdtemp()` under the system temp location. Use `--keep-tmp` intentionally for debugging, otherwise let the tool manage cleanup.

### Config file corrupted

The loader validates JSON on read. If the file is malformed, back it up and re-run `--learn` to regenerate.

## Examples

### First-Time Setup

```bash
# Build the mapping config for all projects under ~/src
python3 auto-export.py --root ~/src --learn

# Preview the plan
python3 auto-export.py --root ~/src --dry-run

# Run the real thing
python3 auto-export.py --root ~/src
```

### Regular Usage

After setup, a single command updates every project:

```bash
python3 auto-export.py --root ~/src
```

### Adding a New Project

After creating a new project folder and starting conversations:

```bash
python3 auto-export.py --root ~/src --learn --update
# → Only new/unconfirmed projects prompt; confirmed ones are kept as-is
```

### Changing Target Directories

To move a project's chat output to a different folder, edit the mapping config:

```json
"kiro:my-project": {
  "target": "archived/my-project",
  "docs_chats_path": "docs/chats",
  ...
}
```

Then re-run the pipeline. `ChatMerger` will treat the new folder as empty and copy everything fresh.

### Using a Custom Config Path

```bash
# Per-run
python3 auto-export.py --root ~/src --config ./mapping.json --dry-run

# Session-wide
export AUTO_EXPORT_CONFIG=~/my-mappings/work.json
python3 auto-export.py --root ~/work
```

## See Also

- [docs/MERGE_CHATS.md](MERGE_CHATS.md) — the `ChatMerger` used under the hood
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — where auto-export fits in the system
- [docs/AUTO_EXPORT_PLAN.md](AUTO_EXPORT_PLAN.md) — the original design doc

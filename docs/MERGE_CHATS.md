# Chat Merge Utility

**merge-chats.py** - Intelligently merge exported chat files from different sources, avoiding duplicates and handling incomplete conversations.

## Overview

When working with Claude chat exports across multiple computers, you often end up with:
- **Same conversations with different filenames** (due to LLM-generated titles)
- **Incomplete versions** (conversation continued on another machine)
- **True duplicates** (identical content)

The merge utility solves this by using **content-based fingerprinting** to detect duplicates and intelligently merge only new or updated conversations.

## Features

✅ **Content Fingerprinting** - Identifies conversations by content, not filename
✅ **Smart Deduplication** - Detects identical conversations regardless of filename
✅ **Incomplete Detection** - Finds and updates incomplete conversations
✅ **Three Modes** - Preview, Interactive, or Automatic
✅ **Safety Features** - Backups, dry-run, detailed reports
✅ **Configurable** - Adjust similarity thresholds and fingerprint depth

## Installation

The utility is included with Claude Chat Manager:

```bash
cd claude-chat-manager
chmod +x merge-chats.py
```

No additional dependencies required - uses only Python standard library.

## Usage

### Basic Syntax

```bash
python merge-chats.py --source SOURCE_DIR --target TARGET_DIR [mode] [options]
```

**Parameters:**
- `--source` / `-s`: Directory with newly exported chats
- `--target` / `-t`: Directory with existing chats (e.g., `docs/chats/`)
- **Mode** (required): One of `--preview`, `--interactive`, or `--auto`

### Modes

#### Preview Mode (Recommended First)

Show what would be done without making any changes:

```bash
python merge-chats.py \
  --source ~/exports/MacBook-Air-...-20260130_195936 \
  --target ./docs/chats/ \
  --preview
```

**Output:**
```
🔍 Merge Preview
======================================================================

Source files analyzed: 15

  [✅ NEW] implementing-authentication-system-2025-12-26.md
    → No matching conversation found in target

  [🔄 UPDATE] refactoring-api-endpoints-2025-12-25.md
    → Source has more messages (18 vs 12)
    → Target: old-api-refactoring-2025-12-25.md

  [⏭️  SKIP] setting-up-testing-infrastructure-2025-12-20.md
    → Identical conversation already exists
    → Target: pytest-setup-guide-2025-12-20.md

======================================================================
Summary:
  ✅ NEW: 5 conversations (will copy)
  🔄 UPDATE: 3 conversations (will replace)
  ⏭️  SKIP: 7 conversations (already exist)
  ⚠️  REVIEW: 0 conversations (need manual check)
======================================================================
```

#### Interactive Mode

Review and approve each action:

```bash
python merge-chats.py \
  --source ~/exports/new/ \
  --target ./docs/chats/ \
  --interactive
```

**Features:**
- Review each file before processing
- Options: `(y)es`, `(n)o`, `(s)kip all`, `(q)uit`
- Safe for first-time use
- Full control over what gets merged

#### Automatic Mode

Merge based on heuristics with optional confirmation:

```bash
python merge-chats.py \
  --source ~/exports/new/ \
  --target ./docs/chats/ \
  --auto \
  --backup
```

**Features:**
- Processes all NEW and UPDATE actions automatically
- Skips identical files
- Flags similar-but-different for review
- Optional backup creation

## Options

### Similarity Threshold

Control how similar conversations must be to match:

```bash
--similarity 0.9    # Stricter matching (default: 0.8)
--similarity 0.7    # More lenient matching
```

**Range:** 0.0 (no match) to 1.0 (exact match)
**Default:** 0.8 (80% similarity)

### Fingerprint Depth

Number of message pairs used for fingerprinting:

```bash
--fingerprint-messages 5    # Use first 5 pairs (default: 3)
--fingerprint-messages 2    # Faster but less accurate
```

**Default:** 3 message pairs (6 messages total)

### Backup Control

```bash
--backup          # Create .md.backup before overwriting
--no-backup       # Don't create backups (faster)
```

**Default:** Backups enabled for `--auto` and `--interactive`, disabled for `--preview`

### Report Generation

Generate detailed markdown report:

```bash
--report merge-report.md
```

**Report includes:**
- Summary statistics
- Detailed list of all actions
- Message counts and similarity scores
- Reasons for each decision

### Verbose Output

Enable debug logging:

```bash
--verbose    # or -v
```

Shows detailed information about fingerprint extraction, matching, and decisions.

## How It Works

### 1. Content Fingerprinting

For each file, the utility:
1. Extracts the first N message pairs (user + assistant, default N=3)
2. Cleans and normalizes the content (removes formatting, excessive whitespace)
3. Creates a hash from the combined text
4. Stores both the hash and the full fingerprint text
5. Stores message count and first user question for metadata

### 2. Similarity Calculation

When comparing files:
1. Check hash for exact match (fast path for identical conversations)
2. If no exact match, calculate text similarity using **difflib.SequenceMatcher**
3. Apply Ratcliff/Obershelp pattern matching on **full fingerprint text** (all N message pairs)
4. Return similarity score (0.0 to 1.0)

**Why full fingerprint text, not just first message?**

Previous versions only compared the first user message (200 chars), which caused:
- **False positives**: "How do I implement authentication?" vs "How do I implement authorization?" → 90% similar but different topics
- **False negatives**: Different phrasings of the same question might score too low

By using the **full fingerprint text** (first N message pairs):
- ✅ Catches conversations that start similarly but diverge later
- ✅ Reduces false positives from similar opening instructions
- ✅ More comprehensive comparison (default: 6 messages vs 1 message)
- ✅ Better accuracy in detecting true duplicates

**Algorithm Benefits:**
- Handles reordered text (e.g., "auth system" vs "system auth")
- Detects typos and variations (e.g., "impliment" vs "implement")
- Manages insertions/deletions (e.g., "user auth" vs "secure user auth")
- More accurate than simple character position matching
- Uses same content that created the hash (consistency)

### 3. Decision Logic

For each source file:

```
IF no match found:
    → ACTION: NEW (copy to target)

ELSE IF exact match (hash identical, same message count):
    → ACTION: SKIP (already exists)

ELSE IF source has MORE messages:
    → ACTION: UPDATE (replace target with longer version)

ELSE IF target has MORE messages:
    → ACTION: SKIP (keep complete version)

ELSE IF similarity < threshold:
    → ACTION: REVIEW (manual check needed)

ELSE:
    → ACTION: SKIP (already exists)
```

## Examples

### Example 1: Initial Sync

First time merging exports from a different computer:

```bash
# 1. Preview what will happen
python merge-chats.py \
  --source ~/Desktop/exports-from-laptop/ \
  --target ./docs/chats/ \
  --preview

# 2. Review output, then merge interactively
python merge-chats.py \
  --source ~/Desktop/exports-from-laptop/ \
  --target ./docs/chats/ \
  --interactive \
  --backup
```

### Example 2: Regular Updates

Merging new exports from the same machine:

```bash
# Use automatic mode with report
python merge-chats.py \
  --source ~/exports/latest/ \
  --target ./docs/chats/ \
  --auto \
  --backup \
  --report weekly-merge.md
```

### Example 3: High-Precision Matching

When you have very similar conversations on different topics:

```bash
# Increase similarity threshold and fingerprint depth
python merge-chats.py \
  --source ~/exports/new/ \
  --target ./docs/chats/ \
  --auto \
  --similarity 0.9 \
  --fingerprint-messages 5
```

### Example 4: Quick Check

Fast preview without detailed analysis:

```bash
python merge-chats.py \
  --source ~/exports/new/ \
  --target ./docs/chats/ \
  --preview \
  --fingerprint-messages 2
```

## Typical Workflow

### Scenario: Syncing Chats from Multiple Computers

You work on two machines: **Desktop** and **Laptop**. You want to merge all conversations into a single `docs/chats/` directory in your project repository.

**Step 1: Export from Desktop**

```bash
# On Desktop
cd ~/src/my-project
python claude-chat-manager.py "My Project" -f book -o ~/exports/desktop-20260130
```

**Step 2: Export from Laptop**

```bash
# On Laptop
cd ~/src/my-project
python claude-chat-manager.py "My Project" -f book -o ~/exports/laptop-20260130
```

**Step 3: Copy laptop exports to Desktop**

```bash
# Transfer via USB, network, or cloud storage
scp -r laptop:~/exports/laptop-20260130 ~/exports/
```

**Step 4: Merge on Desktop**

```bash
# Preview both merges
python merge-chats.py --source ~/exports/desktop-20260130 --target docs/chats/ --preview
python merge-chats.py --source ~/exports/laptop-20260130 --target docs/chats/ --preview

# Merge desktop exports first
python merge-chats.py --source ~/exports/desktop-20260130 --target docs/chats/ --auto --backup

# Merge laptop exports (will detect duplicates)
python merge-chats.py --source ~/exports/laptop-20260130 --target docs/chats/ --auto --backup
```

**Result:**
- New conversations from both machines: **copied** ✅
- Incomplete conversations: **updated** with longer version 🔄
- Duplicates: **skipped** automatically ⏭️

## Limitations

### What the Utility Does NOT Do

❌ **Merge partial conversations into one file** - It replaces files, not merges content
❌ **Detect conversations split across multiple files** - Each file analyzed independently
❌ **Handle non-markdown files** - Only processes `.md` files
❌ **Modify file content** - Files copied as-is, no content changes

### Edge Cases

**Same beginning, different continuation:**
- If two conversations start identically but diverge, similarity might be high
- Use `--similarity 0.9` or higher for stricter matching
- Review mode will flag these for manual inspection

**Very short conversations:**
- Short chats (1-2 messages) may have false matches
- Consider using `--fingerprint-messages 1` for short chats
- Or manually review short files

## Troubleshooting

### "No markdown files found in source directory"

**Cause:** Source directory doesn't contain `.md` files
**Solution:** Verify you're pointing to the correct export directory

```bash
ls ~/exports/your-export-dir/*.md
```

### "All files marked as SKIP"

**Cause:** All conversations already exist in target
**Solution:** This is expected if you've already merged these files

### "Too many REVIEW actions"

**Cause:** Similarity threshold too low or conversations very similar
**Solution:**
1. Increase threshold: `--similarity 0.9`
2. Increase fingerprint depth: `--fingerprint-messages 5`
3. Manually inspect flagged files

### High similarity but different message counts

**Cause:** Conversation continued on another machine
**Solution:** This is expected - the tool will UPDATE with the longer version

## Advanced Usage

### Custom Similarity Function

For advanced users, you can modify the similarity calculation in [src/chat_merger.py:296](../src/chat_merger.py#L296):

```python
def _levenshtein_similarity(self, s1: str, s2: str) -> float:
    # Your custom similarity algorithm
    pass
```

### Batch Processing

Process multiple export directories:

```bash
#!/bin/bash
for dir in ~/exports/*/; do
    echo "Processing $dir"
    python merge-chats.py --source "$dir" --target ./docs/chats/ --auto --backup
done
```

### Integration with Git

Automatic commit after merge:

```bash
# Merge and commit
python merge-chats.py --source ~/exports/new/ --target ./docs/chats/ --auto --report merge.md

# Review changes
git status
git diff docs/chats/

# Commit if satisfied
git add docs/chats/
git commit -m "Merge new chat exports (see merge.md for details)"
```

## Performance

**Typical Performance:**
- **100 files**: ~1-2 seconds
- **1000 files**: ~10-15 seconds
- **10000 files**: ~2-3 minutes

**Optimization tips:**
- Use `--fingerprint-messages 2` for faster processing
- Process in batches if you have thousands of files
- Use `--preview` first to avoid processing unnecessary files

## Testing

Run the test suite:

```bash
# Run all merger tests
pytest tests/test_chat_merger.py -v

# Run with coverage
pytest tests/test_chat_merger.py --cov=src.chat_merger

# Run specific test
pytest tests/test_chat_merger.py::TestMergeDecisions::test_decide_update_longer -v
```

**Test coverage:** 94% (147 statements, 9 missed)

## Contributing

To improve the merge utility:

1. **Add new similarity algorithms** - Implement better text matching
2. **Support other formats** - Add support for wiki/markdown variants
3. **Performance optimization** - Parallel processing, caching
4. **Enhanced heuristics** - Better decision logic for edge cases

See [DEVELOPMENT.md](DEVELOPMENT.md) for contribution guidelines.

## Related Tools

- **claude-chat-manager.py** - Export chats in various formats
- **sanitize-chats.py** - Remove sensitive data from exports
- **wiki-generator** - Create single-page wikis from chats

## License

Part of Claude Chat Manager - provided as-is for personal use.

---

**Version:** 1.0.0
**Last Updated:** 2026-01-30
**Author:** Claude Chat Manager Project

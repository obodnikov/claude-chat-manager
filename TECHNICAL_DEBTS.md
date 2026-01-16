# Technical Debts

This document tracks known technical debts and future enhancement opportunities for the Claude Chat Manager project.

## Future Enhancements

### 1. Tool Use Export Format for Kiro Chats

**Priority:** Medium  
**Added:** 2026-01-16  
**Related:** Kiro IDE execution log enrichment feature

**Description:**

Currently, when exporting Kiro chats, we extract full bot text responses from execution logs but only include basic `[Tool: toolName]` markers for tool use blocks. The execution logs contain rich tool use data including:

- Tool input parameters
- Tool execution results
- File modifications
- Command outputs

**Current Behavior:**
```markdown
I'll help you with that.

[Tool: readFile]

Here's what I found in the file...
```

**Proposed Enhancement:**

Create a new export format (e.g., `detailed` or `full`) that includes structured tool use information:

```markdown
I'll help you with that.

**Tool: readFile**
- File: `src/config.py`
- Lines: 1-50

**Result:**
```python
# File content here...
```

Here's what I found in the file...
```

**Implementation Notes:**

1. The execution log structure already contains this data in `messagesFromExecutionId[].entries[]`:
   - `type: "toolUse"` entries have `name`, `input` fields
   - `type: "toolResult"` entries have the tool output

2. Would require:
   - New export format option in CLI (`--format detailed`)
   - Extended `extract_bot_responses_from_execution_log()` to return tool details
   - New formatter for tool use blocks in `formatters.py`
   - Documentation updates

3. Considerations:
   - Tool results can be very large (file contents, command outputs)
   - May need truncation or collapsible sections
   - Should be opt-in to avoid bloating standard exports

**Files to Modify:**
- `src/kiro_parser.py` - Extend extraction functions
- `src/exporters.py` - Add new format option
- `src/formatters.py` - Add tool use formatting
- `claude-chat-manager.py` - Add CLI flag
- `README.md` - Document new format

---

### 2. Execution Log Index Caching

**Priority:** Low  
**Added:** 2026-01-16  
**Related:** Performance optimization for large workspaces

**Description:**

The `build_execution_log_index()` function scans all execution log directories and parses every file to build a mapping from executionId to file path. For large workspaces with many log files, this could be slow.

**Current Behavior:**
- Index is built once per workspace export (not per chat)
- Full scan of all hash-named subdirectories
- Parses each extensionless file to extract executionId

**Proposed Enhancement:**

1. **Module-level caching**: Cache the index at module level with workspace path as key
2. **Incremental updates**: Only scan new files since last index build
3. **Progress logging**: Add progress indicators for large operations
4. **Lazy loading**: Build index on-demand rather than upfront

**Implementation Notes:**

```python
# Example caching approach
_execution_log_cache: Dict[Path, Dict[str, Path]] = {}

def build_execution_log_index(workspace_dir: Path, use_cache: bool = True) -> Dict[str, Path]:
    if use_cache and workspace_dir in _execution_log_cache:
        return _execution_log_cache[workspace_dir]
    
    index = _scan_execution_logs(workspace_dir)
    _execution_log_cache[workspace_dir] = index
    return index
```

**Current Mitigation:**
- Index is already built once per workspace, not per chat
- For typical workspaces, performance is acceptable
- Only becomes an issue with very large workspaces (1000+ execution logs)

---

## Resolved Debts

*None yet*

---

**Document Version:** 1.1  
**Last Updated:** 2026-01-16

# Sensitive Data Sanitization - Implementation Specification

**Status:** Ready for Implementation
**Date:** 2025-12-26
**Version:** 1.0

---

## 📋 Overview

This document specifies the implementation of sensitive data sanitization for Claude Chat Manager. The solution uses a **hybrid architecture** combining integrated sanitization during export with a standalone post-processing script for existing files.

---

## ✅ Confirmed Requirements

### Architecture
- **Hybrid Solution:**
  - Integrated sanitization in book and wiki exports
  - Standalone post-processing script with interactive mode
  - Shared core sanitizer module (`src/sanitizer.py`)
  - Configuration via `.env` file (shared by both approaches)

### Default Configuration
```bash
SANITIZE_ENABLED=false          # Explicit opt-in
SANITIZE_LEVEL=balanced         # Recommended detection level
SANITIZE_STYLE=partial          # Keep first/last chars (e.g., sk-ab***xyz)
SANITIZE_PATHS=false            # Don't sanitize file paths by default
```

### Priority Patterns (Detection Order)

| Priority | Category | Example Patterns | Redaction Example |
|----------|----------|------------------|-------------------|
| 1 | API Keys | `sk-[a-zA-Z0-9]{20,}`, `sk-proj-*`, `sk-or-v1-*`, `ghp_*`, `AKIA*`, `AIza*` | `sk-pr***xyz` |
| 2 | Tokens | `Bearer [A-Za-z0-9._-]{20,}`, JWT format, `xox[baprs]-*` | `Beare***abc` |
| 3 | Password (Context) | `password = "..."`, `passwd: ...`, `pwd = ...`, `secret = ...` | `pass***123` |
| 4 | Environment Variables | `API_KEY=sk-xxx`, `export TOKEN=...`, `SECRET_KEY=...` | `API_KEY=[SECRET]` |

### Post-Processing Script
- **Name:** `sanitize-chats.py`
- **Location:** Project root directory
- **Supported Formats:** `.md` files only (for now)
- **Modes:**
  - Interactive mode (review each match)
  - Batch mode (auto-sanitize)
  - Preview mode (show without applying)

### Integration Scope
- **Phase 1 (Confirmed):**
  - Book format (`export_chat_book()`)
  - Wiki format (`WikiGenerator`)
- **Phase 2 (Future):**
  - Pretty format
  - Markdown format
  - Raw format (optional)

---

## 🎯 Detection Levels

### Minimal
- Only obvious API keys with known patterns
- High-confidence matches only
- Minimal false positives

### Balanced (Default)
- All priority patterns from table above
- Contextual password detection
- Environment variable assignments
- Reasonable balance of coverage vs false positives

### Aggressive
- All balanced patterns
- Generic secret patterns
- Email addresses
- IP addresses (optional)
- More contextual variations
- Higher false positive rate

### Custom
- Use only user-defined patterns
- Ignore built-in pattern library
- Full user control

---

## 🎨 Redaction Styles

### Simple
```
Original: sk-proj-abc123xyz789
Redacted: REDACTED
```

### Stars
```
Original: sk-proj-abc123xyz789
Redacted: **********
```

### Labeled
```
Original: sk-proj-abc123xyz789
Redacted: [API_KEY]
```

### Partial (Default)
```
Original: sk-proj-abc123xyz789
Redacted: sk-pr***789
(Keep first 5 + last 3 characters)
```

### Hash
```
Original: sk-proj-abc123xyz789
Redacted: [a3f4d8c2]
(Consistent hash - same value → same placeholder)
```

---

## 📁 File Structure

### New Files
```
claude-chat-manager/
├── src/
│   └── sanitizer.py              # Core sanitization engine (NEW)
├── tests/
│   └── test_sanitizer.py         # Sanitizer tests (NEW)
├── docs/
│   ├── SANITIZATION_SPEC.md      # This file (NEW)
│   └── SANITIZATION.md           # User guide (NEW - Phase 6)
└── sanitize-chats.py             # Post-processing script (NEW)
```

### Modified Files
```
src/
├── config.py                     # Add sanitize_* properties
├── exporters.py                  # Add sanitization to book export
├── wiki_generator.py             # Add sanitization to wiki
└── cli.py                        # Add --sanitize flags

.env.example                      # Add SANITIZE_* section
README.md                         # Add sanitization examples
```

---

## 🔧 Configuration Options

### Environment Variables (.env)

```bash
# ============================================================================
# Sensitive Data Sanitization Settings
# ============================================================================

# Enable sanitization for exports (default: false)
SANITIZE_ENABLED=false

# Sanitization level (default: balanced)
# Options: minimal, balanced, aggressive, custom
SANITIZE_LEVEL=balanced

# Redaction style (default: partial)
# Options: simple, stars, labeled, partial, hash
SANITIZE_STYLE=partial

# Sanitize file paths (default: false)
# Example: /Users/mike/project → /Users/[USER]/project
SANITIZE_PATHS=false

# Custom patterns (comma-separated regex)
# Example: mycompany-[a-z0-9]+,internal-.*
SANITIZE_CUSTOM_PATTERNS=

# Allowlist patterns - never sanitize (comma-separated regex)
# Default: example\.com,localhost,127\.0\.0\.1
SANITIZE_ALLOWLIST=example\.com,localhost,127\.0\.0\.1

# Generate sanitization report (default: false)
SANITIZE_REPORT=false
```

### CLI Flags

```bash
--sanitize                    # Enable sanitization (override .env)
--sanitize-level LEVEL        # Set level (minimal/balanced/aggressive/custom)
--sanitize-style STYLE        # Set style (simple/stars/labeled/partial/hash)
--sanitize-preview            # Preview what would be sanitized
```

---

## 💻 Usage Examples

### Integrated Export
```bash
# Enable in .env
echo "SANITIZE_ENABLED=true" >> .env

# Export with automatic sanitization
python claude-chat-manager.py "My Project" -f book -o exports/

# Override .env settings
python claude-chat-manager.py "My Project" -f wiki -o wiki.md \
    --sanitize --sanitize-level aggressive --sanitize-style labeled

# Preview mode
python claude-chat-manager.py "My Project" --sanitize-preview
```

### Post-Processing Script
```bash
# Interactive mode - review each match
python sanitize-chats.py exported-chats/ --interactive

# Batch mode - auto-sanitize
python sanitize-chats.py exported-chats/

# Preview only (no changes)
python sanitize-chats.py my-chat.md --preview

# Custom configuration
python sanitize-chats.py exported-chats/ \
    --level aggressive \
    --style labeled \
    --report sanitization-report.txt
```

---

## 📊 Implementation Phases

### Phase 1: Core Sanitizer (Week 1)
- Create `src/sanitizer.py` with pattern detection
- Implement all redaction styles
- Add configuration to `src/config.py`
- Update `.env.example`
- Basic tests (`tests/test_sanitizer.py`)

### Phase 2: Book Format Integration (Week 1-2)
- Modify `export_chat_book()` for sanitization
- Update `export_project_chats()` to pass sanitize parameter
- Test with sample data
- Add sanitization summary to output

### Phase 3: Wiki Format Integration (Week 2)
- Modify `WikiGenerator` class
- Update `export_project_wiki()`
- Test wiki format
- Ensure titles are sanitized

### Phase 4: Post-Processing Script (Week 2-3)
- Create `sanitize-chats.py`
- Implement interactive mode
- Implement batch mode
- Add preview mode
- Test on existing exports

### Phase 5: CLI Integration (Week 3)
- Add `--sanitize` flags to CLI
- Update argument parser
- Add help text
- Integration testing

### Phase 6: Documentation (Week 3)
- Create `docs/SANITIZATION.md` user guide
- Update `README.md` with examples
- Document all patterns and options
- Create migration guide

### Phase 7: Testing & Polish (Week 3-4)
- Comprehensive integration tests
- Performance testing
- User acceptance testing
- Bug fixes and refinements

---

## ✅ Success Criteria

### Functionality
- [x] Detects all priority patterns (API keys, tokens, passwords, env vars)
- [x] All redaction styles work correctly
- [x] Configuration via .env and CLI
- [x] Integrated export sanitization (book + wiki)
- [x] Post-processing script with interactive mode
- [x] Preview mode works
- [x] No false positives on test data
- [x] Allowlist prevents unwanted redactions

### User Experience
- [x] Default disabled (explicit opt-in)
- [x] Clear feedback on sanitization
- [x] Preview mode shows what would change
- [x] Interactive mode provides context
- [x] Backup files created automatically

### Code Quality
- [x] Test coverage >80%
- [x] Type hints on all functions
- [x] Proper error handling
- [x] Performance overhead <10%
- [x] Complete documentation

---

## 🚫 Out of Scope (Future Consideration)

- Email sanitization (can be added later)
- IP address sanitization (optional)
- Credit card detection (not expected in chats)
- File path sanitization beyond usernames
- Support for non-.md formats in post-processor
- Pretty and raw format integration
- Web-based sanitization preview UI
- Machine learning-based detection

---

## 🔒 Security Considerations

### Pattern Design
- Patterns designed to minimize false negatives (missing real secrets)
- Balanced approach to avoid excessive false positives
- Allowlist system for known-safe patterns
- Custom patterns for organization-specific secrets

### Data Handling
- No sensitive data logged or stored
- Original files backed up before modification
- Sanitization happens in-memory
- No network calls during sanitization

### User Control
- Explicit opt-in (disabled by default)
- Preview mode for verification
- Interactive mode for manual review
- Allowlist for exceptions

---

## 📝 Pattern Reference

### API Key Patterns
```regex
sk-[a-zA-Z0-9]{20,}              # Generic Anthropic/OpenAI
sk-proj-[a-zA-Z0-9_-]{20,}       # OpenAI project keys
sk-or-v1-[a-zA-Z0-9_-]{20,}      # OpenRouter
ghp_[a-zA-Z0-9]{36}              # GitHub personal access token
gho_[a-zA-Z0-9]{36}              # GitHub OAuth token
ghs_[a-zA-Z0-9]{36}              # GitHub server token
AKIA[0-9A-Z]{16}                 # AWS access key ID
AIza[0-9A-Za-z_-]{35}            # Google API key
```

### Token Patterns
```regex
Bearer\s+[A-Za-z0-9._-]{20,}                              # Bearer tokens
eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*     # JWT
xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}   # Slack tokens
```

### Contextual Patterns
```regex
(?i)password\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?        # password = "..."
(?i)passwd\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?          # passwd: ...
(?i)pwd\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?             # pwd = ...
(?i)secret\s*[=:]\s*["\']?([^"\'\s]{8,})["\']?          # secret = ...
```

### Environment Variable Patterns
```regex
(?i)(API_KEY|SECRET_KEY|AUTH_TOKEN|PASSWORD)\s*=\s*["\']?([^"\'\s]{8,})["\']?
export\s+([A-Z_]+)\s*=\s*["\']?([^"\'\s]{8,})["\']?
```

### Default Allowlist
```regex
example\.com                     # Example domains
localhost                        # Local development
127\.0\.0\.1                     # Localhost IP
0\.0\.0\.0                       # All interfaces
sk-[x]{20,}                      # Placeholder keys (sk-xxxx...)
xxx+                             # Generic xxx placeholders
\*\*\*+                          # Already redacted (*****)
your-api-key-here                # Common placeholder text
insert-key-here                  # Common placeholder text
```

---

## 🎓 Testing Strategy

### Unit Tests
- Pattern matching accuracy
- Redaction style correctness
- Configuration loading
- Allowlist functionality
- Edge cases (empty strings, special chars)

### Integration Tests
- Book format export with sanitization
- Wiki format export with sanitization
- Post-processing script modes
- CLI flag handling
- Configuration overrides

### Performance Tests
- Large file processing (<10% overhead target)
- Batch processing multiple files
- Memory usage profiling

### User Acceptance Tests
- Real-world chat samples (anonymized)
- False positive validation
- Interactive mode usability
- Documentation clarity

---

## 📞 Support & Maintenance

### Issue Tracking
- GitHub issues for bug reports
- Feature requests for new patterns
- Community pattern contributions

### Version Updates
- Pattern library updates as new services emerge
- Performance optimizations
- Security improvements
- Documentation enhancements

---

## 🎯 Next Steps

**CONFIRMED AND READY FOR IMPLEMENTATION**

All open questions have been resolved. Proceed with:

1. **Phase 1:** Create core sanitizer module
2. **Regular check-ins:** Review progress after each phase
3. **Feedback loop:** Adjust based on testing results
4. **Documentation:** Keep docs updated as implementation progresses

---

**Document Status:** ✅ APPROVED - Ready for Implementation
**Last Updated:** 2025-12-26
**Approved By:** User Confirmation
**Implementation Start:** Phase 1 - Core Sanitizer Module

# Sensitive Data Sanitization Guide

**Version:** 1.0
**Last Updated:** 2025-12-26

---

## 📋 Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Sanitization Levels](#sanitization-levels)
- [Redaction Styles](#redaction-styles)
- [What Gets Detected](#what-gets-detected)
- [Post-Processing Tool](#post-processing-tool)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

The sanitization feature automatically detects and redacts sensitive information from chat exports, including:

- **API Keys** (OpenAI, Anthropic, GitHub, AWS, Google, etc.)
- **Authentication Tokens** (Bearer tokens, JWTs, Slack tokens)
- **Passwords** (contextual detection)
- **Environment Variables** (with sensitive values)

### Why Use Sanitization?

- **Share Chats Safely:** Export conversations without exposing credentials
- **Documentation:** Create public documentation from private chats
- **Compliance:** Meet data protection requirements
- **Peace of Mind:** Automatic detection catches what manual review might miss

---

## Quick Start

### 1. Enable in Configuration (Optional)

Add to your `.env` file:

```bash
SANITIZE_ENABLED=true
SANITIZE_LEVEL=balanced
SANITIZE_STYLE=partial
```

### 2. Preview What Would Be Sanitized

```bash
python claude-chat-manager.py "My Project" --sanitize-preview
```

Output:
```
🔍 Sanitization Preview Mode
============================================================

Scanning 10 chat file(s) in project 'My Project'...
Configuration:
  Level: balanced
  Style: partial
  Sanitize paths: False

📄 conversation-1.jsonl: 3 secret(s) found
     1. [API Key] sk-proj-abc...xyz → sk-pr***xyz
     2. [Bearer Token] Bearer eyJ...abc → Beare***abc
     3. [Password] password123 → pass***123

📊 Summary
Files scanned: 10
Files with secrets: 1
Total secrets found: 3

⚠️  Sensitive data detected!
```

### 3. Export with Sanitization

```bash
# Book format
python claude-chat-manager.py "My Project" -f book -o exports/ --sanitize

# Wiki format
python claude-chat-manager.py "My Project" --wiki wiki.md --sanitize
```

---

## Configuration

### Environment Variables (.env)

```bash
# ============================================================================
# Sensitive Data Sanitization Settings
# ============================================================================

# Enable sanitization for all exports (default: false)
SANITIZE_ENABLED=false

# Detection sensitivity level (default: balanced)
# Options: minimal, balanced, aggressive, custom
SANITIZE_LEVEL=balanced

# How to replace detected secrets (default: partial)
# Options: simple, stars, labeled, partial, hash
SANITIZE_STYLE=partial

# Sanitize file paths like /Users/mike → /Users/[USER] (default: false)
SANITIZE_PATHS=false

# Custom regex patterns to detect (comma-separated)
# Example: mycompany-[a-z0-9]+,internal-.*
SANITIZE_CUSTOM_PATTERNS=

# Patterns to never sanitize (comma-separated regex)
# Default: example\.com,localhost,127\.0\.0\.1
SANITIZE_ALLOWLIST=example\.com,localhost,127\.0\.0\.1

# Generate detailed sanitization report (default: false)
SANITIZE_REPORT=false
```

### CLI Flags (Override .env)

All settings can be overridden via command-line flags:

```bash
--sanitize                    # Enable sanitization
--no-sanitize                 # Disable sanitization
--sanitize-level LEVEL        # Set detection level
--sanitize-style STYLE        # Set redaction style
--sanitize-paths              # Enable path sanitization
--sanitize-preview            # Preview without exporting
--sanitize-report FILE        # Generate report
```

---

## CLI Usage

### Basic Usage

```bash
# Enable sanitization (uses .env settings)
python claude-chat-manager.py "Project" -f book -o exports/ --sanitize

# Disable even if enabled in .env
python claude-chat-manager.py "Project" -f book -o exports/ --no-sanitize

# Preview before exporting
python claude-chat-manager.py "Project" --sanitize-preview
```

### Custom Settings

```bash
# Use aggressive detection with labeled redaction
python claude-chat-manager.py "Project" -f book -o exports/ \
    --sanitize \
    --sanitize-level aggressive \
    --sanitize-style labeled

# Sanitize paths and generate report
python claude-chat-manager.py "Project" --wiki wiki.md \
    --sanitize \
    --sanitize-paths \
    --sanitize-report sanitization-report.txt
```

### Wiki Format

```bash
# Create sanitized wiki
python claude-chat-manager.py "Project" --wiki project-wiki.md --sanitize

# Update existing wiki with sanitization
python claude-chat-manager.py "Project" --wiki wiki.md --update --sanitize

# Rebuild entire wiki with sanitization
python claude-chat-manager.py "Project" --wiki wiki.md --rebuild --sanitize
```

---

## Sanitization Levels

### Minimal (High Precision, Low False Positives)

Detects only **obvious** API keys with well-known patterns:
- OpenAI keys (`sk-*`, `sk-proj-*`)
- GitHub tokens (`ghp_*`, `gho_*`, `ghs_*`)
- AWS access keys (`AKIA*`)
- Google API keys (`AIza*`)

**Use when:** You want minimal false positives and only care about major cloud providers.

```bash
--sanitize-level minimal
```

### Balanced (Default - Recommended)

Detects all **minimal** patterns plus:
- Bearer tokens
- JWT tokens
- Contextual passwords (`password = "..."`)
- Environment variable assignments
- Slack tokens
- OpenRouter keys

**Use when:** You want good coverage with reasonable false positive rate (recommended).

```bash
--sanitize-level balanced
```

### Aggressive (Maximum Coverage)

Detects all **balanced** patterns plus:
- Generic secret patterns
- Email addresses
- IP addresses (optional)
- More contextual variations
- Broader pattern matching

**Use when:** You need maximum protection and can tolerate some false positives.

```bash
--sanitize-level aggressive
```

### Custom

Use only user-defined patterns from `SANITIZE_CUSTOM_PATTERNS`.

**Use when:** You have organization-specific secrets to detect.

```bash
SANITIZE_CUSTOM_PATTERNS=mycompany-[a-z0-9]+,internal-key-.*
--sanitize-level custom
```

---

## Redaction Styles

### Simple (Complete Replacement)

```
Original: sk-proj-abc123xyz789
Redacted: REDACTED
```

**Pros:** Maximum security
**Cons:** All secrets look identical

```bash
--sanitize-style simple
```

### Stars (Asterisk Replacement)

```
Original: sk-proj-abc123xyz789
Redacted: ********************
```

**Pros:** Shows original length
**Cons:** Still uniform, no type indication

```bash
--sanitize-style stars
```

### Labeled (Type Indicator)

```
Original: sk-proj-abc123xyz789
Redacted: [API_KEY]
```

**Pros:** Shows what was redacted
**Cons:** Loses all original information

```bash
--sanitize-style labeled
```

### Partial (Default - Recommended)

```
Original: sk-proj-abc123xyz789
Redacted: sk-pr***789
```

**Pros:**
- Keeps first 5 + last 3 characters
- Recognizable but safe
- Good for debugging

**Cons:** Slightly less secure than full redaction

```bash
--sanitize-style partial
```

### Hash (Consistent Placeholder)

```
Original: sk-proj-abc123xyz789
Redacted: [a3f4d8c2]
```

**Pros:**
- Same secret → same hash
- Can track references
- Reversible with lookup table

**Cons:** Requires maintaining hash mapping

```bash
--sanitize-style hash
```

---

## What Gets Detected

### API Keys

| Service | Pattern Example | Detected |
|---------|----------------|----------|
| OpenAI | `sk-proj-...` | ✅ |
| OpenAI (Legacy) | `sk-...` | ✅ |
| OpenRouter | `sk-or-v1-...` | ✅ |
| GitHub PAT | `ghp_...` | ✅ |
| GitHub OAuth | `gho_...` | ✅ |
| GitHub Server | `ghs_...` | ✅ |
| AWS Access Key | `AKIA...` | ✅ |
| Google API | `AIza...` | ✅ |

### Tokens

| Type | Pattern | Detected |
|------|---------|----------|
| Bearer Tokens | `Bearer abc123...` | ✅ |
| JWT | `eyJ...` | ✅ |
| Slack Bot | `xoxb-...` | ✅ |
| Slack App | `xoxa-...` | ✅ |
| Slack User | `xoxp-...` | ✅ |

### Contextual Patterns

| Pattern | Example | Detected |
|---------|---------|----------|
| Password Assignment | `password = "secret123"` | ✅ |
| Password Colon | `passwd: secret123` | ✅ |
| Secret Assignment | `secret = "key123"` | ✅ |
| Environment Variables | `API_KEY=sk-abc123` | ✅ |
| Export Commands | `export TOKEN=abc123` | ✅ |

### Default Allowlist (Never Sanitized)

- `example.com` - Example domains
- `localhost` - Local development
- `127.0.0.1` - Localhost IP
- `0.0.0.0` - All interfaces
- `sk-xxxx...` - Placeholder keys
- `xxx...` - Generic placeholders
- `*****` - Already redacted
- `your-api-key-here` - Common placeholder text

---

## Post-Processing Tool

Use `sanitize-chats.py` to sanitize **already exported** files.

### Basic Usage

```bash
# Interactive mode - review each match
python sanitize-chats.py exported-chats/ --interactive

# Batch mode - auto-sanitize all
python sanitize-chats.py exported-chats/

# Preview only (no changes)
python sanitize-chats.py my-chat.md --preview
```

### Interactive Mode

```
Match 1 of 5:
  Type: API Key
  Line: 42
  Context: "...use this key: sk-proj-abc123 for..."

  Original: sk-proj-abc123xyz789
  Redacted: sk-pr***789

  Sanitize this match? [Y/n/a/s/q/?]
    Y - Yes, sanitize this match
    n - No, skip this match
    a - Yes to all remaining matches
    s - Skip all remaining in this file
    q - Quit and save progress
    ? - Show more context
```

### Custom Configuration

```bash
# Use aggressive detection with labeled style
python sanitize-chats.py chats/ \
    --level aggressive \
    --style labeled \
    --report sanitization-report.txt

# Disable backups (not recommended)
python sanitize-chats.py chats/ --no-backup
```

### Safety Features

- ✅ **Automatic Backups:** Creates `.bak` files before modification
- ✅ **Atomic Writes:** Changes applied safely
- ✅ **Error Recovery:** Continues on file errors
- ✅ **Progress Tracking:** Shows what's being processed

---

## Best Practices

### 1. Always Preview First

```bash
# Check what would be sanitized
python claude-chat-manager.py "Project" --sanitize-preview
```

### 2. Use Balanced Level by Default

```bash
# Good balance of coverage vs false positives
--sanitize-level balanced
```

### 3. Use Partial Style for Debugging

```bash
# Keeps some recognizability
--sanitize-style partial
```

### 4. Keep Backups

The post-processing tool creates backups automatically:
```
chat.md              # Sanitized version
chat.20251226.bak    # Original backup
```

### 5. Review Allowlist

Add organization-specific safe patterns:
```bash
SANITIZE_ALLOWLIST=example\.com,mycompany\.test,staging\.local
```

### 6. Generate Reports for Audits

```bash
--sanitize-report sanitization-report.txt
```

### 7. Test on Small Projects First

```bash
# Export a small project to verify settings
python claude-chat-manager.py "Test Project" -f book -o test/ --sanitize
```

---

## Troubleshooting

### False Positives

**Problem:** Legitimate text being redacted

**Solutions:**
1. Use `minimal` level for fewer false positives
2. Add patterns to allowlist:
   ```bash
   SANITIZE_ALLOWLIST=mypattern,anotherpattern
   ```
3. Use custom level with specific patterns only

### False Negatives

**Problem:** Secrets not being detected

**Solutions:**
1. Use `aggressive` level for more coverage
2. Add custom patterns:
   ```bash
   SANITIZE_CUSTOM_PATTERNS=mycompany-[a-z0-9]+
   ```
3. Use `--sanitize-preview` to verify detection

### Performance Issues

**Problem:** Slow exports with sanitization

**Solutions:**
1. Sanitization adds <5% overhead normally
2. Most time is LLM title generation, not sanitization
3. Use book format instead of wiki for faster exports
4. Disable title generation if not needed

### Files Skipped

**Problem:** "Files skipped (errors)" in summary

**Causes:**
- Malformed JSONL files
- Empty chat files
- Permission issues

**Check:** Review logs for specific errors:
```bash
tail -50 logs/claude-chat-manager.log
```

---

## Advanced Usage

### Organization-Specific Secrets

```bash
# Detect company-specific patterns
SANITIZE_CUSTOM_PATTERNS=acme-key-[0-9a-f]{32},internal-token-.*
SANITIZE_LEVEL=custom
```

### Path Sanitization

```bash
# Redact file paths
--sanitize-paths

# Before: /Users/mike/project/file.py
# After:  /Users/[USER]/project/file.py
```

### Combining with Post-Processing

```bash
# 1. Export without sanitization
python claude-chat-manager.py "Project" -f book -o exports/

# 2. Review and sanitize specific files
python sanitize-chats.py exports/sensitive-chat.md --interactive

# 3. Batch sanitize the rest
python sanitize-chats.py exports/ --level aggressive
```

### Report Analysis

Generate report for compliance review:
```bash
python claude-chat-manager.py "Project" -f book -o exports/ \
    --sanitize \
    --sanitize-report audit-$(date +%Y%m%d).txt
```

Report contents:
- Total matches found
- Breakdown by type (API keys, tokens, passwords)
- File locations
- Patterns matched

---

## Examples

### Example 1: Safe Public Documentation

```bash
# Preview to verify coverage
python claude-chat-manager.py "Documentation Project" --sanitize-preview

# Export with balanced sanitization
python claude-chat-manager.py "Documentation Project" \
    -f book -o public-docs/ \
    --sanitize \
    --sanitize-level balanced \
    --sanitize-style partial
```

### Example 2: Maximum Security

```bash
# Use aggressive detection and full redaction
python claude-chat-manager.py "Secure Project" \
    --wiki secure-wiki.md \
    --sanitize \
    --sanitize-level aggressive \
    --sanitize-style simple \
    --sanitize-paths
```

### Example 3: Review Existing Exports

```bash
# Sanitize previously exported files
python sanitize-chats.py old-exports/ --interactive

# Generate report of what was found
python sanitize-chats.py old-exports/ \
    --level aggressive \
    --report findings-report.txt
```

---

## FAQ

**Q: Does sanitization slow down exports?**
A: Minimal impact (<5% overhead). LLM title generation is the main time factor.

**Q: Can I recover sanitized data?**
A: No. Always keep original files. Use `--preview` to verify before exporting.

**Q: Are sanitized exports perfect?**
A: No tool is 100% perfect. Always review sensitive exports manually.

**Q: What about email addresses?**
A: Not detected by default. Use `aggressive` level or add custom pattern.

**Q: Can I add my own patterns?**
A: Yes! Use `SANITIZE_CUSTOM_PATTERNS` in `.env` file.

**Q: Does it work with wiki updates?**
A: Yes! Use `--wiki wiki.md --update --sanitize`.

---

## See Also

- [SANITIZATION_SPEC.md](SANITIZATION_SPEC.md) - Technical implementation details
- [README.md](../README.md) - Main project documentation
- [.env.example](../.env.example) - Full configuration reference

---

**Last Updated:** 2025-12-26
**Feature Version:** 1.0
**Questions?** Open an issue on GitHub

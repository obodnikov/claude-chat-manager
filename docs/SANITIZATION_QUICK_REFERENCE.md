# Sanitization Quick Reference

**Version:** 1.0 | **Last Updated:** 2025-12-26

---

## 🚀 Quick Commands

```bash
# Preview what would be sanitized
python claude-chat-manager.py "Project" --sanitize-preview

# Export with sanitization (uses .env settings)
python claude-chat-manager.py "Project" -f book -o exports/ --sanitize

# Post-process existing files
python sanitize-chats.py exported-chats/ --interactive
```

---

## 📋 CLI Flags Cheat Sheet

| Flag | Options | Description |
|------|---------|-------------|
| `--sanitize` | - | Enable sanitization |
| `--no-sanitize` | - | Disable sanitization |
| `--sanitize-level` | minimal, balanced, aggressive, custom | Detection sensitivity |
| `--sanitize-style` | simple, stars, labeled, partial, hash | Redaction style |
| `--sanitize-paths` | - | Sanitize file paths |
| `--sanitize-preview` | - | Preview without exporting |
| `--sanitize-report FILE` | - | Generate detailed report |

---

## 🎯 Detection Levels

| Level | Coverage | False Positives | Use When |
|-------|----------|-----------------|----------|
| **minimal** | Low | Very Few | Only major cloud providers |
| **balanced** ⭐ | Medium | Few | General use (recommended) |
| **aggressive** | High | Some | Maximum protection needed |
| **custom** | Custom | Depends | Organization-specific secrets |

---

## 🎨 Redaction Styles

| Style | Example | Security | Readability |
|-------|---------|----------|-------------|
| **simple** | `REDACTED` | ⭐⭐⭐⭐⭐ | ⭐ |
| **stars** | `**********` | ⭐⭐⭐⭐ | ⭐⭐ |
| **labeled** | `[API_KEY]` | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **partial** ⭐ | `sk-pr***xyz` | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **hash** | `[a3f4d8c2]` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 🔍 What Gets Detected

### API Keys
- OpenAI: `sk-*`, `sk-proj-*`
- OpenRouter: `sk-or-v1-*`
- GitHub: `ghp_*`, `gho_*`, `ghs_*`
- AWS: `AKIA*`
- Google: `AIza*`

### Tokens
- Bearer tokens: `Bearer abc...`
- JWT: `eyJ...`
- Slack: `xox[baprs]-...`

### Contextual
- Password assignments
- Environment variables
- Secret definitions

---

## ⚙️ Configuration (.env)

```bash
# Enable/disable
SANITIZE_ENABLED=false

# Detection level
SANITIZE_LEVEL=balanced

# Redaction style
SANITIZE_STYLE=partial

# File paths
SANITIZE_PATHS=false

# Custom patterns (comma-separated)
SANITIZE_CUSTOM_PATTERNS=

# Never sanitize (comma-separated)
SANITIZE_ALLOWLIST=example\.com,localhost
```

---

## 💡 Common Use Cases

### 1. Safe Public Sharing
```bash
python claude-chat-manager.py "Project" \
    --sanitize-preview                    # Check first

python claude-chat-manager.py "Project" \
    -f book -o public/ --sanitize         # Export safely
```

### 2. Maximum Security
```bash
python claude-chat-manager.py "Project" \
    --wiki wiki.md \
    --sanitize \
    --sanitize-level aggressive \
    --sanitize-style simple \
    --sanitize-paths
```

### 3. Review Existing Exports
```bash
python sanitize-chats.py exports/ --interactive
```

### 4. Compliance Audit
```bash
python claude-chat-manager.py "Project" \
    -f book -o exports/ \
    --sanitize \
    --sanitize-report audit-2025-12-26.txt
```

---

## 🛡️ Best Practices

✅ **DO:**
- Always preview first (`--sanitize-preview`)
- Use `balanced` level by default
- Keep original backups
- Review allowlist for your use case
- Test on small projects first

❌ **DON'T:**
- Rely 100% on automation (manual review too)
- Use `aggressive` without checking false positives
- Skip backups (post-processing tool creates them automatically)
- Forget to check the sanitization report

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| False positives | Use `minimal` level or add to allowlist |
| False negatives | Use `aggressive` level or add custom patterns |
| Slow performance | Sanitization adds <5%, check LLM calls instead |
| Files skipped | Check logs for malformed/empty files |

---

## 📚 Full Documentation

- **Complete Guide:** [SANITIZATION.md](SANITIZATION.md)
- **Technical Spec:** [SANITIZATION_SPEC.md](SANITIZATION_SPEC.md)
- **Main README:** [../README.md](../README.md)

---

**Questions?** Open an issue on GitHub

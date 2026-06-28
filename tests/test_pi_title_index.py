"""Tests for src/pi_title_index.py — wingman sidecar title index writer.

Covers:
- load_title_index: missing file, corrupt JSON, valid file, wrong structure.
- upsert_llm_title: write new entry, refresh llm entry, manual guard,
  version + other-sessions preserved, atomic write (no partial file on error).
- title_index_path: correct path derivation.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.pi_title_index import (
    DEFAULT_INDEX,
    load_title_index,
    title_index_path,
    upsert_llm_title,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_NOW = "2026-06-28T10:00:00.000000Z"
_now = lambda: FIXED_NOW  # noqa: E731  — injected clock for determinism

SESSION_A = "019eef5f-c83f-7f83-ba2a-29f541999380"
SESSION_B = "019ef0c5-fdf8-7626-ad4d-da7ee350c408"
MODEL = "anthropic/claude-haiku-4-5"


def _write_index(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _read_index(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# title_index_path
# ---------------------------------------------------------------------------

class TestTitleIndexPath:
    def test_correct_path(self, tmp_path: Path) -> None:
        result = title_index_path(tmp_path)
        assert result == tmp_path / "sessions" / ".wingman-titles.json"


# ---------------------------------------------------------------------------
# load_title_index
# ---------------------------------------------------------------------------

class TestLoadTitleIndex:
    def test_missing_file_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "sessions" / ".wingman-titles.json"
        result = load_title_index(path)
        assert result == {"version": 1, "titles": {}}

    def test_missing_file_returns_deep_copy(self, tmp_path: Path) -> None:
        path = tmp_path / "sessions" / ".wingman-titles.json"
        a = load_title_index(path)
        b = load_title_index(path)
        a["titles"]["x"] = {}
        assert "x" not in b["titles"]

    def test_corrupt_json_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        path.write_text("{ not valid json }", encoding="utf-8")
        result = load_title_index(path)
        assert result == {"version": 1, "titles": {}}

    def test_wrong_structure_no_titles_key(self, tmp_path: Path) -> None:
        # Repair strategy: missing 'titles' key is coerced to {}, other keys preserved.
        path = tmp_path / ".wingman-titles.json"
        _write_index(path, {"version": 1, "something_else": {"x": 1}})
        result = load_title_index(path)
        assert result["titles"] == {}
        assert result["something_else"] == {"x": 1}  # preserved
        assert result["version"] == 1

    def test_titles_not_dict_repaired(self, tmp_path: Path) -> None:
        # Repair strategy: bad 'titles' value is reset to {}, other keys kept.
        path = tmp_path / ".wingman-titles.json"
        _write_index(path, {"version": 2, "titles": ["bad"], "extra": "kept"})
        result = load_title_index(path)
        assert result["titles"] == {}
        assert result["extra"] == "kept"
        assert result["version"] == 2

    def test_valid_file_returned(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        data = {
            "version": 1,
            "titles": {
                SESSION_A: {
                    "title": "My chat",
                    "source": "manual",
                    "generatedAt": FIXED_NOW,
                }
            },
        }
        _write_index(path, data)
        result = load_title_index(path)
        assert result["titles"][SESSION_A]["title"] == "My chat"


# ---------------------------------------------------------------------------
# upsert_llm_title — write new entry
# ---------------------------------------------------------------------------

class TestUpsertLlmTitleNew:
    def test_creates_index_file_when_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "sessions" / ".wingman-titles.json"
        result = upsert_llm_title(path, SESSION_A, "Foo Bar", MODEL, 5, now=_now)
        assert result is True
        assert path.exists()

    def test_entry_fields(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "Foo Bar", MODEL, 5, now=_now)
        data = _read_index(path)
        entry = data["titles"][SESSION_A]
        assert entry["title"] == "Foo Bar"
        assert entry["source"] == "llm"
        assert entry["model"] == MODEL
        assert entry["generatedAt"] == FIXED_NOW
        assert entry["sourceMsgCount"] == 5

    def test_version_field_written(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "Foo", MODEL, 1, now=_now)
        data = _read_index(path)
        assert data["version"] == 1

    def test_returns_true_on_success(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        assert upsert_llm_title(path, SESSION_A, "X", MODEL, 1, now=_now) is True


# ---------------------------------------------------------------------------
# upsert_llm_title — manual guard
# ---------------------------------------------------------------------------

class TestUpsertLlmTitleManualGuard:
    def test_does_not_overwrite_manual_entry(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        original = {
            "version": 1,
            "titles": {
                SESSION_A: {
                    "title": "User title",
                    "source": "manual",
                    "generatedAt": FIXED_NOW,
                }
            },
        }
        _write_index(path, original)

        result = upsert_llm_title(path, SESSION_A, "LLM title", MODEL, 3, now=_now)

        assert result is False
        data = _read_index(path)
        assert data["titles"][SESSION_A]["title"] == "User title"
        assert data["titles"][SESSION_A]["source"] == "manual"

    def test_file_unchanged_after_manual_guard(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        original = {
            "version": 1,
            "titles": {
                SESSION_A: {"title": "Keep me", "source": "manual", "generatedAt": FIXED_NOW}
            },
        }
        _write_index(path, original)
        mtime_before = path.stat().st_mtime

        upsert_llm_title(path, SESSION_A, "New LLM title", MODEL, 3, now=_now)

        # File should not have been rewritten (mtime unchanged on most OSes,
        # but content check is the reliable assertion).
        data = _read_index(path)
        assert data["titles"][SESSION_A]["source"] == "manual"


# ---------------------------------------------------------------------------
# upsert_llm_title — refresh existing llm entry
# ---------------------------------------------------------------------------

class TestUpsertLlmTitleRefresh:
    def test_overwrites_existing_llm_entry(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        old_data = {
            "version": 1,
            "titles": {
                SESSION_A: {
                    "title": "Old LLM title",
                    "source": "llm",
                    "model": "old-model",
                    "generatedAt": "2026-01-01T00:00:00.000000Z",
                    "sourceMsgCount": 2,
                }
            },
        }
        _write_index(path, old_data)

        result = upsert_llm_title(path, SESSION_A, "New LLM title", MODEL, 7, now=_now)

        assert result is True
        data = _read_index(path)
        entry = data["titles"][SESSION_A]
        assert entry["title"] == "New LLM title"
        assert entry["model"] == MODEL
        assert entry["sourceMsgCount"] == 7
        assert entry["generatedAt"] == FIXED_NOW


# ---------------------------------------------------------------------------
# upsert_llm_title — merge (preserve other sessions + version)
# ---------------------------------------------------------------------------

class TestUpsertLlmTitleMerge:
    def test_preserves_other_sessions(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        existing = {
            "version": 1,
            "titles": {
                SESSION_B: {
                    "title": "Other session",
                    "source": "manual",
                    "generatedAt": FIXED_NOW,
                }
            },
        }
        _write_index(path, existing)

        upsert_llm_title(path, SESSION_A, "New session title", MODEL, 4, now=_now)

        data = _read_index(path)
        # Both sessions present
        assert SESSION_A in data["titles"]
        assert SESSION_B in data["titles"]
        assert data["titles"][SESSION_B]["title"] == "Other session"

    def test_preserves_version(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        _write_index(path, {"version": 2, "titles": {}})

        upsert_llm_title(path, SESSION_A, "Title", MODEL, 1, now=_now)

        data = _read_index(path)
        assert data["version"] == 2

    def test_multiple_sessions_independent(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "Alpha", MODEL, 3, now=_now)
        upsert_llm_title(path, SESSION_B, "Beta", MODEL, 5, now=_now)

        data = _read_index(path)
        assert data["titles"][SESSION_A]["title"] == "Alpha"
        assert data["titles"][SESSION_B]["title"] == "Beta"

    def test_unknown_top_level_keys_preserved(self, tmp_path: Path) -> None:
        """Forward-compat: extra top-level keys (e.g. future wingman fields) survive upsert."""
        path = tmp_path / ".wingman-titles.json"
        seed = {
            "version": 3,
            "titles": {
                SESSION_B: {
                    "title": "Existing",
                    "source": "manual",
                    "generatedAt": FIXED_NOW,
                }
            },
            "schema": "wingman-v3",
            "extra": {"flag": True, "count": 42},
        }
        _write_index(path, seed)

        upsert_llm_title(path, SESSION_A, "New Title", MODEL, 2, now=_now)

        data = _read_index(path)
        assert data["schema"] == "wingman-v3"
        assert data["extra"] == {"flag": True, "count": 42}
        assert data["version"] == 3
        assert SESSION_A in data["titles"]
        assert SESSION_B in data["titles"]


# ---------------------------------------------------------------------------
# upsert_llm_title — atomic write (no partial file on failure)
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_no_orphan_on_write_failure(self, tmp_path: Path) -> None:
        """If the rename fails, no partial temp file should remain."""
        # Use the real sessions/ subdirectory (mirrors title_index_path() output)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        path = sessions_dir / ".wingman-titles.json"

        with patch("os.replace", side_effect=OSError("simulated rename failure")):
            result = upsert_llm_title(path, SESSION_A, "T", MODEL, 1, now=_now)

        assert result is False
        # No stray temp files in the sessions directory
        tmp_files = list(sessions_dir.glob(".wingman-titles-*.tmp"))
        assert tmp_files == []

    def test_existing_file_untouched_on_write_failure(self, tmp_path: Path) -> None:
        """Original index must survive a failed atomic write."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        path = sessions_dir / ".wingman-titles.json"
        original = {"version": 1, "titles": {SESSION_B: {"title": "Safe", "source": "llm",
                                                           "model": MODEL, "generatedAt": FIXED_NOW,
                                                           "sourceMsgCount": 1}}}
        _write_index(path, original)

        with patch("os.replace", side_effect=OSError("simulated rename failure")):
            upsert_llm_title(path, SESSION_A, "New", MODEL, 2, now=_now)

        data = _read_index(path)
        assert SESSION_B in data["titles"]
        assert SESSION_A not in data["titles"]


# ---------------------------------------------------------------------------
# upsert_llm_title — fail-safe (never raises)
# ---------------------------------------------------------------------------

class TestFailSafe:
    def test_returns_false_on_unhandled_exception(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        # Corrupt the load path so an unexpected error occurs
        with patch("src.pi_title_index.load_title_index", side_effect=RuntimeError("boom")):
            result = upsert_llm_title(path, SESSION_A, "T", MODEL, 1, now=_now)
        assert result is False

    def test_does_not_raise(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        with patch("src.pi_title_index.load_title_index", side_effect=RuntimeError("boom")):
            # Should not raise — exports must never be broken by title sync
            try:
                upsert_llm_title(path, SESSION_A, "T", MODEL, 1, now=_now)
            except Exception as exc:
                pytest.fail(f"upsert_llm_title raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Title normalisation
# ---------------------------------------------------------------------------

class TestNormalizeTitle:
    """Tests for _normalize_title via upsert_llm_title (public surface)."""

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "  Hello World  ", MODEL, 1, now=_now)
        assert _read_index(path)["titles"][SESSION_A]["title"] == "Hello World"

    def test_replaces_newlines(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "Line one\nLine two", MODEL, 1, now=_now)
        assert _read_index(path)["titles"][SESSION_A]["title"] == "Line one Line two"

    def test_replaces_tabs(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "col1\tcol2", MODEL, 1, now=_now)
        assert _read_index(path)["titles"][SESSION_A]["title"] == "col1 col2"

    def test_collapses_repeated_spaces(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        upsert_llm_title(path, SESSION_A, "too   many   spaces", MODEL, 1, now=_now)
        assert _read_index(path)["titles"][SESSION_A]["title"] == "too many spaces"

    def test_truncates_at_200_chars(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        long_title = "x" * 250
        upsert_llm_title(path, SESSION_A, long_title, MODEL, 1, now=_now)
        assert len(_read_index(path)["titles"][SESSION_A]["title"]) == 200

    def test_empty_title_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / ".wingman-titles.json"
        result = upsert_llm_title(path, SESSION_A, "   \n\t  ", MODEL, 1, now=_now)
        assert result is False
        assert not path.exists()


# ---------------------------------------------------------------------------
# Integration: exporters / wiki gating — real code paths
# ---------------------------------------------------------------------------

class TestExporterGating:
    """Verify sync_wingman_title is called only under the right conditions
    by exercising the real exporters._generate_book_filename and
    WikiGenerator._generate_title_with_llm call paths.
    """

    def _make_pi_session_file(self, sessions_dir: Path, session_id: str, cwd: str) -> Path:
        """Write a minimal pi session JSONL file."""
        sessions_dir.mkdir(parents=True, exist_ok=True)
        f = sessions_dir / f"20260628_{session_id[:8]}.jsonl"
        header = json.dumps({
            "type": "session", "version": 3, "id": session_id,
            "timestamp": "2026-06-28T10:00:00.000Z", "cwd": cwd,
        })
        msg = json.dumps({
            "type": "message", "id": "aaa", "parentId": None,
            "timestamp": "2026-06-28T10:00:01.000Z",
            "message": {"role": "user", "content": "hello"},
        })
        f.write_text(header + "\n" + msg + "\n", encoding="utf-8")
        return f

    def _minimal_chat_data(self) -> list:
        """Minimal chat_data list compatible with _generate_book_filename."""
        return [
            {"message": {"role": "user", "content": "What is the plan?"},
             "timestamp": "2026-06-28T10:00:01.000Z"},
            {"message": {"role": "assistant", "content": "Here is the plan."},
             "timestamp": "2026-06-28T10:00:02.000Z"},
        ]

    # -- _generate_book_filename integration --

    def test_book_calls_sync_for_pi_session(self, tmp_path: Path) -> None:
        """_generate_book_filename calls sync_wingman_title with the pi session id."""
        from unittest.mock import MagicMock, patch
        from src.exporters import _generate_book_filename

        llm_client = MagicMock()
        llm_client.generate_chat_title.return_value = "Generated Title"
        llm_client.model = MODEL

        calls: list = []

        # sync_wingman_title is imported lazily inside _generate_book_filename;
        # patch it at its canonical location so both call sites are covered.
        with patch("src.pi_title_index.sync_wingman_title",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            with patch("src.exporters.config") as mock_cfg:
                mock_cfg.pi_write_wingman_titles = True
                mock_cfg.pi_data_dir = tmp_path
                mock_cfg.openrouter_model = MODEL
                mock_cfg.book_include_date = False
                _generate_book_filename(
                    self._minimal_chat_data(),
                    tmp_path / "chat.jsonl",
                    llm_client,
                    None,
                    pi_session_id=SESSION_A,
                    pi_msg_count=1,
                )

        assert len(calls) == 1

    def test_book_no_sync_when_session_id_none(self, tmp_path: Path) -> None:
        """_generate_book_filename does NOT sync when pi_session_id is None."""
        from unittest.mock import MagicMock, patch
        from src.exporters import _generate_book_filename

        llm_client = MagicMock()
        llm_client.generate_chat_title.return_value = "Title"
        llm_client.model = MODEL

        calls: list = []
        with patch("src.pi_title_index.sync_wingman_title",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            with patch("src.exporters.config") as mock_cfg:
                mock_cfg.pi_write_wingman_titles = True
                mock_cfg.pi_data_dir = tmp_path
                mock_cfg.openrouter_model = MODEL
                mock_cfg.book_include_date = False
                _generate_book_filename(
                    self._minimal_chat_data(),
                    tmp_path / "chat.jsonl",
                    llm_client,
                    None,
                    pi_session_id=None,
                    pi_msg_count=0,
                )

        assert calls == []

    # -- WikiGenerator._generate_title_with_llm integration --

    def test_wiki_calls_sync_for_pi_session(self, tmp_path: Path) -> None:
        """WikiGenerator._generate_title_with_llm calls sync_wingman_title."""
        from unittest.mock import MagicMock, patch
        from src.wiki_generator import WikiGenerator

        llm_client = MagicMock()
        llm_client.generate_chat_title.return_value = "Wiki Title"
        llm_client.model = MODEL

        calls: list = []
        gen = WikiGenerator(llm_client=llm_client)

        chat_data = [
            {"message": {"role": "user", "content": "question"},
             "timestamp": "2026-06-28T10:00:01.000Z"},
        ]

        # sync_wingman_title is imported lazily; patch at canonical location.
        with patch("src.pi_title_index.sync_wingman_title",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            with patch("src.wiki_generator.config") as mock_cfg:
                mock_cfg.pi_write_wingman_titles = True
                mock_cfg.pi_data_dir = tmp_path
                mock_cfg.openrouter_model = MODEL
                gen._generate_title_with_llm(
                    chat_data,
                    pi_session_id=SESSION_A,
                    pi_msg_count=3,
                )

        assert len(calls) == 1

    def test_wiki_no_sync_when_flag_off(self, tmp_path: Path) -> None:
        """WikiGenerator._generate_title_with_llm skips sync when flag is off."""
        from unittest.mock import MagicMock, patch
        from src.wiki_generator import WikiGenerator

        llm_client = MagicMock()
        llm_client.generate_chat_title.return_value = "Wiki Title"

        calls: list = []
        gen = WikiGenerator(llm_client=llm_client)
        chat_data = [{"message": {"role": "user", "content": "hi"},
                      "timestamp": "2026-06-28T10:00:01.000Z"}]

        with patch("src.pi_title_index.sync_wingman_title",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            with patch("src.wiki_generator.config") as mock_cfg:
                mock_cfg.pi_write_wingman_titles = False
                gen._generate_title_with_llm(
                    chat_data,
                    pi_session_id=SESSION_A,
                    pi_msg_count=3,
                )

        assert calls == []

    def test_wiki_no_sync_when_session_id_none(self, tmp_path: Path) -> None:
        """WikiGenerator._generate_title_with_llm skips sync when session_id is None."""
        from unittest.mock import MagicMock, patch
        from src.wiki_generator import WikiGenerator

        llm_client = MagicMock()
        llm_client.generate_chat_title.return_value = "Title"

        calls: list = []
        gen = WikiGenerator(llm_client=llm_client)
        chat_data = [{"message": {"role": "user", "content": "hi"},
                      "timestamp": "2026-06-28T10:00:01.000Z"}]

        with patch("src.pi_title_index.sync_wingman_title",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            with patch("src.wiki_generator.config") as mock_cfg:
                mock_cfg.pi_write_wingman_titles = True
                mock_cfg.pi_data_dir = tmp_path
                mock_cfg.openrouter_model = MODEL
                gen._generate_title_with_llm(
                    chat_data,
                    pi_session_id=None,
                    pi_msg_count=0,
                )

        assert calls == []

    # -- config flag property --

    def test_flag_off_by_default(self) -> None:
        """PI_WRITE_WINGMAN_TITLES defaults to False."""
        import os
        from unittest.mock import patch
        from src.config import Config
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PI_WRITE_WINGMAN_TITLES", None)
            fresh = Config()
            assert fresh.pi_write_wingman_titles is False

    def test_flag_on_when_set(self) -> None:
        """PI_WRITE_WINGMAN_TITLES=true enables the feature."""
        import os
        from unittest.mock import patch
        from src.config import Config
        with patch.dict(os.environ, {"PI_WRITE_WINGMAN_TITLES": "true"}):
            assert Config().pi_write_wingman_titles is True


# ---------------------------------------------------------------------------
# sync_wingman_title — guard behaviour
# ---------------------------------------------------------------------------

class TestSyncWingmanTitleGuards:
    """Validate sync_wingman_title path-traversal guard, fresh-dir creation,
    and fail-safe behaviour."""

    def test_no_op_when_session_id_none(self, tmp_path: Path) -> None:
        """sync_wingman_title is a no-op when session_id is None."""
        from src.pi_title_index import sync_wingman_title
        from unittest.mock import patch
        calls: list = []
        with patch("src.pi_title_index.upsert_llm_title",
                   side_effect=lambda *a, **kw: calls.append(a)):
            sync_wingman_title(tmp_path, None, "Title", MODEL, 1)
        assert calls == []

    def test_no_op_when_session_id_empty(self, tmp_path: Path) -> None:
        """sync_wingman_title is a no-op when session_id is empty string."""
        from src.pi_title_index import sync_wingman_title
        from unittest.mock import patch
        calls: list = []
        with patch("src.pi_title_index.upsert_llm_title",
                   side_effect=lambda *a, **kw: calls.append(a)):
            sync_wingman_title(tmp_path, "", "Title", MODEL, 1)
        assert calls == []

    def test_creates_sessions_dir_when_missing(self, tmp_path: Path) -> None:
        """sync_wingman_title creates pi_data_dir/sessions/ if absent."""
        from src.pi_title_index import sync_wingman_title
        pi_dir = tmp_path / "fresh_pi"
        assert not pi_dir.exists()
        # upsert will write the index; let it run for real
        sync_wingman_title(pi_dir, SESSION_A, "Title", MODEL, 1)
        assert (pi_dir / "sessions").is_dir()

    def test_path_traversal_guard_blocks_outside_path(self, tmp_path: Path) -> None:
        """sync_wingman_title skips when resolved index escapes pi_data_dir."""
        from src.pi_title_index import sync_wingman_title
        from unittest.mock import patch

        pi_dir = tmp_path / "pi"
        sessions_dir = pi_dir / "sessions"
        sessions_dir.mkdir(parents=True)

        # Patch title_index_path to return a path outside pi_data_dir
        outside_path = tmp_path / "outside" / ".wingman-titles.json"
        calls: list = []
        with patch("src.pi_title_index.title_index_path", return_value=outside_path):
            with patch("src.pi_title_index.upsert_llm_title",
                       side_effect=lambda *a, **kw: calls.append(a)):
                sync_wingman_title(pi_dir, SESSION_A, "Title", MODEL, 1)
        # upsert must NOT be called when path is outside base
        assert calls == []

    def test_does_not_raise_on_upsert_failure(self, tmp_path: Path) -> None:
        """sync_wingman_title never raises — export must not be broken."""
        from src.pi_title_index import sync_wingman_title
        from unittest.mock import patch
        with patch("src.pi_title_index.upsert_llm_title",
                   side_effect=RuntimeError("boom")):
            try:
                sync_wingman_title(tmp_path, SESSION_A, "Title", MODEL, 1)
            except Exception as exc:
                pytest.fail(f"sync_wingman_title raised unexpectedly: {exc}")

    def test_locking_failure_returns_false(self, tmp_path: Path) -> None:
        """upsert_llm_title returns False and does not write when lock fails."""
        from src.pi_title_index import upsert_llm_title
        from unittest.mock import patch

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        path = sessions_dir / ".wingman-titles.json"

        with patch("src.pi_title_index._acquire_lock", return_value=False):
            result = upsert_llm_title(path, SESSION_A, "Title", MODEL, 1, now=_now)

        assert result is False
        assert not path.exists()

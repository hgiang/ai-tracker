from pathlib import Path

import pytest

from app.services import preferences as prefs_mod


@pytest.fixture(autouse=True)
def reset_cache():
    prefs_mod._cached.cache_clear()
    yield
    prefs_mod._cached.cache_clear()


def test_load_preferences_returns_file_content(tmp_path: Path, monkeypatch):
    path = tmp_path / "preferences.md"
    path.write_text("# my prefs\n- love RAG\n", encoding="utf-8")
    monkeypatch.setattr(prefs_mod.settings, "preferences_path", str(path))

    assert "love RAG" in prefs_mod.load_preferences()


def test_load_preferences_falls_back_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(prefs_mod.settings, "preferences_path", str(tmp_path / "nope.md"))
    text = prefs_mod.load_preferences()
    assert "Reader Preferences" in text


def test_cache_invalidates_on_mtime_change(tmp_path: Path, monkeypatch):
    path = tmp_path / "preferences.md"
    path.write_text("first\n", encoding="utf-8")
    monkeypatch.setattr(prefs_mod.settings, "preferences_path", str(path))

    assert prefs_mod.load_preferences_cached().strip() == "first"

    # Bump mtime by writing new content with a different timestamp
    path.write_text("second\n", encoding="utf-8")
    import os, time

    new_time = path.stat().st_mtime + 5
    os.utime(path, (new_time, new_time))

    assert prefs_mod.load_preferences_cached().strip() == "second"

"""Load the user's reader preferences from preferences.md."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings

_DEFAULT_PREFERENCES = """\
# Reader Preferences

## Topics I want to see
- Large language models, agentic AI, RAG, fine-tuning, inference efficiency

## Topics to skip
- Crypto, hype, marketing fluff
"""


def _resolve_path() -> Path:
    return Path(settings.preferences_path).expanduser().resolve()


def load_preferences() -> str:
    """Return the preferences markdown, or a built-in default if missing."""
    path = _resolve_path()
    if not path.is_file():
        return _DEFAULT_PREFERENCES
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _cached() -> tuple[float, str]:
    path = _resolve_path()
    mtime = path.stat().st_mtime if path.is_file() else 0.0
    return mtime, load_preferences()


def load_preferences_cached() -> str:
    """Cached read; invalidates automatically when preferences.md changes on disk."""
    path = _resolve_path()
    current_mtime = path.stat().st_mtime if path.is_file() else 0.0
    cached_mtime, cached_text = _cached()
    if current_mtime != cached_mtime:
        _cached.cache_clear()
        _, cached_text = _cached()
    return cached_text

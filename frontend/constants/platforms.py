"""Frontend constants and platform configuration."""

from __future__ import annotations

DEFAULT_API = "http://127.0.0.1:8000"

PLATFORM_LIMITS: dict[str, dict] = {
    "linkedin": {"label": "LinkedIn", "max_chars": 1300, "max_words": None, "type": "single"},
    "twitter": {"label": "X / Twitter", "max_chars": 280, "max_words": None, "type": "thread"},
    "medium": {"label": "Medium", "max_chars": None, "max_words": 1500, "type": "single"},
    "youtube_script": {"label": "YouTube script", "max_chars": None, "max_words": 1200, "type": "single"},
    "newsletter": {"label": "Newsletter", "max_chars": None, "max_words": 900, "type": "single"},
    "instagram": {"label": "Instagram caption", "max_chars": 2200, "max_words": None, "type": "single"},
    "threads": {"label": "Threads", "max_chars": 500, "max_words": None, "type": "thread"},
}

PLATFORMS: dict[str, str] = {
    "LinkedIn": "linkedin",
    "X / Twitter": "twitter",
    "Medium": "medium",
    "YouTube script": "youtube_script",
    "Newsletter": "newsletter",
    "Instagram caption": "instagram",
    "Threads": "threads",
}

TERMINAL = {"done", "failed"}
PAUSE = {"awaiting_choice"}

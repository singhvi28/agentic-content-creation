"""Compliance and text metrics calculation utilities."""

from __future__ import annotations

from frontend.constants.platforms import PLATFORM_LIMITS


def calculate_compliance(text: str, platform_key: str | None) -> dict:
    """Calculates character & word stats and compliance against platform limits."""
    if not text:
        return {"chars": 0, "words": 0, "status": "ok", "badge": "0 chars"}

    chars = len(text)
    words = len(text.split())
    rule = PLATFORM_LIMITS.get(platform_key or "")

    if not rule:
        return {"chars": chars, "words": words, "status": "ok", "badge": f"📊 {chars:,} chars · {words:,} words"}

    max_chars = rule.get("max_chars")
    max_words = rule.get("max_words")
    is_thread = rule.get("type") == "thread"

    if is_thread and platform_key == "twitter":
        # Split thread tweets by double newline or numbered items
        tweets = [t.strip() for t in text.split("\n\n") if t.strip()]
        thread_overflow = False
        tweet_badges = []
        for i, tw in enumerate(tweets, 1):
            tw_len = len(tw)
            if tw_len > 280:
                thread_overflow = True
                tweet_badges.append(f"T{i}: {tw_len}/280 🔴")
            else:
                tweet_badges.append(f"T{i}: {tw_len}/280 🟢")
        status_icon = "🔴 Exceeds 280-char cap" if thread_overflow else "🟢 Valid thread"
        return {
            "chars": chars,
            "words": words,
            "status": "error" if thread_overflow else "ok",
            "badge": f"{status_icon} ({len(tweets)} tweets: {' · '.join(tweet_badges[:4])}{'...' if len(tweet_badges) > 4 else ''})",
        }

    if max_chars:
        pct = int((chars / max_chars) * 100)
        if chars > max_chars:
            diff = chars - max_chars
            return {
                "chars": chars,
                "words": words,
                "status": "error",
                "badge": f"🔴 {chars:,} / {max_chars:,} chars (+{diff:,} over cap, {pct}%) · {words:,} words",
            }
        return {
            "chars": chars,
            "words": words,
            "status": "ok",
            "badge": f"🟢 {chars:,} / {max_chars:,} chars ({pct}%) · {words:,} words",
        }

    if max_words:
        pct = int((words / max_words) * 100)
        if words > max_words:
            diff = words - max_words
            return {
                "chars": chars,
                "words": words,
                "status": "error",
                "badge": f"🔴 {words:,} / {max_words:,} words (+{diff:,} over cap, {pct}%) · {chars:,} chars",
            }
        return {
            "chars": chars,
            "words": words,
            "status": "ok",
            "badge": f"🟢 {words:,} / {max_words:,} words ({pct}%) · {chars:,} chars",
        }

    return {"chars": chars, "words": words, "status": "ok", "badge": f"📊 {chars:,} chars · {words:,} words"}

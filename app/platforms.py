"""First-class platform presets for the content pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformPreset:
    id: str
    label: str
    max_chars: int | None  # hard/soft char cap (per segment for threads)
    max_words: int | None
    tone: str
    cta_style: str
    hashtag_policy: str  # none | light | encouraged
    structure: str  # single | thread
    formatting: str  # markdown | plain
    guidance: str


PLATFORMS: dict[str, PlatformPreset] = {
    "linkedin": PlatformPreset(
        id="linkedin",
        label="LinkedIn",
        max_chars=1300,
        max_words=None,
        tone="Professional but human; peer-to-peer, not corporate fluff.",
        cta_style="Soft engagement CTA (question or invite to comment).",
        hashtag_policy="light",
        structure="single",
        formatting="plain",
        guidance=(
            "Write a LinkedIn post. Lead with a strong first line. "
            "Use short paragraphs and whitespace. Stay around 1,300 characters."
        ),
    ),
    "twitter": PlatformPreset(
        id="twitter",
        label="X / Twitter",
        max_chars=280,
        max_words=None,
        tone="Punchy, conversational, high signal.",
        cta_style="Optional reply/retweet prompt; keep light.",
        hashtag_policy="light",
        structure="thread",
        formatting="plain",
        guidance=(
            "Write an X/Twitter thread. Each tweet MUST be ≤280 characters. "
            "Number tweets (1/, 2/, …). First tweet is the hook; last is the CTA."
        ),
    ),
    "medium": PlatformPreset(
        id="medium",
        label="Medium",
        max_chars=None,
        max_words=1500,
        tone="Thoughtful longform; clear voice and narrative arc.",
        cta_style="End with a reflective takeaway or next-step for the reader.",
        hashtag_policy="none",
        structure="single",
        formatting="markdown",
        guidance=(
            "Write a Medium article in Markdown with a title, intro, "
            "section headings, and conclusion. Aim under ~1,500 words."
        ),
    ),
    "youtube_script": PlatformPreset(
        id="youtube_script",
        label="YouTube script",
        max_chars=None,
        max_words=1200,
        tone="Spoken-word friendly; energetic and clear for video.",
        cta_style="Subscribe / comment CTA near the end.",
        hashtag_policy="none",
        structure="single",
        formatting="plain",
        guidance=(
            "Write a YouTube talking-head script with: cold open hook, "
            "beat-by-beat sections, verbal transitions, and closing CTA. "
            "Write for speaking aloud, not as an essay."
        ),
    ),
    "newsletter": PlatformPreset(
        id="newsletter",
        label="Newsletter",
        max_chars=None,
        max_words=900,
        tone="Direct, useful, editor-to-reader.",
        cta_style="One clear primary CTA (reply, click, or forward).",
        hashtag_policy="none",
        structure="single",
        formatting="markdown",
        guidance=(
            "Write a newsletter in Markdown with Subject line, Preview text, "
            "greeting, scannable body sections, and a single CTA."
        ),
    ),
    "instagram": PlatformPreset(
        id="instagram",
        label="Instagram caption",
        max_chars=2200,
        max_words=None,
        tone="Warm, visual, scroll-stopping.",
        cta_style="Save/share/comment prompt.",
        hashtag_policy="encouraged",
        structure="single",
        formatting="plain",
        guidance=(
            "Write an Instagram caption under ~2,200 characters. "
            "Strong opener, short lines, then 5–10 relevant hashtags at the end."
        ),
    ),
    "threads": PlatformPreset(
        id="threads",
        label="Threads",
        max_chars=500,
        max_words=None,
        tone="Casual, conversational, native to Threads.",
        cta_style="Invite replies; keep it light.",
        hashtag_policy="light",
        structure="thread",
        formatting="plain",
        guidance=(
            "Write a Threads thread. Each post ideally ≤500 characters. "
            "Number posts (1/, 2/, …). First post hooks; keep the chain tight."
        ),
    ),
}

PLATFORM_IDS: tuple[str, ...] = tuple(PLATFORMS.keys())


def get_preset(platform: str) -> PlatformPreset:
    try:
        return PLATFORMS[platform]
    except KeyError as exc:
        raise ValueError(f"Unknown platform: {platform}") from exc


def preset_rules_block(preset: PlatformPreset) -> str:
    caps = []
    if preset.max_chars is not None:
        unit = "per post/tweet" if preset.structure == "thread" else "total"
        caps.append(f"max_chars={preset.max_chars} ({unit})")
    if preset.max_words is not None:
        caps.append(f"max_words≈{preset.max_words}")
    caps_str = ", ".join(caps) if caps else "no hard length cap"
    return (
        f"Platform: {preset.label} ({preset.id})\n"
        f"Structure: {preset.structure}\n"
        f"Formatting: {preset.formatting}\n"
        f"Tone: {preset.tone}\n"
        f"CTA style: {preset.cta_style}\n"
        f"Hashtags: {preset.hashtag_policy}\n"
        f"Length: {caps_str}\n"
        f"Guidance: {preset.guidance}"
    )

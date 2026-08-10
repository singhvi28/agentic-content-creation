"""Default campaign pack helpers."""

from __future__ import annotations

from app.db.models import Platform

DEFAULT_CAMPAIGN_PLATFORMS: tuple[str, ...] = (
    "medium",
    "youtube_script",
    "twitter",
    "linkedin",
)


def build_campaign_platforms(include_newsletter: bool = False) -> list[str]:
    platforms = list(DEFAULT_CAMPAIGN_PLATFORMS)
    if include_newsletter and Platform.newsletter.value not in platforms:
        platforms.append(Platform.newsletter.value)
    return platforms

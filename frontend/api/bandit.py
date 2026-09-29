"""Bandit API services."""

from __future__ import annotations

from frontend.api.client import get_json, post_json


def get_bandit_stats() -> dict:
    """Retrieves current Thompson sampling arm statistics."""
    return get_json("/bandit/stats")


def get_bandit_feedback_logs(limit: int = 50) -> list[dict]:
    """Retrieves recent user feedback logs."""
    return get_json(f"/bandit/feedback?limit={limit}")


def reset_bandit_priors(arm_id: str | None = None) -> dict:
    """Resets bandit arm(s) back to uniform Beta(1,1) priors."""
    body = {"arm_id": arm_id} if arm_id else {}
    return post_json("/bandit/reset", body)

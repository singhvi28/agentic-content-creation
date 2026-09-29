"""Content API services."""

from __future__ import annotations

from frontend.api.client import get_json, post_json


def generate_content(body: dict) -> dict:
    """Enqueues a new content generation job."""
    return post_json("/content/generate", body)


def get_job_detail(job_id: str) -> dict:
    """Retrieves full details of a job."""
    return get_json(f"/content/{job_id}")


def choose_ab_variant(job_id: str, content_version_id: str) -> dict:
    """Selects an A/B hook variant winner."""
    return post_json(f"/content/{job_id}/choose", {"content_version_id": content_version_id})


def submit_job_feedback(job_id: str, body: dict) -> dict:
    """Submits quality feedback for an asset or pack."""
    return post_json(f"/content/{job_id}/feedback", body)


def get_job_usage(job_id: str) -> dict:
    """Retrieves token usage breakdown for a job."""
    return get_json(f"/content/{job_id}/usage")


def list_recent_jobs(limit: int = 30) -> list[dict]:
    """Lists recent generation jobs."""
    return get_json(f"/content/?limit={limit}")

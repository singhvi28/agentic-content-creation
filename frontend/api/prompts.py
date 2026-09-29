"""Prompt templates API services."""

from __future__ import annotations

from frontend.api.client import delete_req, get_json, patch_json, post_json


def list_prompt_templates(stage: str | None = None, active_only: bool = True) -> list[dict]:
    """Retrieves prompt templates with optional stage and active filters."""
    query_params = []
    if stage and stage != "All Stages":
        query_params.append(f"stage={stage}")
    query_params.append(f"active_only={'true' if active_only else 'false'}")
    query_str = "?" + "&".join(query_params) if query_params else ""
    return get_json(f"/prompts/{query_str}")


def create_prompt_template(body: dict) -> dict:
    """Creates a new prompt template."""
    return post_json("/prompts/", body)


def patch_prompt_template(template_id: str, body: dict) -> dict:
    """Creates a new immutable version of a prompt template."""
    return patch_json(f"/prompts/{template_id}", body)


def deactivate_prompt_template(template_id: str) -> None:
    """Deactivates a prompt template."""
    delete_req(f"/prompts/{template_id}")

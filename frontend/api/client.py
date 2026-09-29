"""Base HTTP client utilities for Streamlit frontend."""

from __future__ import annotations

import time

import httpx
import streamlit as st

from frontend.constants.platforms import DEFAULT_API, PAUSE, TERMINAL


def api_base() -> str:
    """Returns the base API URL from session state or default."""
    return st.session_state.get("api_base", DEFAULT_API).rstrip("/")


def get_json(path: str) -> dict | list:
    """Performs a GET request and returns JSON."""
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{api_base()}{path}")
        r.raise_for_status()
        return r.json()


def post_json(path: str, body: dict) -> dict:
    """Performs a POST request with JSON body and returns JSON."""
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{api_base()}{path}", json=body)
        r.raise_for_status()
        return r.json()


def patch_json(path: str, body: dict) -> dict:
    """Performs a PATCH request with JSON body and returns JSON."""
    with httpx.Client(timeout=30.0) as client:
        r = client.patch(f"{api_base()}{path}", json=body)
        r.raise_for_status()
        return r.json()


def delete_req(path: str) -> None:
    """Performs a DELETE request."""
    with httpx.Client(timeout=30.0) as client:
        r = client.delete(f"{api_base()}{path}")
        r.raise_for_status()


def poll_job(job_id: str, status_box, progress) -> dict:
    """Polls a job until it reaches a terminal or pause status."""
    detail: dict = {}
    for i in range(180):
        detail = get_json(f"/content/{job_id}")
        status = detail.get("status", "unknown")
        n_versions = len(detail.get("versions") or [])
        status_box.info(f"Status: **{status}** · versions: {n_versions}")
        progress.progress(min(1.0, (i + 1) / 180))
        if status in TERMINAL or status in PAUSE:
            break
        time.sleep(2)
    progress.progress(1.0)
    return detail

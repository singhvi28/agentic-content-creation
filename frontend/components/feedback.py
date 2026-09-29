"""Quality Feedback & Bandit Learning component."""

from __future__ import annotations

import httpx
import streamlit as st

from frontend.api.content import submit_job_feedback


def render_feedback_ui(detail: dict) -> None:
    """Renders user rating & edit submission form to update bandit posteriors."""
    st.markdown("#### ⭐ Quality Feedback & Bandit Learning")
    assets = detail.get("assets") or []
    versions = detail.get("versions") or []

    if assets:
        asset_options = {
            f"{a['platform']} ({a['version_id'][:8]}…)": a["version_id"]
            for a in assets
        }
        choice = st.selectbox("Asset to rate", list(asset_options.keys()))
        rating = st.slider("Asset rating (1-5 stars)", min_value=1, max_value=5, value=5, key="asset_rating")
        if st.button("Submit Asset Feedback"):
            try:
                submit_job_feedback(
                    detail["job_id"],
                    {
                        "scope": "asset",
                        "content_version_id": asset_options[choice],
                        "rating": rating,
                    },
                )
                st.success("Asset feedback recorded — bandit priors updated.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")

        pack_rating = st.slider(
            "Overall Pack rating (1-5 stars)", min_value=1, max_value=5, value=5, key="pack_rating"
        )
        if st.button("Submit Overall Pack Feedback"):
            try:
                submit_job_feedback(
                    detail["job_id"],
                    {"scope": "pack", "rating": pack_rating},
                )
                st.success("Pack feedback recorded — all campaign bandit arms updated.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")

    elif versions:
        options = {
            f"Round {v['round']} ({v['id'][:8]}…)": v["id"] for v in versions
        }
        choice = st.selectbox("Version to rate", list(options.keys()))
        rating = st.slider("Rating (1-5 stars)", min_value=1, max_value=5, value=5)
        edited = st.text_area("Optional user-edited text (recorded for fine-tuning & bandit)", height=100)
        if st.button("Submit Feedback"):
            try:
                submit_job_feedback(
                    detail["job_id"],
                    {
                        "scope": "asset",
                        "content_version_id": options[choice],
                        "rating": rating,
                        "edited_text": edited.strip() or None,
                    },
                )
                st.success("Feedback recorded — Thompson Sampling bandit updated.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")

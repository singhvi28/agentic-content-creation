"""LLM Token Usage & Cost Analytics component."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api.content import get_job_usage


def render_token_usage_ui(job_id: str) -> None:
    """Renders LLM token usage, cost metrics, and stage breakdown table."""
    try:
        usage_data = get_job_usage(job_id)
    except Exception:
        return

    usages = usage_data.get("usages") or []
    if not usages:
        return

    with st.expander("📊 LLM Token Usage & Cost Breakdown", expanded=False):
        total_tokens = usage_data.get("total_estimated_tokens", 0)
        total_prompt = usage_data.get("total_prompt_chars", 0)
        total_completion = usage_data.get("total_completion_chars", 0)
        # Approximate blended cost per 1M tokens ($0.15/1M tokens default for fast models)
        est_cost = (total_tokens / 1_000_000) * 0.15

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tokens", f"{total_tokens:,}")
        col2.metric("Prompt Chars", f"{total_prompt:,}")
        col3.metric("Completion Chars", f"{total_completion:,}")
        col4.metric("Est. Cost", f"${est_cost:.5f}")

        # Table of individual operations
        df_usage = pd.DataFrame(
            [
                {
                    "Stage / Operation": u["operation"],
                    "Provider": u["provider"],
                    "Model": u["model"],
                    "Tokens": u["estimated_tokens"],
                    "Prompt Chars": u["prompt_chars"],
                    "Completion Chars": u["completion_chars"],
                    "Logged At": u["created_at"][:19].replace("T", " "),
                }
                for u in usages
            ]
        )
        st.dataframe(df_usage, use_container_width=True, hide_index=True)

"""Sidebar navigation and settings component."""

from __future__ import annotations

import streamlit as st

from frontend.api.client import get_json
from frontend.constants.platforms import DEFAULT_API


def render_sidebar() -> str:
    """Renders the sidebar settings and returns the active page selection."""
    with st.sidebar:
        st.header("⚙️ System Settings")
        st.text_input("API base URL", value=DEFAULT_API, key="api_base")
        try:
            health = get_json("/health")
            st.success(f"API {health.get('status', 'ok')}")
        except Exception:
            st.error("API unreachable")

        st.subheader("🤖 Client LLM Settings")
        st.selectbox(
            "Drafting / Generation Model",
            [
                "groq/openai/gpt-oss-20b",
                "groq/openai/gpt-oss-120b",
                "groq/qwen/qwen3.8-27b",
                "groq/allam-2-7b",
                "openai/gpt-4o-mini",
                "fake",
            ],
            key="llm_model",
            help="Choose model for generation. Universal provider support via LiteLLM.",
        )

        st.selectbox(
            "Separate Critic Model (Optional)",
            [
                "Same as Generation Model",
                "groq/openai/gpt-oss-120b",
                "groq/openai/gpt-oss-20b",
                "groq/qwen/qwen3.8-27b",
                "openai/gpt-4o-mini",
                "fake",
            ],
            key="llm_critic_model",
            help="Use a dedicated, higher-precision model specifically for the Critique & Quality evaluation stage.",
        )

        st.text_input(
            "Client API Key (e.g. GROQ_API_KEY)",
            type="password",
            key="llm_api_key",
            help="Client-side API key passed directly to worker memory for this job (never persisted in DB).",
        )

        st.divider()
        page = st.radio(
            "Navigation",
            ["Generate & History", "Prompt Templates", "Bandit Performance"],
            label_visibility="collapsed",
        )
        return page

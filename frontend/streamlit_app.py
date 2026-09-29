"""Agentic Content Pipeline - Main Streamlit Application."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path for modular imports
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from frontend.components.sidebar import render_sidebar
from frontend.views.bandit_view import render_bandit_view
from frontend.views.generate_view import render_generate_view
from frontend.views.prompts_view import render_prompts_view


def main() -> None:
    """Main application orchestrator & router."""
    st.set_page_config(
        page_title="Agentic Content Pipeline",
        page_icon="📝",
        layout="wide",
    )
    st.title("Agentic Content Pipeline")
    st.caption(
        "Autonomous Multi-Turn Content Generation · Thompson Sampling Bandit · Prompt Versioning"
    )

    # Render persistent sidebar navigation & settings
    page = render_sidebar()

    # Route to active view
    if page == "Generate & History":
        render_generate_view()
    elif page == "Prompt Templates":
        render_prompts_view()
    elif page == "Bandit Performance":
        render_bandit_view()


if __name__ == "__main__":
    main()

"""Version Diff & Multi-turn Evolution component."""

from __future__ import annotations

import difflib

import streamlit as st


def render_version_diff_ui(versions: list[dict]) -> None:
    """Renders visual side-by-side comparison and colorized diff between draft and revision."""
    if len(versions) < 2:
        return

    round0 = next((v for v in versions if v.get("round") == 0), versions[0])
    round1 = next((v for v in versions if v.get("round") == 1), versions[-1])

    if round0["id"] == round1["id"]:
        return

    with st.expander("🔍 Version Diff & Multi-Turn Evolution (Draft vs Revision)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            score0 = f" (Critic: {round0['critic_score']}/10)" if round0.get("critic_score") is not None else ""
            st.markdown(f"##### 📝 Round 0 Draft{score0}")
            st.text_area("Round 0 Text", value=round0.get("text", ""), height=220, disabled=True, key="diff_r0")
        with c2:
            score1 = f" (Critic: {round1['critic_score']}/10)" if round1.get("critic_score") is not None else ""
            st.markdown(f"##### ✨ Round 1 Revised Draft{score1}")
            st.text_area("Round 1 Text", value=round1.get("text", ""), height=220, disabled=True, key="diff_r1")

        if round0.get("critic_notes"):
            st.info(f"**Editor Feedback Applied:** {round0['critic_notes']}")

        # Unified line diff
        text0_lines = round0.get("text", "").splitlines(keepends=True)
        text1_lines = round1.get("text", "").splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                text0_lines,
                text1_lines,
                fromfile="Round 0 (Initial Draft)",
                tofile="Round 1 (Revised Draft)",
                lineterm="",
            )
        )
        if diff:
            st.markdown("##### 📄 Unified Line Diff")
            st.code("\n".join(diff), language="diff")

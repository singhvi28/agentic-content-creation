"""A/B Hook Variant Comparison component."""

from __future__ import annotations

import httpx
import streamlit as st

from frontend.api.client import poll_job
from frontend.api.content import choose_ab_variant
from frontend.utils.compliance import calculate_compliance


def render_ab_variant_comparison_ui(detail: dict) -> None:
    """Renders side-by-side A/B hook variant cards with hook highlights and selection."""
    variants = detail.get("variants") or []
    st.markdown("#### 🎯 A/B Hook Variant Comparison")
    st.caption("Compare opening hooks and structure side-by-side. Pick the winner to proceed with full critique & revision.")

    if not variants:
        st.warning("No variants found on this job.")
        return

    cols = st.columns(len(variants))
    for col, variant in zip(cols, variants):
        with col:
            idx = variant.get("variant_index", 0)
            action = variant.get("bandit_action") or {}
            style = action.get("prompt_style", "standard")
            v_text = variant.get("text") or ""

            # Extract first 1-2 lines as hook
            lines = [line.strip() for line in v_text.splitlines() if line.strip()]
            hook_text = " ".join(lines[:2]) if lines else "No hook"

            st.container(border=True)
            st.markdown(f"### 🏷️ Variant #{idx + 1}")
            st.markdown(f"**Bandit Style:** `{style}`")

            # Compliance stats
            comp = calculate_compliance(v_text, detail.get("platform"))
            st.caption(comp["badge"])

            st.markdown("##### 🪝 Hook Line:")
            st.info(f'"{hook_text}"')

            with st.expander("Read Full Draft", expanded=True):
                st.write(v_text)

            if st.button(
                f"🏆 Pick Winner #{idx + 1}",
                key=f"pick_btn_{variant['version_id']}",
                type="primary",
                use_container_width=True,
            ):
                try:
                    choose_ab_variant(detail["job_id"], variant["version_id"])
                    status_box = st.empty()
                    progress = st.progress(0.0)
                    with st.spinner("Resuming pipeline with winning hook…"):
                        new_detail = poll_job(detail["job_id"], status_box, progress)
                    st.session_state["job_detail"] = new_detail
                    st.rerun()
                except httpx.HTTPError as exc:
                    st.error(f"Choose failed: {exc}")

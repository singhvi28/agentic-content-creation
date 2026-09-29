"""Bandit Performance, Feedback Audit, & Priors Reset View."""

from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

from frontend.api.bandit import (
    get_bandit_feedback_logs,
    get_bandit_stats,
    reset_bandit_priors,
)


def render_bandit_view() -> None:
    """Renders the Thompson Sampling Bandit analytics, feedback audit, and reset view."""
    st.subheader("Bandit Performance & Audit")

    tab_stats, tab_feedback, tab_reset = st.tabs(
        ["📊 Thompson Sampling Arms", "📝 Feedback Audit Logs", "⚙️ Reset Priors"]
    )

    with tab_stats:
        if st.button("Refresh Bandit Stats"):
            st.session_state.pop("bandit_stats", None)

        try:
            data = get_bandit_stats()
        except httpx.HTTPError as exc:
            st.error(f"Could not load stats: {exc}")
            return

        arms = data.get("arms") or []
        if not arms:
            st.info("No arms found.")
        else:
            df = pd.DataFrame(arms)
            show = df[
                ["prompt_style", "platform", "alpha", "beta", "mean", "arm_id"]
            ].sort_values(["platform", "mean"], ascending=[True, False])
            st.dataframe(show, use_container_width=True, hide_index=True)

            st.markdown("#### Mean Reward by Style × Platform")
            pivot = show.pivot_table(
                index="prompt_style", columns="platform", values="mean"
            )
            st.bar_chart(pivot)

    with tab_feedback:
        st.markdown("#### User Feedback Audit Trail")
        st.caption(
            "Historical rating and text edit submissions that update posterior Thompson Sampling beta distributions."
        )
        try:
            feedback_logs = get_bandit_feedback_logs(limit=50)
        except Exception as exc:
            st.error(f"Could not load feedback logs: {exc}")
            feedback_logs = []

        if feedback_logs:
            fb_rows = []
            for f in feedback_logs:
                fb_rows.append(
                    {
                        "Rating": f"{f['rating']} ⭐",
                        "Scope": f["scope"],
                        "Job ID": f["job_id"],
                        "Version ID": f.get("content_version_id") or "pack-wide",
                        "User Edited Text": f.get("edited_text") or "None",
                        "Timestamp": f["created_at"][:19].replace("T", " "),
                    }
                )
            st.dataframe(pd.DataFrame(fb_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No feedback entries recorded yet.")

    with tab_reset:
        st.markdown("#### Reset Bandit Priors")
        st.caption(
            "Reset Thompson Sampling beta distributions back to prior α=1.0, β=1.0 (uninformed exploration)."
        )

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("##### Reset Specific Arm")
            try:
                stats_res = get_bandit_stats()
                all_arms = [a["arm_id"] for a in stats_res.get("arms", [])]
            except Exception:
                all_arms = []

            if all_arms:
                selected_arm = st.selectbox("Select Arm to Reset", all_arms)
                if st.button(f"Reset Arm '{selected_arm}'", type="secondary"):
                    try:
                        res = reset_bandit_priors(arm_id=selected_arm)
                        st.success(res.get("message", "Arm reset successfully."))
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Reset failed: {exc}")
            else:
                st.info("No arms available.")

        with col_r2:
            st.markdown("##### Reset All Bandit Arms")
            st.warning("This resets all prompt styles across all platforms back to equal priors.")
            confirm_all = st.checkbox("Confirm reset of all arms")
            if st.button("Reset All Arms to Prior (α=1, β=1)", type="primary", disabled=not confirm_all):
                try:
                    res = reset_bandit_priors()
                    st.success(res.get("message", "All arms reset successfully."))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Reset failed: {exc}")

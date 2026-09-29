"""Job History & Direct UUID Lookup component."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api.content import get_job_detail, list_recent_jobs


def render_job_history_ui() -> None:
    """Renders job lookup and history table."""
    st.markdown("#### Job History & Direct Lookup")
    c_search, c_btn = st.columns([3, 1])
    with c_search:
        lookup_uuid = st.text_input("Look up Job by UUID", placeholder="e.g. 296d882c-855e-418e-9061-4f7dd52e7998")
    with c_btn:
        st.write("")
        st.write("")
        if st.button("Load Job", disabled=not lookup_uuid.strip()):
            try:
                loaded_detail = get_job_detail(lookup_uuid.strip())
                st.session_state["job_detail"] = loaded_detail
                st.session_state["job_id"] = lookup_uuid.strip()
                st.success(f"Loaded job `{lookup_uuid.strip()}`")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load job: {exc}")

    st.divider()
    try:
        recent_jobs = list_recent_jobs(limit=30)
    except Exception as exc:
        st.error(f"Failed to load recent jobs: {exc}")
        recent_jobs = []

    if recent_jobs:
        st.markdown(f"Found **{len(recent_jobs)}** recent job(s):")
        jobs_table = []
        for j in recent_jobs:
            stat_emoji = (
                "🟢"
                if j["status"] == "done"
                else "🟡"
                if j["status"] == "awaiting_choice"
                else "🔴"
                if j["status"] == "failed"
                else "⏳"
            )
            jobs_table.append(
                {
                    "Select": j["job_id"],
                    "Status": f"{stat_emoji} {j['status']}",
                    "Type": j["job_type"],
                    "Platform": j.get("platform") or "multi-pack",
                    "Brief": (j.get("brief") or "")[:45] + "…",
                    "Model": j.get("llm_model") or "default",
                    "Created At": j["created_at"][:19].replace("T", " "),
                }
            )
        df_jobs = pd.DataFrame(jobs_table)
        st.dataframe(df_jobs.drop(columns=["Select"]), use_container_width=True, hide_index=True)

        job_select_map = {
            f"{row['Status']} · {row['Platform']} · {row['Brief']} ({row['Created At']})": row["Select"]
            for row in jobs_table
        }
        chosen_hist_label = st.selectbox("Select job to inspect/resume", list(job_select_map.keys()))
        if st.button("Load Selected Job from History", type="secondary"):
            selected_jid = job_select_map[chosen_hist_label]
            try:
                loaded_detail = get_job_detail(selected_jid)
                st.session_state["job_detail"] = loaded_detail
                st.session_state["job_id"] = selected_jid
                st.success(f"Loaded job `{selected_jid}`")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load job: {exc}")
    else:
        st.info("No past generation jobs found yet.")

"""Generation & Active Job View."""

from __future__ import annotations

import httpx
import streamlit as st

from frontend.api.client import poll_job
from frontend.api.content import generate_content
from frontend.api.prompts import list_prompt_templates
from frontend.components.ab_variants import render_ab_variant_comparison_ui
from frontend.components.feedback import render_feedback_ui
from frontend.components.job_history import render_job_history_ui
from frontend.components.token_usage import render_token_usage_ui
from frontend.components.version_diff import render_version_diff_ui
from frontend.constants.platforms import PLATFORMS
from frontend.utils.compliance import calculate_compliance


def render_active_job(detail: dict) -> None:
    """Renders the complete view of an active or completed generation job."""
    st.divider()
    status = detail.get("status", "unknown")
    job_type = detail.get("job_type", "single")
    pt_info = detail.get("prompt_template")
    pt_badge = (
        f" · template=`{pt_info['name']} ({pt_info['version_tag']})`"
        if pt_info
        else ""
    )
    st.markdown(
        f"### 📋 Active Job: `{detail.get('job_id')}` · **{status.upper()}** · type=`{job_type}`{pt_badge}"
    )

    if status == "failed":
        st.error(detail.get("error_message") or "Job failed")
        return

    # Render Token Usage Analytics
    render_token_usage_ui(detail["job_id"])

    # A/B pick-winner UI
    if status == "awaiting_choice":
        render_ab_variant_comparison_ui(detail)
        return

    # Shared content strategy plan (campaigns)
    if detail.get("shared_plan"):
        st.markdown("#### 🗺️ Shared Content Strategy Plan")
        st.text_area(
            "shared_plan",
            value=detail["shared_plan"],
            height=150,
            label_visibility="collapsed",
        )

    # Cross-surface Cohesion Score
    if detail.get("cross_surface_score") is not None:
        score_val = detail["cross_surface_score"]
        score_badge = (
            "🟢 High Alignment"
            if score_val >= 8.0
            else "🟡 Moderate Alignment"
            if score_val >= 6.0
            else "🔴 Low Alignment"
        )
        st.markdown(
            f"**Cross-surface Cohesion Score:** `{score_val}/10` ({score_badge}) — "
            f"*{detail.get('cross_surface_notes') or ''}*"
        )

    # Visual Version Diff for single jobs
    versions = detail.get("versions") or []
    assets = detail.get("assets") or []
    if versions and not assets:
        render_version_diff_ui(versions)

    # Render Campaign Assets
    if assets:
        st.markdown("#### 📦 Campaign Pack Assets")
        for asset in assets:
            comp = calculate_compliance(asset.get("text", ""), asset.get("platform"))
            score_str = f" · critic={asset.get('critic_score')}/10" if asset.get("critic_score") is not None else ""
            with st.expander(
                f"🏷️ {asset['platform'].upper()} {score_str} · {comp['badge']}",
                expanded=True,
            ):
                st.markdown(f"**Compliance:** {comp['badge']}")
                st.write(asset.get("text") or "")
                if asset.get("critic_notes"):
                    st.info(f"**Critic Review:** {asset['critic_notes']}")

        # Download Campaign Pack
        if detail.get("final_content"):
            st.download_button(
                label="📥 Download Full Campaign Pack (.md)",
                data=detail["final_content"],
                file_name=f"campaign_pack_{detail['job_id'][:8]}.md",
                mime="text/markdown",
            )

    # Render Final Content (Single Post)
    if detail.get("final_content") and not assets:
        st.markdown("#### ✨ Final Generated Content")
        comp = calculate_compliance(detail["final_content"], detail.get("platform"))
        st.caption(f"**Platform Compliance:** {comp['badge']}")
        st.text_area(
            "final",
            value=detail["final_content"],
            height=240,
            label_visibility="collapsed",
        )
        st.download_button(
            label="📥 Download Final Post (.md)",
            data=detail["final_content"],
            file_name=f"post_{detail.get('platform', 'content')}_{detail['job_id'][:8]}.md",
            mime="text/markdown",
        )

    # Render Multi-turn Rounds History
    if versions and not assets:
        with st.expander(f"📚 Iteration History ({len(versions)} rounds recorded)", expanded=False):
            for v in versions:
                action = v.get("bandit_action") or {}
                style = action.get("prompt_style", "?")
                vi = v.get("variant_index")
                variant_bit = f" · AB#{vi + 1}" if vi is not None else ""
                comp_v = calculate_compliance(v.get("text", ""), detail.get("platform"))
                label = (
                    f"Round {v['round']}{variant_bit} · style={style} · "
                    f"critic={v.get('critic_score')} · {comp_v['badge']}"
                )
                st.markdown(f"**{label}**")
                st.write(v.get("text") or "")
                if v.get("critic_notes"):
                    st.caption(f"Critic Notes: {v['critic_notes']}")
                st.divider()

    # Feedback Section
    render_feedback_ui(detail)


def render_generate_view() -> None:
    """Renders the main content generation view with Creation and History tabs."""
    st.subheader("Content Generation & History")

    tab_gen, tab_hist = st.tabs(["🚀 Create New Generation", "📜 Recent Generations & History"])

    with tab_hist:
        render_job_history_ui()

    with tab_gen:
        mode = st.radio("Mode", ["Single platform", "Campaign pack"], horizontal=True)

        brief = st.text_area(
            "Brief",
            height=130,
            placeholder="e.g. Write about shipping faster with CI/CD and automated regression suites…",
        )

        platform_label = None
        include_newsletter = False
        ab_choice = "Off"
        if mode == "Single platform":
            col_p, col_ab = st.columns([2, 1])
            with col_p:
                platform_label = st.selectbox("Platform", list(PLATFORMS.keys()))
            with col_ab:
                ab_choice = st.selectbox(
                    "A/B Hook Variants",
                    ["Off", "2", "3"],
                    help="Generate multiple drafts with distinct opening hooks, then pick a winner.",
                )
        else:
            st.caption(
                "Default pack generates synchronized assets for Medium, YouTube script, X thread, and LinkedIn. "
                "Optional newsletter teaser."
            )
            include_newsletter = st.checkbox("Include newsletter teaser", value=False)

        # Prompt template selection
        prompt_templates = []
        try:
            prompt_templates = list_prompt_templates(active_only=True)
        except Exception:
            pass

        selected_pt_id = None
        if prompt_templates:
            pt_options = {"System Defaults": None}
            for pt in prompt_templates:
                label = f"{pt['name']} ({pt['version_tag']}) · [{pt['stage']}]"
                pt_options[label] = pt["id"]
            chosen_pt_label = st.selectbox(
                "Custom Prompt Template (Optional)",
                list(pt_options.keys()),
                help="Override default system prompt for the specified stage with a custom versioned template.",
            )
            selected_pt_id = pt_options[chosen_pt_label]
            if selected_pt_id:
                chosen_pt = next((p for p in prompt_templates if p["id"] == selected_pt_id), None)
                if chosen_pt:
                    with st.expander(f"Preview: {chosen_pt['name']} ({chosen_pt['version_tag']})", expanded=False):
                        st.caption(f"Stage: `{chosen_pt['stage']}` · Description: {chosen_pt.get('description') or 'None'}")
                        st.code(chosen_pt["template"], language="markdown")

        if st.button("Generate Content", type="primary", disabled=not brief.strip()):
            llm_model = st.session_state.get("llm_model", "").strip() or None
            llm_critic_model = st.session_state.get("llm_critic_model", "").strip() or None
            if llm_critic_model == "Same as Generation Model":
                llm_critic_model = None
            llm_api_key = st.session_state.get("llm_api_key", "").strip() or None

            try:
                if mode == "Campaign pack":
                    body = {
                        "brief": brief.strip(),
                        "job_type": "campaign",
                        "include_newsletter": include_newsletter,
                    }
                else:
                    body = {
                        "brief": brief.strip(),
                        "job_type": "single",
                        "platform": PLATFORMS[platform_label],
                    }
                    if ab_choice != "Off":
                        body["ab_variants"] = int(ab_choice)

                if selected_pt_id:
                    body["prompt_template_id"] = selected_pt_id
                if llm_model:
                    body["llm_model"] = llm_model
                if llm_critic_model:
                    body["llm_critic_model"] = llm_critic_model
                if llm_api_key:
                    body["llm_api_key"] = llm_api_key

                created = generate_content(body)
            except httpx.HTTPError as exc:
                st.error(f"Failed to enqueue job: {exc}")
                return

            job_id = created["job_id"]
            st.session_state["job_id"] = job_id
            st.success(f"Queued job `{job_id}`")

            status_box = st.empty()
            progress = st.progress(0.0)
            with st.spinner("Running agentic pipeline…"):
                try:
                    detail = poll_job(job_id, status_box, progress)
                except httpx.HTTPError as exc:
                    st.error(f"Polling failed: {exc}")
                    return
            st.session_state["job_detail"] = detail

    detail = st.session_state.get("job_detail")
    if detail:
        render_active_job(detail)

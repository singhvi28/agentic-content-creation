"""Enhanced Streamlit UI for the agentic content pipeline."""

from __future__ import annotations

import difflib
import time
from datetime import datetime

import httpx
import pandas as pd
import streamlit as st

DEFAULT_API = "http://127.0.0.1:8000"

PLATFORM_LIMITS = {
    "linkedin": {"label": "LinkedIn", "max_chars": 1300, "max_words": None, "type": "single"},
    "twitter": {"label": "X / Twitter", "max_chars": 280, "max_words": None, "type": "thread"},
    "medium": {"label": "Medium", "max_chars": None, "max_words": 1500, "type": "single"},
    "youtube_script": {"label": "YouTube script", "max_chars": None, "max_words": 1200, "type": "single"},
    "newsletter": {"label": "Newsletter", "max_chars": None, "max_words": 900, "type": "single"},
    "instagram": {"label": "Instagram caption", "max_chars": 2200, "max_words": None, "type": "single"},
    "threads": {"label": "Threads", "max_chars": 500, "max_words": None, "type": "thread"},
}

PLATFORMS = {
    "LinkedIn": "linkedin",
    "X / Twitter": "twitter",
    "Medium": "medium",
    "YouTube script": "youtube_script",
    "Newsletter": "newsletter",
    "Instagram caption": "instagram",
    "Threads": "threads",
}
TERMINAL = {"done", "failed"}
PAUSE = {"awaiting_choice"}


def api_base() -> str:
    return st.session_state.get("api_base", DEFAULT_API).rstrip("/")


def get_json(path: str) -> dict | list:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{api_base()}{path}")
        r.raise_for_status()
        return r.json()


def post_json(path: str, body: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{api_base()}{path}", json=body)
        r.raise_for_status()
        return r.json()


def patch_json(path: str, body: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        r = client.patch(f"{api_base()}{path}", json=body)
        r.raise_for_status()
        return r.json()


def delete_req(path: str) -> None:
    with httpx.Client(timeout=30.0) as client:
        r = client.delete(f"{api_base()}{path}")
        r.raise_for_status()


def poll_job(job_id: str, status_box, progress) -> dict:
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


def calculate_compliance(text: str, platform_key: str | None) -> dict:
    """Calculates character & word stats and compliance against platform limits."""
    if not text:
        return {"chars": 0, "words": 0, "status": "ok", "badge": "0 chars"}

    chars = len(text)
    words = len(text.split())
    rule = PLATFORM_LIMITS.get(platform_key or "")

    if not rule:
        return {"chars": chars, "words": words, "status": "ok", "badge": f"📊 {chars:,} chars · {words:,} words"}

    max_chars = rule.get("max_chars")
    max_words = rule.get("max_words")
    is_thread = rule.get("type") == "thread"

    if is_thread and platform_key == "twitter":
        # Split thread tweets by double newline or numbered items
        tweets = [t.strip() for t in text.split("\n\n") if t.strip()]
        thread_overflow = False
        tweet_badges = []
        for i, tw in enumerate(tweets, 1):
            tw_len = len(tw)
            if tw_len > 280:
                thread_overflow = True
                tweet_badges.append(f"T{i}: {tw_len}/280 🔴")
            else:
                tweet_badges.append(f"T{i}: {tw_len}/280 🟢")
        status_icon = "🔴 Exceeds 280-char cap" if thread_overflow else "🟢 Valid thread"
        return {
            "chars": chars,
            "words": words,
            "status": "error" if thread_overflow else "ok",
            "badge": f"{status_icon} ({len(tweets)} tweets: {' · '.join(tweet_badges[:4])}{'...' if len(tweet_badges) > 4 else ''})",
        }

    if max_chars:
        pct = int((chars / max_chars) * 100)
        if chars > max_chars:
            diff = chars - max_chars
            return {
                "chars": chars,
                "words": words,
                "status": "error",
                "badge": f"🔴 {chars:,} / {max_chars:,} chars (+{diff:,} over cap, {pct}%) · {words:,} words",
            }
        return {
            "chars": chars,
            "words": words,
            "status": "ok",
            "badge": f"🟢 {chars:,} / {max_chars:,} chars ({pct}%) · {words:,} words",
        }

    if max_words:
        pct = int((words / max_words) * 100)
        if words > max_words:
            diff = words - max_words
            return {
                "chars": chars,
                "words": words,
                "status": "error",
                "badge": f"🔴 {words:,} / {max_words:,} words (+{diff:,} over cap, {pct}%) · {chars:,} chars",
            }
        return {
            "chars": chars,
            "words": words,
            "status": "ok",
            "badge": f"🟢 {words:,} / {max_words:,} words ({pct}%) · {chars:,} chars",
        }

    return {"chars": chars, "words": words, "status": "ok", "badge": f"📊 {chars:,} chars · {words:,} words"}


def render_token_usage_ui(job_id: str) -> None:
    """Renders LLM token usage, cost metrics, and stage breakdown table."""
    try:
        usage_data = get_json(f"/content/{job_id}/usage")
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
                    post_json(
                        f"/content/{detail['job_id']}/choose",
                        {"content_version_id": variant["version_id"]},
                    )
                    status_box = st.empty()
                    progress = st.progress(0.0)
                    with st.spinner("Resuming pipeline with winning hook…"):
                        new_detail = poll_job(detail["job_id"], status_box, progress)
                    st.session_state["job_detail"] = new_detail
                    st.rerun()
                except httpx.HTTPError as exc:
                    st.error(f"Choose failed: {exc}")


def page_generate() -> None:
    st.subheader("Content Generation & History")

    tab_gen, tab_hist = st.tabs(["🚀 Create New Generation", "📜 Recent Generations & History"])

    with tab_hist:
        st.markdown("#### Job History & Direct Lookup")
        c_search, c_btn = st.columns([3, 1])
        with c_search:
            lookup_uuid = st.text_input("Look up Job by UUID", placeholder="e.g. 296d882c-855e-418e-9061-4f7dd52e7998")
        with c_btn:
            st.write("")
            st.write("")
            if st.button("Load Job", disabled=not lookup_uuid.strip()):
                try:
                    loaded_detail = get_json(f"/content/{lookup_uuid.strip()}")
                    st.session_state["job_detail"] = loaded_detail
                    st.session_state["job_id"] = lookup_uuid.strip()
                    st.success(f"Loaded job `{lookup_uuid.strip()}`")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not load job: {exc}")

        st.divider()
        try:
            recent_jobs = get_json("/content/?limit=30")
        except Exception as exc:
            st.error(f"Failed to load recent jobs: {exc}")
            recent_jobs = []

        if recent_jobs:
            st.markdown(f"Found **{len(recent_jobs)}** recent job(s):")
            jobs_table = []
            for j in recent_jobs:
                stat_emoji = "🟢" if j["status"] == "done" else "🟡" if j["status"] == "awaiting_choice" else "🔴" if j["status"] == "failed" else "⏳"
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
                    loaded_detail = get_json(f"/content/{selected_jid}")
                    st.session_state["job_detail"] = loaded_detail
                    st.session_state["job_id"] = selected_jid
                    st.success(f"Loaded job `{selected_jid}`")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not load job: {exc}")
        else:
            st.info("No past generation jobs found yet.")

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
            prompt_templates = get_json("/prompts/?active_only=true")
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

                created = post_json("/content/generate", body)
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
    if not detail:
        return

    st.divider()
    status = detail.get("status")
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

    if detail.get("shared_plan"):
        st.markdown("#### 🗺️ Shared Content Strategy Plan")
        st.text_area(
            "shared_plan",
            value=detail["shared_plan"],
            height=150,
            label_visibility="collapsed",
        )

    if detail.get("cross_surface_score") is not None:
        score_val = detail["cross_surface_score"]
        score_badge = "🟢 High Alignment" if score_val >= 8.0 else "🟡 Moderate Alignment" if score_val >= 6.0 else "🔴 Low Alignment"
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
    st.markdown("#### ⭐ Quality Feedback & Bandit Learning")
    if assets:
        asset_options = {
            f"{a['platform']} ({a['version_id'][:8]}…)": a["version_id"]
            for a in assets
        }
        choice = st.selectbox("Asset to rate", list(asset_options.keys()))
        rating = st.slider("Asset rating (1-5 stars)", min_value=1, max_value=5, value=5, key="asset_rating")
        if st.button("Submit Asset Feedback"):
            try:
                post_json(
                    f"/content/{detail['job_id']}/feedback",
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
                post_json(
                    f"/content/{detail['job_id']}/feedback",
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
                post_json(
                    f"/content/{detail['job_id']}/feedback",
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


def page_prompts() -> None:
    st.subheader("Prompt Templates & Versioning")
    st.caption(
        "Manage versioned prompt templates across Plan, Draft, Critique, and Revise stages. "
        "Edits create immutable new version rows to preserve full historical reproducibility."
    )

    tab1, tab2, tab3 = st.tabs(
        ["Saved Templates & History", "Create New Template", "System Defaults Reference"]
    )

    with tab1:
        col1, col2 = st.columns([3, 1])
        with col1:
            stage_filter = st.selectbox(
                "Filter by Stage",
                ["All Stages", "plan", "draft", "critique", "revise"],
                key="prompts_stage_filter",
            )
        with col2:
            active_only = st.checkbox("Active only", value=True, key="prompts_active_only")

        query_params = []
        if stage_filter != "All Stages":
            query_params.append(f"stage={stage_filter}")
        query_params.append(f"active_only={'true' if active_only else 'false'}")
        query_str = "?" + "&".join(query_params) if query_params else ""

        try:
            templates = get_json(f"/prompts/{query_str}")
        except Exception as exc:
            st.error(f"Could not load templates: {exc}")
            templates = []

        if not templates:
            st.info("No prompt templates found. Create one in the 'Create New Template' tab.")
        else:
            st.write(f"Found **{len(templates)}** template version(s).")
            # Group by name
            grouped: dict[str, list[dict]] = {}
            for t in templates:
                grouped.setdefault(t["name"], []).append(t)

            for name, versions in grouped.items():
                st.markdown(f"### 📋 {name}")
                for v in versions:
                    active_badge = "🟢 Active" if v["is_active"] else "🔴 Inactive"
                    expander_title = (
                        f"{v['version_tag']} · stage: {v['stage']} · {active_badge} "
                        f"({v['created_at'][:19].replace('T', ' ')})"
                    )
                    with st.expander(expander_title, expanded=(v == versions[0])):
                        st.markdown(f"**ID:** `{v['id']}`")
                        if v.get("description"):
                            st.markdown(f"**Description:** {v['description']}")
                        st.markdown("**Template Body:**")
                        st.code(v["template"], language="markdown")

                        st.divider()
                        st.markdown("##### Create Next Immutable Version")
                        with st.form(key=f"edit_form_{v['id']}"):
                            next_tag = st.text_input(
                                "New Version Tag",
                                value="",
                                placeholder="e.g. v2 (leave blank to auto-increment)",
                            )
                            updated_desc = st.text_input(
                                "Updated Description",
                                value=v.get("description") or "",
                            )
                            updated_text = st.text_area(
                                "Updated Template Body",
                                value=v["template"],
                                height=160,
                            )
                            submit_patch = st.form_submit_button("Save as New Version", type="primary")
                            if submit_patch:
                                try:
                                    patch_body = {
                                        "template": updated_text.strip(),
                                        "description": updated_desc.strip() or None,
                                    }
                                    if next_tag.strip():
                                        patch_body["version_tag"] = next_tag.strip()
                                    new_v = patch_json(f"/prompts/{v['id']}", patch_body)
                                    st.success(f"Created new immutable version `{new_v['version_tag']}` (ID: `{new_v['id']}`)!")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to update template: {exc}")

                        if v["is_active"]:
                            if st.button("Deactivate this version", key=f"del_{v['id']}"):
                                try:
                                    delete_req(f"/prompts/{v['id']}")
                                    st.success("Template version deactivated.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to deactivate: {exc}")

    with tab2:
        st.markdown("#### Create a New Prompt Template")
        st.caption("Custom templates can override the default prompt for any specific pipeline stage.")

        with st.form(key="create_prompt_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                new_name = st.text_input("Template Name", placeholder="e.g. Viral Technical Hook")
                new_stage = st.selectbox("Pipeline Stage", ["plan", "draft", "critique", "revise"])
            with col_b:
                new_version_tag = st.text_input("Initial Version Tag", value="v1")
                new_desc = st.text_input("Description (optional)", placeholder="e.g. Optimized for high engagement on LinkedIn")

            default_example = (
                "You are an expert content strategist.\n\n"
                "Brief: {brief}\nPlatform: {platform}\nStyle: {style}\n\n"
                "{rules}\n\n"
                "Write a high-converting draft addressing the core pain points."
            )
            new_tpl_body = st.text_area(
                "Template Body",
                value=default_example,
                height=180,
                help="Use {var} placeholders for dynamic variables filled during pipeline execution.",
            )

            with st.expander("ℹ️ Available Template Variables by Stage", expanded=False):
                st.markdown(
                    """
                    - **Plan Stage (`plan`):** `{brief}`, `{platform}`, `{prompt_style}`, `{style}`, `{rules}`, `{structure_hint}`
                    - **Draft Stage (`draft`):** `{brief}`, `{platform}`, `{prompt_style}`, `{plan}`, `{style}`, `{rules}`, `{format_hint}`, `{thread_hint}`
                    - **Critique Stage (`critique`):** `{brief}`, `{platform}`, `{draft}`
                    - **Revise Stage (`revise`):** `{brief}`, `{platform}`, `{draft}`, `{feedback}`, `{notes}`
                    """
                )

            submit_create = st.form_submit_button("Create Prompt Template", type="primary")
            if submit_create:
                if not new_name.strip() or not new_tpl_body.strip():
                    st.error("Name and Template Body are required.")
                else:
                    try:
                        create_body = {
                            "name": new_name.strip(),
                            "stage": new_stage,
                            "template": new_tpl_body.strip(),
                            "version_tag": new_version_tag.strip() or "v1",
                            "description": new_desc.strip() or None,
                        }
                        created = post_json("/prompts/", create_body)
                        st.success(f"Created template `{created['name']}` ({created['version_tag']}) with ID `{created['id']}`!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create template: {exc}")

    with tab3:
        st.markdown("#### System Default Prompts")
        st.caption("Reference copies of the hardcoded system prompts used when no custom template override is provided.")

        with st.expander("1. Planning Prompt (`plan`)", expanded=True):
            st.code(
                """You are a content strategist. Create a short outline/plan for the following brief.

{rules}

Style: {style}
Structure hint: {structure_hint}

Brief:
{brief}

Return a numbered outline only (5–8 bullets). No draft yet.""",
                language="markdown",
            )

        with st.expander("2. Drafting Prompt (`draft` / single & campaign)"):
            st.code(
                """You are a content strategist writing for {platform}.
Draft the complete post/article based on the brief and plan below.

Style instructions: {style}
{rules}
{format_hint}
{thread_hint}

Brief:
{brief}

Plan:
{plan}

Write the full final draft now. No preamble, no commentary.""",
                language="markdown",
            )

        with st.expander("3. Critique Prompt (`critique`)"):
            st.code(
                """You are a tough copy editor evaluating a draft for {platform}.

Brief:
{brief}

Draft:
{draft}

Evaluate readability, structure, platform fit, and hook strength.
Return a valid JSON object matching the schema:
{"score": <1.0-10.0>, "notes": "<concise actionable critique>", "passed": <true/false>}""",
                language="json",
            )

        with st.expander("4. Revision Prompt (`revise`)"):
            st.code(
                """You are an editor revising a draft for {platform}.

Brief:
{brief}

Original draft:
{draft}

Editor feedback:
{feedback}

Rewrite the draft addressing ALL editor feedback. Return only the revised text.""",
                language="markdown",
            )


def page_bandit() -> None:
    st.subheader("Bandit Performance & Audit")

    tab_stats, tab_feedback, tab_reset = st.tabs(
        ["📊 Thompson Sampling Arms", "📝 Feedback Audit Logs", "⚙️ Reset Priors"]
    )

    with tab_stats:
        if st.button("Refresh Bandit Stats"):
            st.session_state.pop("bandit_stats", None)

        try:
            data = get_json("/bandit/stats")
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
        st.caption("Historical rating and text edit submissions that update posterior Thompson Sampling beta distributions.")
        try:
            feedback_logs = get_json("/bandit/feedback?limit=50")
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
        st.caption("Reset Thompson Sampling beta distributions back to prior α=1.0, β=1.0 (uninformed exploration).")

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("##### Reset Specific Arm")
            try:
                stats_res = get_json("/bandit/stats")
                all_arms = [a["arm_id"] for a in stats_res.get("arms", [])]
            except Exception:
                all_arms = []

            if all_arms:
                selected_arm = st.selectbox("Select Arm to Reset", all_arms)
                if st.button(f"Reset Arm '{selected_arm}'", type="secondary"):
                    try:
                        res = post_json("/bandit/reset", {"arm_id": selected_arm})
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
                    res = post_json("/bandit/reset", {})
                    st.success(res.get("message", "All arms reset successfully."))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Reset failed: {exc}")


def main() -> None:
    st.set_page_config(
        page_title="Agentic Content Pipeline",
        page_icon="📝",
        layout="wide",
    )
    st.title("Agentic Content Pipeline")
    st.caption(
        "Autonomous Multi-Turn Content Generation · Thompson Sampling Bandit · Prompt Versioning"
    )

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

    if page == "Generate & History":
        page_generate()
    elif page == "Prompt Templates":
        page_prompts()
    else:
        page_bandit()


if __name__ == "__main__":
    main()

"""Basic Streamlit UI for the agentic content pipeline."""

from __future__ import annotations

import time

import httpx
import pandas as pd
import streamlit as st

DEFAULT_API = "http://127.0.0.1:8000"
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


def api_base() -> str:
    return st.session_state.get("api_base", DEFAULT_API).rstrip("/")


def get_json(path: str) -> dict:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{api_base()}{path}")
        r.raise_for_status()
        return r.json()


def post_json(path: str, body: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{api_base()}{path}", json=body)
        r.raise_for_status()
        return r.json()


def poll_job(job_id: str, status_box, progress) -> dict:
    detail: dict = {}
    for i in range(180):
        detail = get_json(f"/content/{job_id}")
        status = detail.get("status", "unknown")
        n_versions = len(detail.get("versions") or [])
        status_box.info(f"Status: **{status}** · versions: {n_versions}")
        progress.progress(min(1.0, (i + 1) / 180))
        if status in TERMINAL:
            break
        time.sleep(2)
    progress.progress(1.0)
    return detail


def page_generate() -> None:
    st.subheader("Generate content")
    mode = st.radio("Mode", ["Single platform", "Campaign pack"], horizontal=True)

    brief = st.text_area(
        "Brief",
        height=140,
        placeholder="e.g. Write about shipping faster with CI…",
    )

    platform_label = None
    include_newsletter = False
    if mode == "Single platform":
        platform_label = st.selectbox("Platform", list(PLATFORMS.keys()))
    else:
        st.caption(
            "Default pack: Medium, YouTube script, X thread, LinkedIn. "
            "Optional newsletter teaser."
        )
        include_newsletter = st.checkbox("Include newsletter teaser", value=False)

    if st.button("Generate", type="primary", disabled=not brief.strip()):
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
            created = post_json("/content/generate", body)
        except httpx.HTTPError as exc:
            st.error(f"Failed to enqueue job: {exc}")
            return

        job_id = created["job_id"]
        st.session_state["job_id"] = job_id
        st.success(f"Queued job `{job_id}`")

        status_box = st.empty()
        progress = st.progress(0.0)
        with st.spinner("Running pipeline…"):
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
    st.markdown(
        f"**Job** `{detail.get('job_id')}` · **{status}** · type=`{job_type}`"
    )

    if status == "failed":
        st.error(detail.get("error_message") or "Job failed")
        return

    if detail.get("shared_plan"):
        st.markdown("#### Shared plan")
        st.text_area(
            "shared_plan",
            value=detail["shared_plan"],
            height=140,
            label_visibility="collapsed",
        )

    if detail.get("cross_surface_score") is not None:
        st.markdown(
            f"**Cross-surface score:** {detail['cross_surface_score']} — "
            f"{detail.get('cross_surface_notes') or ''}"
        )

    assets = detail.get("assets") or []
    if assets:
        st.markdown("#### Campaign assets")
        for asset in assets:
            with st.expander(
                f"{asset['platform']} · critic={asset.get('critic_score')}",
                expanded=True,
            ):
                st.write(asset.get("text") or "")
                if asset.get("critic_notes"):
                    st.caption(asset["critic_notes"])

    if detail.get("final_content") and not assets:
        st.markdown("#### Final content")
        st.text_area(
            "final",
            value=detail["final_content"],
            height=220,
            label_visibility="collapsed",
        )

    versions = detail.get("versions") or []
    if versions and not assets:
        st.markdown("#### Versions")
        for v in versions:
            action = v.get("bandit_action") or {}
            style = action.get("prompt_style", "?")
            label = (
                f"Round {v['round']} · style={style} · "
                f"critic={v.get('critic_score')}"
            )
            with st.expander(label, expanded=(v["round"] == versions[-1]["round"])):
                st.write(v.get("text") or "")
                if v.get("critic_notes"):
                    st.caption(v["critic_notes"])

    # Feedback
    st.markdown("#### Feedback")
    if assets:
        asset_options = {
            f"{a['platform']} ({a['version_id'][:8]}…)": a["version_id"]
            for a in assets
        }
        choice = st.selectbox("Asset to rate", list(asset_options.keys()))
        rating = st.slider("Asset rating", min_value=1, max_value=5, value=4, key="asset_rating")
        if st.button("Submit asset feedback"):
            try:
                post_json(
                    f"/content/{detail['job_id']}/feedback",
                    {
                        "scope": "asset",
                        "content_version_id": asset_options[choice],
                        "rating": rating,
                    },
                )
                st.success("Asset feedback recorded.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")

        pack_rating = st.slider(
            "Pack rating", min_value=1, max_value=5, value=4, key="pack_rating"
        )
        if st.button("Submit pack feedback"):
            try:
                post_json(
                    f"/content/{detail['job_id']}/feedback",
                    {"scope": "pack", "rating": pack_rating},
                )
                st.success("Pack feedback recorded — all used arms updated.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")
    elif versions:
        options = {
            f"Round {v['round']} ({v['id'][:8]}…)": v["id"] for v in versions
        }
        choice = st.selectbox("Version to rate", list(options.keys()))
        rating = st.slider("Rating", min_value=1, max_value=5, value=4)
        edited = st.text_area("Optional edit (saved with feedback)", height=100)
        if st.button("Submit feedback"):
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
                st.success("Feedback recorded — bandit updated.")
            except httpx.HTTPError as exc:
                st.error(f"Feedback failed: {exc}")


def page_bandit() -> None:
    st.subheader("Bandit stats")
    if st.button("Refresh"):
        st.session_state.pop("bandit_stats", None)

    try:
        data = get_json("/bandit/stats")
    except httpx.HTTPError as exc:
        st.error(f"Could not load stats: {exc}")
        return

    arms = data.get("arms") or []
    if not arms:
        st.info("No arms yet.")
        return

    df = pd.DataFrame(arms)
    show = df[
        ["prompt_style", "platform", "alpha", "beta", "mean", "arm_id"]
    ].sort_values(["platform", "mean"], ascending=[True, False])
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("#### Mean reward by style × platform")
    pivot = show.pivot_table(
        index="prompt_style", columns="platform", values="mean"
    )
    st.bar_chart(pivot)


def main() -> None:
    st.set_page_config(
        page_title="Content Pipeline",
        page_icon="📝",
        layout="wide",
    )
    st.title("Agentic Content Pipeline")
    st.caption(
        "Single platforms or campaign packs · Thompson Sampling over style × platform"
    )

    with st.sidebar:
        st.header("Settings")
        st.text_input("API base URL", value=DEFAULT_API, key="api_base")
        try:
            health = get_json("/health")
            st.success(f"API {health.get('status', 'ok')}")
        except Exception:
            st.error("API unreachable")

        page = st.radio(
            "Page", ["Generate", "Bandit stats"], label_visibility="collapsed"
        )

    if page == "Generate":
        page_generate()
    else:
        page_bandit()


if __name__ == "__main__":
    main()

"""Basic Streamlit UI for the agentic content pipeline."""

from __future__ import annotations

import time

import httpx
import pandas as pd
import streamlit as st

DEFAULT_API = "http://127.0.0.1:8000"
CONTENT_TYPES = {
    "Blog post": "blog_post",
    "Social post": "social_post",
    "Email": "email",
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
    for i in range(120):
        detail = get_json(f"/content/{job_id}")
        status = detail.get("status", "unknown")
        n_versions = len(detail.get("versions") or [])
        status_box.info(f"Status: **{status}** · versions: {n_versions}")
        progress.progress(min(1.0, (i + 1) / 120))
        if status in TERMINAL:
            break
        time.sleep(2)
    progress.progress(1.0)
    return detail


def page_generate() -> None:
    st.subheader("Generate content")
    content_label = st.selectbox("Content type", list(CONTENT_TYPES.keys()))
    brief = st.text_area(
        "Brief",
        height=140,
        placeholder="e.g. Write a LinkedIn post about writing better tests…",
    )
    if st.button("Generate", type="primary", disabled=not brief.strip()):
        try:
            created = post_json(
                "/content/generate",
                {
                    "brief": brief.strip(),
                    "content_type": CONTENT_TYPES[content_label],
                },
            )
        except httpx.HTTPError as exc:
            st.error(f"Failed to enqueue job: {exc}")
            return

        job_id = created["job_id"]
        st.session_state["job_id"] = job_id
        st.success(f"Queued job `{job_id}`")

        status_box = st.empty()
        progress = st.progress(0.0)
        with st.spinner("Running Plan → Draft → Critique → Revise…"):
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
    st.markdown(f"**Job** `{detail.get('job_id')}` · **{status}**")

    if status == "failed":
        st.error(detail.get("error_message") or "Job failed")
        return

    if detail.get("final_content"):
        st.markdown("#### Final content")
        st.text_area(
            "final",
            value=detail["final_content"],
            height=220,
            label_visibility="collapsed",
        )

    versions = detail.get("versions") or []
    if versions:
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

        st.markdown("#### Feedback")
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
        ["prompt_style", "content_type", "alpha", "beta", "mean", "arm_id"]
    ].sort_values(["content_type", "mean"], ascending=[True, False])
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("#### Mean reward by style × content type")
    pivot = show.pivot_table(
        index="prompt_style", columns="content_type", values="mean"
    )
    st.bar_chart(pivot)


def main() -> None:
    st.set_page_config(
        page_title="Content Pipeline",
        page_icon="📝",
        layout="wide",
    )
    st.title("Agentic Content Pipeline")
    st.caption("Plan → Draft → Critique → Revise, with Thompson Sampling bandit")

    with st.sidebar:
        st.header("Settings")
        st.text_input("API base URL", value=DEFAULT_API, key="api_base")
        try:
            health = get_json("/health")
            st.success(f"API {health.get('status', 'ok')}")
        except Exception:
            st.error("API unreachable")

        page = st.radio("Page", ["Generate", "Bandit stats"], label_visibility="collapsed")

    if page == "Generate":
        page_generate()
    else:
        page_bandit()


if __name__ == "__main__":
    main()

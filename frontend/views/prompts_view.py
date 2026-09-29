"""Prompt Templates & Versioning View."""

from __future__ import annotations

import streamlit as st

from frontend.api.prompts import (
    create_prompt_template,
    deactivate_prompt_template,
    list_prompt_templates,
    patch_prompt_template,
)


def render_prompts_view() -> None:
    """Renders the prompt templates and versioning management view."""
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

        try:
            templates = list_prompt_templates(stage=stage_filter, active_only=active_only)
        except Exception as exc:
            st.error(f"Could not load templates: {exc}")
            templates = []

        if not templates:
            st.info("No prompt templates found. Create one in the 'Create New Template' tab.")
        else:
            st.write(f"Found **{len(templates)}** template version(s).")
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
                                    new_v = patch_prompt_template(v["id"], patch_body)
                                    st.success(
                                        f"Created new immutable version `{new_v['version_tag']}` (ID: `{new_v['id']}`)!"
                                    )
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to update template: {exc}")

                        if v["is_active"]:
                            if st.button("Deactivate this version", key=f"del_{v['id']}"):
                                try:
                                    deactivate_prompt_template(v["id"])
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
                        created = create_prompt_template(create_body)
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

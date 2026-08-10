"""Prompt templates keyed by prompt_style + platform preset."""

from app.platforms import get_preset, preset_rules_block

STYLE_INSTRUCTIONS = {
    "concise": (
        "Write in a concise, direct style. Prefer short sentences. "
        "Cut fluff. Lead with the point."
    ),
    "storytelling": (
        "Write in a storytelling style. Open with a hook or anecdote, "
        "build narrative tension, and land on a clear takeaway."
    ),
    "data_driven": (
        "Write in a data-driven style. Cite concrete numbers, comparisons, "
        "and evidence. Structure claims around facts and implications."
    ),
}


def plan_prompt(brief: str, platform: str, prompt_style: str) -> str:
    style = STYLE_INSTRUCTIONS.get(prompt_style, STYLE_INSTRUCTIONS["concise"])
    preset = get_preset(platform)
    rules = preset_rules_block(preset)
    structure_hint = (
        "Plan a multi-post thread (numbered beats)."
        if preset.structure == "thread"
        else "Plan a single piece."
    )
    return f"""You are a content strategist. Create a short outline/plan for the following brief.

{rules}

Style: {style}
Structure hint: {structure_hint}

Brief:
{brief}

Return a numbered outline only (5–8 bullets). No draft yet."""


def draft_prompt(brief: str, platform: str, prompt_style: str, plan: str) -> str:
    style = STYLE_INSTRUCTIONS.get(prompt_style, STYLE_INSTRUCTIONS["concise"])
    preset = get_preset(platform)
    rules = preset_rules_block(preset)
    format_hint = (
        "Use Markdown formatting."
        if preset.formatting == "markdown"
        else "Use plain text only (no markdown headings)."
    )
    thread_hint = ""
    if preset.structure == "thread":
        thread_hint = (
            "Format as a numbered thread (1/, 2/, …). "
            "Respect the per-post character limit strictly."
        )
    return f"""You are a professional content writer. Write the full piece based on the plan.

{rules}

Style: {style}
{format_hint}
{thread_hint}

Brief:
{brief}

Plan:
{plan}

Return only the finished content — no meta commentary."""


def critique_prompt(brief: str, platform: str, draft: str) -> str:
    preset = get_preset(platform)
    rules = preset_rules_block(preset)
    return f"""You are a strict content editor. Score the draft against the brief and platform rules.

Brief:
{brief}

{rules}

Draft:
{draft}

Respond with ONLY valid JSON (no markdown fences):
{{
  "coherence": <0-10 integer>,
  "on_topic": <0-10 integer>,
  "notes": "<specific actionable feedback in 2-4 sentences, including platform/length/CTA issues>"
}}"""


def revise_prompt(brief: str, draft: str, notes: str, platform: str | None = None) -> str:
    extra = ""
    if platform:
        preset = get_preset(platform)
        extra = f"\n\nPlatform rules to respect:\n{preset_rules_block(preset)}\n"
    return f"""You are a professional content writer revising a draft.
{extra}
Brief:
{brief}

Current draft:
{draft}

Editor feedback:
{notes}

Return only the revised full content — no meta commentary."""

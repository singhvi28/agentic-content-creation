"""Prompt templates keyed by prompt_style arm."""

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

CONTENT_TYPE_GUIDANCE = {
    "blog_post": "Produce a structured blog post with a clear title, intro, body sections, and conclusion.",
    "social_post": "Produce a short social media post (under ~280 words unless the brief says otherwise). Punchy and shareable.",
    "email": "Produce a professional email with subject line, greeting, body, and sign-off.",
}


def plan_prompt(brief: str, content_type: str, prompt_style: str) -> str:
    style = STYLE_INSTRUCTIONS.get(prompt_style, STYLE_INSTRUCTIONS["concise"])
    guidance = CONTENT_TYPE_GUIDANCE.get(content_type, "")
    return f"""You are a content strategist. Create a short outline/plan for the following brief.

Content type: {content_type}
Style: {style}
Guidance: {guidance}

Brief:
{brief}

Return a numbered outline only (5–8 bullets). No draft yet."""


def draft_prompt(brief: str, content_type: str, prompt_style: str, plan: str) -> str:
    style = STYLE_INSTRUCTIONS.get(prompt_style, STYLE_INSTRUCTIONS["concise"])
    guidance = CONTENT_TYPE_GUIDANCE.get(content_type, "")
    return f"""You are a professional content writer. Write the full piece based on the plan.

Content type: {content_type}
Style: {style}
Guidance: {guidance}

Brief:
{brief}

Plan:
{plan}

Return only the finished content — no meta commentary."""


def critique_prompt(brief: str, content_type: str, draft: str) -> str:
    return f"""You are a strict content editor. Score the draft against the brief.

Brief:
{brief}

Content type: {content_type}

Draft:
{draft}

Respond with ONLY valid JSON (no markdown fences):
{{
  "coherence": <0-10 integer>,
  "on_topic": <0-10 integer>,
  "notes": "<specific actionable feedback in 2-4 sentences>"
}}"""


def revise_prompt(brief: str, draft: str, notes: str) -> str:
    return f"""You are a professional content writer revising a draft.

Brief:
{brief}

Current draft:
{draft}

Editor feedback:
{notes}

Return only the revised full content — no meta commentary."""
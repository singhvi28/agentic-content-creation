"""Automated critic: LLM rubric + local readability / repetition checks."""

from __future__ import annotations

import re
from dataclasses import dataclass

import textstat

from app.llm.gemini import LLMClient
from app.orchestrator.prompts import critique_prompt


@dataclass
class CritiqueResult:
    critic_score: float
    critic_notes: str
    coherence: float
    on_topic: float
    readability: float
    repetition_penalty: float


def flesch_to_0_10(flesch: float) -> float:
    """Map Flesch Reading Ease (~0–100) to 0–10. Prefer ~60–70."""
    # Clamp and scale: 0→0, 100→10, with soft peak around 60–70
    clamped = max(0.0, min(100.0, flesch))
    return round(clamped / 10.0, 2)


def ngram_overlap_ratio(text: str, n: int = 3) -> float:
    """Fraction of repeated n-grams (higher = more repetitive)."""
    tokens = re.findall(r"[a-z0-9']+", text.lower())
    if len(tokens) < n + 1:
        return 0.0
    grams = [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
    if not grams:
        return 0.0
    unique = len(set(grams))
    return 1.0 - (unique / len(grams))


def repetition_score_0_10(text: str) -> float:
    """10 = no repetition; 0 = highly repetitive."""
    overlap = ngram_overlap_ratio(text, n=3)
    # overlap 0 → 10, overlap 0.5+ → ~0
    return round(max(0.0, 10.0 * (1.0 - min(1.0, overlap * 2))), 2)


def combine_scores(
    coherence: float,
    on_topic: float,
    readability: float,
    repetition: float,
) -> float:
    """Weighted blend into a single critic_score on 0–10."""
    score = (
        0.30 * coherence
        + 0.35 * on_topic
        + 0.20 * readability
        + 0.15 * repetition
    )
    return round(max(0.0, min(10.0, score)), 2)


async def critique_draft(
    llm: LLMClient,
    brief: str,
    content_type: str,
    draft: str,
) -> CritiqueResult:
    llm_result = await llm.generate_json(
        critique_prompt(brief, content_type, draft)
    )
    coherence = float(llm_result.get("coherence", 5))
    on_topic = float(llm_result.get("on_topic", 5))
    notes = str(llm_result.get("notes", ""))

    try:
        flesch = float(textstat.flesch_reading_ease(draft))
    except Exception:
        flesch = 50.0
    readability = flesch_to_0_10(flesch)
    repetition = repetition_score_0_10(draft)

    score = combine_scores(coherence, on_topic, readability, repetition)
    local_notes = (
        f"Readability(Flesch→0-10)={readability}; "
        f"Repetition={repetition}."
    )
    full_notes = f"{notes} [{local_notes}]".strip()

    return CritiqueResult(
        critic_score=score,
        critic_notes=full_notes,
        coherence=coherence,
        on_topic=on_topic,
        readability=readability,
        repetition_penalty=repetition,
    )
"""Automated critic: LLM rubric + local readability / repetition / length checks."""

from __future__ import annotations

import re
from dataclasses import dataclass

import textstat

from app.llm.gemini import LLMClient
from app.orchestrator.prompts import critique_prompt
from app.platforms import PlatformPreset, get_preset


@dataclass
class CritiqueResult:
    critic_score: float
    critic_notes: str
    coherence: float
    on_topic: float
    readability: float
    repetition_penalty: float
    length_score: float


def flesch_to_0_10(flesch: float) -> float:
    """
    Map Flesch Reading Ease to 0–10 with a target band.

    Scores in roughly 50–70 (plain adult prose) get 10; taper outside so
    maximally simplistic (~100) and dense (~0) writing are not rewarded.
    """
    clamped = max(0.0, min(100.0, flesch))
    low, high = 50.0, 70.0
    if low <= clamped <= high:
        return 10.0
    if clamped < low:
        # 0 → 0, 50 → 10
        return round(10.0 * (clamped / low), 2)
    # 70 → 10, 100 → 0
    return round(10.0 * (1.0 - (clamped - high) / (100.0 - high)), 2)


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
    return round(max(0.0, 10.0 * (1.0 - min(1.0, overlap * 2))), 2)


def split_thread_segments(text: str) -> list[str]:
    """Split thread-style drafts into posts/tweets."""
    # Prefer numbered segments: 1/ ... 2/ ... or Tweet 1: ...
    numbered = re.split(
        r"(?m)^\s*(?:\d+\s*/|\d+\.\s+|Tweet\s+\d+\s*:|Post\s+\d+\s*:)\s*",
        text.strip(),
    )
    parts = [p.strip() for p in numbered if p and p.strip()]
    if len(parts) >= 2:
        return parts
    # Fallback: blank-line separated
    blanks = [p.strip() for p in re.split(r"\n\s*\n+", text.strip()) if p.strip()]
    return blanks if blanks else [text.strip()]


def length_score_0_10(text: str, preset: PlatformPreset) -> float:
    """
    10 = within caps; lower when over max_chars / max_words.
    For threads, score the worst segment against max_chars.
    """
    scores: list[float] = []

    if preset.max_chars is not None:
        segments = (
            split_thread_segments(text)
            if preset.structure == "thread"
            else [text]
        )
        for seg in segments:
            n = len(seg)
            if n <= preset.max_chars:
                scores.append(10.0)
            else:
                over = (n - preset.max_chars) / preset.max_chars
                scores.append(round(max(0.0, 10.0 * (1.0 - min(1.5, over))), 2))

    if preset.max_words is not None:
        words = len(re.findall(r"\b\w+\b", text))
        if words <= preset.max_words:
            scores.append(10.0)
        else:
            over = (words - preset.max_words) / preset.max_words
            scores.append(round(max(0.0, 10.0 * (1.0 - min(1.5, over))), 2))

    if not scores:
        return 10.0
    return round(min(scores), 2)


def combine_scores(
    coherence: float,
    on_topic: float,
    readability: float,
    repetition: float,
    length: float = 10.0,
) -> float:
    """Weighted blend into a single critic_score on 0–10."""
    score = (
        0.25 * coherence
        + 0.30 * on_topic
        + 0.15 * readability
        + 0.10 * repetition
        + 0.20 * length
    )
    return round(max(0.0, min(10.0, score)), 2)


async def critique_draft(
    llm: LLMClient,
    brief: str,
    platform: str,
    draft: str,
) -> CritiqueResult:
    preset = get_preset(platform)
    llm_result = await llm.generate_json(critique_prompt(brief, platform, draft))
    coherence = float(llm_result.get("coherence", 5))
    on_topic = float(llm_result.get("on_topic", 5))
    notes = str(llm_result.get("notes", ""))

    try:
        flesch = float(textstat.flesch_reading_ease(draft))
    except Exception:
        flesch = 50.0
    readability = flesch_to_0_10(flesch)
    repetition = repetition_score_0_10(draft)
    length = length_score_0_10(draft, preset)

    score = combine_scores(coherence, on_topic, readability, repetition, length)
    local_notes = (
        f"Readability={readability}; Repetition={repetition}; "
        f"Length={length} ({preset.id})."
    )
    full_notes = f"{notes} [{local_notes}]".strip()

    return CritiqueResult(
        critic_score=score,
        critic_notes=full_notes,
        coherence=coherence,
        on_topic=on_topic,
        readability=readability,
        repetition_penalty=repetition,
        length_score=length,
    )

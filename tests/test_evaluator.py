from app.orchestrator.evaluator import (
    combine_scores,
    flesch_to_0_10,
    ngram_overlap_ratio,
    repetition_score_0_10,
)


def test_combine_scores_bounds():
    assert combine_scores(10, 10, 10, 10) == 10.0
    assert combine_scores(0, 0, 0, 0) == 0.0


def test_flesch_mapping():
    assert flesch_to_0_10(100) == 10.0
    assert flesch_to_0_10(0) == 0.0
    assert flesch_to_0_10(50) == 5.0


def test_ngram_overlap_detects_repetition():
    clean = "The quick brown fox jumps over the lazy dog near the river bank today."
    repetitive = "buy now buy now buy now buy now buy now buy now buy now buy now"
    assert ngram_overlap_ratio(repetitive) > ngram_overlap_ratio(clean)
    assert repetition_score_0_10(clean) > repetition_score_0_10(repetitive)
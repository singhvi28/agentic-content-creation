from app.orchestrator.evaluator import (
    combine_scores,
    flesch_to_0_10,
    length_score_0_10,
    ngram_overlap_ratio,
    repetition_score_0_10,
)
from app.platforms import PLATFORM_IDS, get_preset


def test_combine_scores_bounds():
    assert combine_scores(10, 10, 10, 10, 10) == 10.0
    assert combine_scores(0, 0, 0, 0, 0) == 0.0


def test_flesch_mapping():
    assert flesch_to_0_10(100) == 10.0
    assert flesch_to_0_10(0) == 0.0
    assert flesch_to_0_10(50) == 5.0


def test_ngram_overlap_detects_repetition():
    clean = "The quick brown fox jumps over the lazy dog near the river bank today."
    repetitive = "buy now buy now buy now buy now buy now buy now buy now buy now"
    assert ngram_overlap_ratio(repetitive) > ngram_overlap_ratio(clean)
    assert repetition_score_0_10(clean) > repetition_score_0_10(repetitive)


def test_length_score_twitter_within_cap():
    preset = get_preset("twitter")
    text = "1/ Short hook.\n\n2/ Another short tweet."
    assert length_score_0_10(text, preset) == 10.0


def test_length_score_twitter_over_cap():
    preset = get_preset("twitter")
    long_tweet = "x" * 400
    text = f"1/ {long_tweet}\n\n2/ ok"
    score = length_score_0_10(text, preset)
    assert score < 8.0


def test_all_platform_presets_exist():
    assert len(PLATFORM_IDS) == 7
    for pid in PLATFORM_IDS:
        p = get_preset(pid)
        assert p.id == pid
        assert p.structure in {"single", "thread"}
        assert p.formatting in {"markdown", "plain"}

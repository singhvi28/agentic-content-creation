import pytest
from numpy.random import default_rng

from app.bandit.thompson import (
    PROMPT_STYLES,
    Arm,
    ArmParams,
    ThompsonSamplingBandit,
    expected_value,
)


def test_arm_id_roundtrip():
    arm = Arm("concise", "linkedin")
    assert arm.arm_id == "concise|linkedin"
    assert Arm.from_arm_id(arm.arm_id) == arm


def test_select_arm_is_deterministic_with_seed():
    params = [
        ArmParams(f"{s}|linkedin", alpha=1.0, beta=1.0) for s in PROMPT_STYLES
    ]
    b1 = ThompsonSamplingBandit(rng=default_rng(42))
    b2 = ThompsonSamplingBandit(rng=default_rng(42))
    assert b1.select_arm("linkedin", params) == b2.select_arm("linkedin", params)


def test_select_arm_prefers_high_alpha():
    """With enough samples, high-alpha arm should usually win."""
    params = [
        ArmParams("concise|twitter", alpha=50.0, beta=1.0),
        ArmParams("storytelling|twitter", alpha=1.0, beta=50.0),
        ArmParams("data_driven|twitter", alpha=1.0, beta=50.0),
    ]
    bandit = ThompsonSamplingBandit(rng=default_rng(0))
    wins = {"concise": 0, "storytelling": 0, "data_driven": 0}
    for _ in range(100):
        arm = bandit.select_arm("twitter", params)
        wins[arm.prompt_style] += 1
    assert wins["concise"] > 80


def test_update_from_rating():
    assert ThompsonSamplingBandit.update_from_rating(1.0, 1.0, 5) == (2.0, 1.0)
    assert ThompsonSamplingBandit.update_from_rating(1.0, 1.0, 1) == (1.0, 2.0)
    assert ThompsonSamplingBandit.update_from_rating(1.0, 1.0, 3) == (1.0, 1.0)


def test_update_from_critic():
    a, b = ThompsonSamplingBandit.update_from_critic(
        1.0, 1.0, critic_score=9.0, weight=0.3, threshold=7.0
    )
    assert a == pytest.approx(1.3)
    assert b == pytest.approx(1.0)

    a, b = ThompsonSamplingBandit.update_from_critic(
        1.0, 1.0, critic_score=0.0, weight=0.3, threshold=7.0
    )
    assert a == pytest.approx(1.0)
    assert b == pytest.approx(1.3)


def test_apply_decay():
    a, b = ThompsonSamplingBandit.apply_decay(5.0, 3.0, decay=0.5)
    assert a == pytest.approx(3.0)
    assert b == pytest.approx(2.0)
    # Prior Beta(1,1) is a fixed point
    assert ThompsonSamplingBandit.apply_decay(1.0, 1.0, 0.995) == (1.0, 1.0)


def test_select_arms_without_replacement_distinct():
    params = [
        ArmParams(f"{s}|linkedin", alpha=1.0, beta=1.0) for s in PROMPT_STYLES
    ]
    bandit = ThompsonSamplingBandit(rng=default_rng(7))
    for k in (2, 3):
        arms = bandit.select_arms_without_replacement("linkedin", params, k)
        assert len(arms) == k
        styles = {a.prompt_style for a in arms}
        assert len(styles) == k
        assert all(a.platform == "linkedin" for a in arms)


def test_expected_value():
    assert expected_value(3.0, 1.0) == 0.75


def test_action_payload():
    action = Arm("storytelling", "newsletter").to_action()
    assert action["prompt_style"] == "storytelling"
    assert action["platform"] == "newsletter"
    assert action["max_revision_rounds"] == 2
    assert "temperature" in action

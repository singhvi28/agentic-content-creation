"""Thompson Sampling contextual bandit over prompt_style × content_type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.random import Generator, default_rng

PROMPT_STYLES = ("concise", "storytelling", "data_driven")

# Fixed pipeline knobs carried in the action payload (expandable later)
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_REVISION_ROUNDS = 2


@dataclass(frozen=True)
class Arm:
    prompt_style: str
    content_type: str

    @property
    def arm_id(self) -> str:
        return f"{self.prompt_style}|{self.content_type}"

    @classmethod
    def from_arm_id(cls, arm_id: str) -> Arm:
        style, ctype = arm_id.split("|", 1)
        return cls(prompt_style=style, content_type=ctype)

    def to_action(self) -> dict:
        return {
            "arm_id": self.arm_id,
            "prompt_style": self.prompt_style,
            "content_type": self.content_type,
            "temperature": DEFAULT_TEMPERATURE,
            "max_revision_rounds": DEFAULT_MAX_REVISION_ROUNDS,
        }


@dataclass
class ArmParams:
    arm_id: str
    alpha: float
    beta: float


class ThompsonSamplingBandit:
    """Contextual Thompson Sampling: separate Beta posteriors per (arm, context)."""

    def __init__(self, rng: Generator | None = None) -> None:
        self.rng = rng if rng is not None else default_rng()

    def all_arms_for_context(self, content_type: str) -> list[Arm]:
        return [Arm(style, content_type) for style in PROMPT_STYLES]

    def select_arm(
        self,
        content_type: str,
        params: Sequence[ArmParams],
    ) -> Arm:
        """Sample θ ~ Beta(α, β) per arm; pick argmax."""
        by_id = {p.arm_id: p for p in params}
        best_arm: Arm | None = None
        best_theta = -1.0

        for arm in self.all_arms_for_context(content_type):
            p = by_id.get(arm.arm_id)
            alpha = p.alpha if p else 1.0
            beta = p.beta if p else 1.0
            theta = float(self.rng.beta(alpha, beta))
            if theta > best_theta:
                best_theta = theta
                best_arm = arm

        assert best_arm is not None
        return best_arm

    @staticmethod
    def update_from_rating(alpha: float, beta: float, rating: int) -> tuple[float, float]:
        """Human feedback: ≥4 success, ≤2 failure, 3 neutral."""
        if rating >= 4:
            return alpha + 1.0, beta
        if rating <= 2:
            return alpha, beta + 1.0
        return alpha, beta

    @staticmethod
    def update_from_critic(
        alpha: float,
        beta: float,
        critic_score: float,
        weight: float = 0.3,
        threshold: float = 7.0,
    ) -> tuple[float, float]:
        """
        Soft secondary reward from automated critic before human feedback.
        Score above threshold → fractional success; below → fractional failure.
        """
        if critic_score >= threshold:
            return alpha + weight, beta
        # Map shortfall into [0, weight]
        shortfall = min(1.0, (threshold - critic_score) / threshold)
        return alpha, beta + weight * shortfall


def expected_value(alpha: float, beta: float) -> float:
    return alpha / (alpha + beta)
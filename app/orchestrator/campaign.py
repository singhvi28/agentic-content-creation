"""Campaign orchestrator: one brief → multi-platform pack."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bandit.thompson import ThompsonSamplingBandit
from app.config import get_settings
from app.db.models import ContentVersion, Job, JobStatus, Platform
from app.llm.gemini import LLMClient
from app.orchestrator.helpers import (
    StatusCallback,
    critique_and_maybe_revise,
    ensure_arm_row,
    load_bandit_params,
    set_status,
    soft_update_bandit,
)
from app.orchestrator.prompts import (
    campaign_plan_prompt,
    cross_surface_critique_prompt,
    draft_from_shared_plan_prompt,
)
from app.platforms import get_preset

logger = logging.getLogger(__name__)


def _pack_markdown(assets: dict[str, str], shared_plan: str) -> str:
    parts = ["# Campaign pack", "", "## Shared plan", shared_plan, ""]
    for platform, text in assets.items():
        label = get_preset(platform).label
        parts.extend([f"## {label}", text, ""])
    return "\n".join(parts).strip()


async def run_campaign_pipeline(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    bandit: ThompsonSamplingBandit,
    on_status: StatusCallback,
) -> None:
    settings = get_settings()
    platforms = list(job.platforms or [])
    if not platforms:
        raise ValueError("Campaign job has no platforms")

    await set_status(session, job, JobStatus.planning, on_status, {"platforms": platforms})
    shared_plan = await llm.generate(
        campaign_plan_prompt(job.brief, platforms),
        temperature=0.5,
    )
    job.shared_plan = shared_plan
    await session.commit()
    await on_status(
        job.id,
        JobStatus.planning,
        {"shared_plan": shared_plan},
    )

    final_assets: dict[str, ContentVersion] = {}
    used_arm_ids: list[str] = []

    for platform in platforms:
        params = await load_bandit_params(session, platform)
        arm = bandit.select_arm(platform, params)
        action = arm.to_action()
        await ensure_arm_row(session, arm.arm_id)
        used_arm_ids.append(arm.arm_id)

        await set_status(
            session,
            job,
            JobStatus.drafting,
            on_status,
            {"platform": platform, "arm": action},
        )
        draft = await llm.generate(
            draft_from_shared_plan_prompt(
                job.brief, platform, arm.prompt_style, shared_plan
            ),
            temperature=float(action["temperature"]),
        )
        version = ContentVersion(
            job_id=job.id,
            platform=Platform(platform),
            round=0,
            text=draft,
            bandit_action=action,
        )
        session.add(version)
        await session.commit()
        await session.refresh(version)
        await on_status(
            job.id,
            JobStatus.drafting,
            {
                "platform": platform,
                "version_id": str(version.id),
                "round": 0,
                "text": draft,
            },
        )

        max_rounds = int(
            action.get("max_revision_rounds", settings.max_revision_rounds)
        )
        final_version = await critique_and_maybe_revise(
            session,
            job,
            llm,
            arm,
            action,
            draft,
            version,
            max_rounds,
            on_status,
            platform=platform,
        )
        final_assets[platform] = final_version

    await set_status(session, job, JobStatus.critiquing, on_status, {"phase": "cross_surface"})
    asset_texts = {p: v.text for p, v in final_assets.items()}
    cross = await llm.generate_json(
        cross_surface_critique_prompt(job.brief, asset_texts)
    )
    consistency = float(cross.get("consistency", 5))
    hook = float(cross.get("hook_alignment", 5))
    cta = float(cross.get("cta_alignment", 5))
    notes = str(cross.get("notes", ""))
    score = round((consistency + hook + cta) / 3.0, 2)
    job.cross_surface_score = score
    job.cross_surface_notes = (
        f"{notes} [consistency={consistency}, hook={hook}, cta={cta}]"
    )

    cross_weight = settings.critic_reward_weight * 0.5
    for arm_id in used_arm_ids:
        await soft_update_bandit(
            session,
            arm_id,
            score,
            weight=cross_weight,
        )
    await session.commit()
    await on_status(
        job.id,
        JobStatus.critiquing,
        {
            "phase": "cross_surface",
            "cross_surface_score": score,
            "cross_surface_notes": job.cross_surface_notes,
        },
    )

    pack_md = _pack_markdown(asset_texts, shared_plan)
    job.final_content_id = None
    await set_status(
        session,
        job,
        JobStatus.done,
        on_status,
        {
            "final_content": pack_md,
            "assets": list(final_assets.keys()),
            "cross_surface_score": score,
        },
    )

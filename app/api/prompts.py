"""API routes for PromptTemplate CRUD and versioning."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromptTemplate, PromptTemplateStage
from app.db.session import get_db
from app.schemas import (
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplateUpdate,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/", response_model=PromptTemplateOut, status_code=201)
async def create_prompt_template(
    body: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateOut:
    template = PromptTemplate(
        name=body.name,
        stage=body.stage,
        template=body.template,
        version_tag=body.version_tag,
        description=body.description,
        is_active=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return PromptTemplateOut.model_validate(template)


@router.get("/", response_model=list[PromptTemplateOut])
async def list_prompt_templates(
    stage: PromptTemplateStage | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> list[PromptTemplateOut]:
    stmt = select(PromptTemplate)
    if stage:
        stmt = stmt.where(PromptTemplate.stage == stage)
    if active_only:
        stmt = stmt.where(PromptTemplate.is_active.is_(True))
    stmt = stmt.order_by(PromptTemplate.name, PromptTemplate.created_at.desc())
    result = await db.execute(stmt)
    templates = result.scalars().all()
    return [PromptTemplateOut.model_validate(t) for t in templates]


@router.get("/{template_id}", response_model=PromptTemplateOut)
async def get_prompt_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateOut:
    template = await db.get(PromptTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return PromptTemplateOut.model_validate(template)


@router.patch("/{template_id}", response_model=PromptTemplateOut)
async def update_prompt_template(
    template_id: uuid.UUID,
    body: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateOut:
    """
    Immutable version update: Creates a new PromptTemplate row with incremented/new
    version_tag while preserving the existing version for historical reproducibility.
    """
    original = await db.get(PromptTemplate, template_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    new_template_text = (
        body.template if body.template is not None else original.template
    )
    new_description = (
        body.description if body.description is not None else original.description
    )

    if body.version_tag:
        new_version_tag = body.version_tag
    else:
        if original.version_tag.startswith("v") and original.version_tag[1:].isdigit():
            v_num = int(original.version_tag[1:]) + 1
            new_version_tag = f"v{v_num}"
        else:
            new_version_tag = f"{original.version_tag}-revised"

    new_version = PromptTemplate(
        name=original.name,
        stage=original.stage,
        template=new_template_text,
        version_tag=new_version_tag,
        description=new_description,
        is_active=True,
    )
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    return PromptTemplateOut.model_validate(new_version)


@router.delete("/{template_id}", status_code=204)
async def delete_prompt_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete: sets is_active=False to preserve audit trail."""
    template = await db.get(PromptTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    template.is_active = False
    await db.commit()

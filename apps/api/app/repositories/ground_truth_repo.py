"""EVALUATION-ONLY — DetectionEngine importing this module is an architecture
violation (checked in Phase 07 review, and by tests in Phase 04+).

This repository exists ONLY for the two writers/readers that are allowed to know
the truth: the ingestion service (loads the CSV) and the evaluation service
(Phase 07, computes P/R/F1). No detection rule, scorer, merger, or alert router
may import from here.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ground_truth import GroundTruth


async def all_truth(session: AsyncSession) -> list[GroundTruth]:
    return list((await session.execute(select(GroundTruth).order_by(GroundTruth.gt_id))).scalars().all())


async def count_truth(session: AsyncSession) -> int:
    from sqlalchemy import func

    return int((await session.execute(select(func.count(GroundTruth.gt_id)))).scalar_one())

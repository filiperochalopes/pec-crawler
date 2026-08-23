from typing import Dict, Any, Optional

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PecVersion
from parsing import is_full_version

logger = logging.getLogger(__name__)


async def save_version(session: AsyncSession, data: Dict[str, Any]) -> PecVersion:
    logger.debug("Saving version with data: %s", data)
    version = data.get("versao_label")
    if not is_full_version(version):
        raise ValueError(
            f"A versão persistida deve ter o formato major.minor.patch: {version!r}"
        )

    row = PecVersion(
        version=version,
        download_link=data["link_linux"],
        release_notes_page=data.get("url_release_page"),
        release_notes_summary=data.get("release_notes_summary"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.debug("Saved PecVersion row: %s", row)
    return row


async def get_last_version(session: AsyncSession) -> Optional[PecVersion]:
    logger.debug("Fetching last persisted version")
    stmt = select(PecVersion).order_by(PecVersion.id.desc()).limit(1)
    res = await session.execute(stmt)
    row = res.scalar_one_or_none()
    logger.debug("Last version: %s", row)
    return row


async def get_version(session: AsyncSession, version: str) -> Optional[PecVersion]:
    logger.debug("Fetching version %s", version)
    if not is_full_version(version):
        logger.warning("Ignoring incomplete version lookup: %s", version)
        return None

    stmt = select(PecVersion).where(PecVersion.version == version).limit(1)
    res = await session.execute(stmt)
    row = res.scalar_one_or_none()
    logger.debug("Fetched row: %s", row)
    return row


async def list_versions(session: AsyncSession, limit: int = 20):
    logger.debug("Listing last %d versions", limit)
    stmt = select(PecVersion).order_by(PecVersion.id.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())

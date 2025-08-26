from typing import Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PecVersion


async def save_version(session: AsyncSession, data: Dict[str, Any]) -> PecVersion:
    row = PecVersion(
        version=data["versao_label"],
        download_link=data["link_linux"],
        release_notes_page=data.get("url_release_page"),
        release_notes_summary=data.get("release_notes_summary"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_last_version(session: AsyncSession) -> Optional[PecVersion]:
    stmt = select(PecVersion).order_by(PecVersion.id.desc()).limit(1)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_version(session: AsyncSession, version: str) -> Optional[PecVersion]:
    stmt = select(PecVersion).where(PecVersion.version == version).limit(1)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_versions(session: AsyncSession, limit: int = 20):
    stmt = select(PecVersion).order_by(PecVersion.id.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


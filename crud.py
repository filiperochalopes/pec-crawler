from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import CrawlerRun

async def save_run(session: AsyncSession, status: str, data: Dict[str, Any]) -> CrawlerRun:
    row = CrawlerRun(
        status=status,
        versao_label=data.get("versao_label"),
        url_release_page=data.get("url_release_page"),
        link_linux=data.get("link_linux"),
        source=data.get("source"),
        payload=data,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row

async def get_last_run(session: AsyncSession) -> Optional[CrawlerRun]:
    stmt = select(CrawlerRun).order_by(CrawlerRun.id.desc()).limit(1)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def list_runs(session: AsyncSession, limit: int = 20):
    stmt = select(CrawlerRun).order_by(CrawlerRun.id.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())
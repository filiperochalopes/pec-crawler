from fastapi import FastAPI, Depends, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from env import settings
from helpers import run_pec_crawler, now_iso, parse_time_hhmm
from database import init_db, get_session
from sqlalchemy.ext.asyncio import AsyncSession
from crud import save_version, get_last_version, list_versions

app = FastAPI(title=settings.APP_NAME, version="1.0.0")
scheduler = AsyncIOScheduler()
LAST_RESULT = {"status": "idle", "message": "Aguardando primeira execução", "ts": now_iso()}

async def daily_job():
    status, data = await run_pec_crawler()
    payload = {"status": status, "data": data, "execution_time": now_iso()}
    global LAST_RESULT
    LAST_RESULT = payload
    # Persistir
    async for session in get_session():
        if status == "success":
            await save_version(session, data)

@app.get("/healthz")
async def healthz():
    """Verifica se a API está ativa."""
    return {"ok": True, "ts": now_iso()}

@app.post("/run")
async def run_now(session: AsyncSession = Depends(get_session)):
    """Executa o crawler imediatamente."""
    status, data = await run_pec_crawler()
    row_id = None
    if status == "success":
        row = await save_version(session, data)
        row_id = row.id
    return {"status": status, "data": data, "id": row_id, "execution_time": now_iso()}

@app.get("/last")
async def last(session: AsyncSession = Depends(get_session)):
    """Última versão persistida."""
    row = await get_last_version(session)
    if not row:
        return LAST_RESULT
    return {
        "id": row.id,
        "version": row.version,
        "download_link": row.download_link,
        "release_notes_page": row.release_notes_page,
        "release_notes_summary": row.release_notes_summary,
        "created_at": row.created_at,
    }

@app.get("/runs")
async def runs(limit: int = Query(20, ge=1, le=200), session: AsyncSession = Depends(get_session)):
    """Lista versões recentes."""
    rows = await list_versions(session, limit=limit)
    return [
        {
            "id": r.id,
            "version": r.version,
            "created_at": r.created_at,
        }
        for r in rows
    ]

@app.on_event("startup")
async def _startup():
    await init_db()
    h, m = parse_time_hhmm(settings.RUN_AT)
    trigger = CronTrigger(hour=h, minute=m, timezone=ZoneInfo(settings.TZ))
    scheduler.add_job(daily_job, trigger, id="pec_daily", replace_existing=True)
    scheduler.start()

@app.on_event("shutdown")
async def _shutdown():
    scheduler.shutdown(wait=False)
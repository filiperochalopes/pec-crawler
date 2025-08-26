from fastapi import FastAPI, Depends, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from env import settings
from helpers import run_pec_crawler, now_iso, parse_time_hhmm
from database import init_db, get_session
from sqlalchemy.ext.asyncio import AsyncSession
from crud import save_run, get_last_run, list_runs

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
        await save_run(session, status, data)

@app.get("/healthz")
async def healthz():
    return {"ok": True, "ts": now_iso()}

@app.post("/run")
async def run_now(session: AsyncSession = Depends(get_session)):
    status, data = await run_pec_crawler()
    row = await save_run(session, status, data)
    return {"status": status, "data": data, "id": row.id, "execution_time": now_iso()}

@app.get("/last")
async def last(session: AsyncSession = Depends(get_session)):
    row = await get_last_run(session)
    if not row:
        return LAST_RESULT
    return {
        "id": row.id,
        "status": row.status,
        "versao_label": row.versao_label,
        "url_release_page": row.url_release_page,
        "link_linux": row.link_linux,
        "source": row.source,
        "created_at": row.created_at,
        "payload": row.payload,
    }

@app.get("/runs")
async def runs(limit: int = Query(20, ge=1, le=200), session: AsyncSession = Depends(get_session)):
    rows = await list_runs(session, limit=limit)
    return [
        {
            "id": r.id,
            "status": r.status,
            "versao_label": r.versao_label,
            "created_at": r.created_at,
        } for r in rows
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
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .checks import check_all
from .config import load_config
from .storage import Store

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("monitor")


async def collect(config, store):
    try:
        while True:
            results = await check_all(config.services)
            await asyncio.to_thread(store.save_round, results, config.retention_days)
            # Intervalo após o fim da rodada: nunca sobrepõe execuções.
            await asyncio.sleep(config.interval_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Coleta interrompida. Verifique a aplicação e o armazenamento.")
        raise


def create_app(config_path=None, db_path=None, start_collector=True):
    @asynccontextmanager
    async def lifespan(app):
        app.state.config = load_config(config_path or os.getenv("MONITOR_CONFIG", "config/services.yml"))
        app.state.store = Store(db_path or os.getenv("MONITOR_DB", "data/monitor.db"))
        task = asyncio.create_task(collect(app.state.config, app.state.store)) if start_collector else None
        app.state.collector = task
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    app = FastAPI(title="Service Health Monitor", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def running():
        task = app.state.collector
        return bool(task and not task.done())

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    def health():
        okay = running()
        return JSONResponse({"status": "ok" if okay else "collector_stopped"}, status_code=200 if okay else 503)

    @app.get("/api/snapshot")
    def snapshot():
        return JSONResponse(dict(server_time=time.time(), collector_running=running(),
                                 interval_seconds=app.state.config.interval_seconds,
                                 services=app.state.store.snapshot(app.state.config.services)),
                            headers={"Cache-Control": "no-store"})

    return app


app = create_app()

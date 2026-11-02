"""Called It: a live-match decision simulator for fans.

Run:  uvicorn app:app --reload        then open http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from called_it import scenario as sc
from called_it.analyst import Analyst
from called_it.rounds import RoundError, RoundStore
from called_it.scoring import match_iq

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

BASE = Path(__file__).parent


class PickIn(BaseModel):
    fan_id: str = Field(min_length=4, max_length=64)
    option: str
    reason: str | None = None


class FanIn(BaseModel):
    fan_id: str = Field(min_length=4, max_length=64)


class AskIn(FanIn):
    question: str = Field(min_length=1, max_length=300)


def create_app(store: RoundStore | None = None, analyst: Analyst | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the local model in the background so the first analysis isn't the one that waits.
        a = app.state.analyst
        if a.backend.kind == "local" and os.getenv("WARM_MODEL", "1") == "1":
            threading.Thread(target=_safe_load, args=(a.backend,), daemon=True).start()
        yield

    app = FastAPI(title="Called It", version="1.0", lifespan=lifespan)
    app.state.store = store or RoundStore()
    app.state.analyst = analyst or Analyst()

    @app.exception_handler(RoundError)
    def round_error(_: Request, e: RoundError):
        return JSONResponse({"detail": str(e)}, status_code=e.status)

    def _fan_pick(r, fan_id):
        p = r.picks.get(fan_id)
        return (p.option, p.reason, p.on_time) if p else (None, None, False)

    def _prefetch(r, fan_id):
        """Start the fan's analysis in the background once their call can no longer change."""
        p = r.picks.get(fan_id) if fan_id else None
        if p and (p.locked_early_at is not None or r.phase(app.state.store.clock()) != "open"):
            app.state.analyst.prefetch(p.option, p.reason, p.on_time)

    def _require_done(r):
        if r.phase(app.state.store.clock()) != "done":
            raise HTTPException(409, "Available once the over has been bowled.")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (BASE / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    def health():
        return {"ok": True, "analyst": app.state.analyst.info(), "scenario": sc.SCENARIO_ID}

    @app.get("/api/rounds/current")
    def current(fan_id: str | None = None):
        r = app.state.store.current()
        _prefetch(r, fan_id)
        return r.public_state(fan_id, app.state.store.clock())

    @app.post("/api/rounds")
    def new_round():
        """Start a fresh round for everyone (demo replay)."""
        r = app.state.store.create()
        return r.public_state(None, app.state.store.clock())

    @app.get("/api/rounds/{round_id}")
    def state(round_id: str, fan_id: str | None = None):
        r = app.state.store.get(round_id)
        _prefetch(r, fan_id)
        return r.public_state(fan_id, app.state.store.clock())

    @app.post("/api/rounds/{round_id}/picks")
    def pick(round_id: str, body: PickIn):
        store = app.state.store
        store.run(round_id, lambda r, now: r.submit(body.fan_id, body.option, body.reason, now))
        _prefetch(store.get(round_id), body.fan_id)
        return store.get(round_id).public_state(body.fan_id, store.clock())

    @app.post("/api/rounds/{round_id}/lock")
    def lock(round_id: str, body: FanIn):
        store = app.state.store
        store.run(round_id, lambda r, now: r.lock(body.fan_id, now))
        _prefetch(store.get(round_id), body.fan_id)
        return store.get(round_id).public_state(body.fan_id, store.clock())

    @app.post("/api/rounds/{round_id}/skip")
    def skip(round_id: str):
        store = app.state.store
        store.run(round_id, lambda r, now: r.skip_to_deadline(now))
        return store.get(round_id).public_state(None, store.clock())

    @app.post("/api/rounds/{round_id}/analysis")
    def analysis(round_id: str, body: FanIn):
        r = app.state.store.get(round_id)
        _require_done(r)
        pick_, reason, on_time = _fan_pick(r, body.fan_id)
        return app.state.analyst.analyse(pick_, reason, on_time)

    @app.post("/api/rounds/{round_id}/ask")
    def ask(round_id: str, body: AskIn):
        r = app.state.store.get(round_id)
        _require_done(r)
        pick_, _, _ = _fan_pick(r, body.fan_id)
        return app.state.analyst.ask(body.question, pick_)

    @app.get("/api/rounds/{round_id}/iq")
    def iq(round_id: str, fan_id: str):
        r = app.state.store.get(round_id)
        _require_done(r)
        return match_iq(*_fan_pick(r, fan_id))

    return app


def _safe_load(backend):
    try:
        backend.load()
    except Exception as e:  # surfaced later as a fallback note
        logging.getLogger("called_it").warning("Model warm-up failed: %s", e)


app = create_app()

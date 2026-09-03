"""NaviPort Pi application.

Runs on the Raspberry Pi (and, unchanged, in local Docker). It:
  1. Polls the backend for its order queue so it's *aware* of orders to make.
  2. Serves a small local UI: the queue, a "scan" box, and per-order controls.
  3. On scan, claims the order (the backend lock guarantees one Pi wins), then
     brews and reports completion/error.

The UI's "scan" box stands in for the camera: on a real Pi, hardware.scan_camera
feeds tokens in automatically; locally you paste the token the customer's phone
shows as a QR.
"""

import asyncio
import contextlib
from pathlib import Path

import hardware
from client import MachineApiError
from client import client
from fastapi import FastAPI
from fastapi import Form
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from config import config

app = FastAPI(title="NaviPort Pi")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class State:
    """In-memory snapshot the UI renders and the poll loop refreshes."""

    def __init__(self):
        self.queue: list[dict] = []
        self.connected: bool = False
        self.last_error: str | None = None
        # order_ids currently being brewed by this Pi.
        self.brewing: set[str] = set()


state = State()


async def poll_loop():
    """Continuously refresh the queue from the backend."""
    while True:
        try:
            state.queue = await client.fetch_queue()
            state.connected = True
            state.last_error = None
        except MachineApiError as exc:
            state.connected = False
            state.last_error = exc.detail
        except Exception as exc:  # network down, backend not up yet, etc.
            state.connected = False
            state.last_error = str(exc)
        await asyncio.sleep(config.POLL_INTERVAL)


async def brew_and_complete(order_id: str):
    """Brew the drink then tell the backend it's done (or report failure)."""
    state.brewing.add(order_id)
    try:
        order = next((o for o in state.queue if o["id"] == order_id), {"id": order_id})
        await hardware.brew(order)
        await client.complete(order_id)
    except MachineApiError as exc:
        state.last_error = f"complete failed: {exc.detail}"
    except Exception as exc:
        state.last_error = f"brew failed: {exc}"
        with contextlib.suppress(Exception):
            await client.report_error(order_id, str(exc))
    finally:
        state.brewing.discard(order_id)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(poll_loop())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    pending = [o for o in state.queue if o["order_status"] == "O"]
    in_progress = [o for o in state.queue if o["order_status"] == "S"]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "device_name": config.DEVICE_NAME,
            "connected": state.connected,
            "last_error": state.last_error,
            "pending": pending,
            "in_progress": in_progress,
            "brewing": state.brewing,
            "poll_interval": config.POLL_INTERVAL,
        },
    )


@app.post("/scan")
async def scan(qr_token: str = Form(...)):
    """Simulated camera scan: claim the order behind this QR token, then brew."""
    try:
        order = await client.scan(qr_token.strip())
        asyncio.create_task(brew_and_complete(order["id"]))
    except MachineApiError as exc:
        state.last_error = exc.detail
    return RedirectResponse("/", status_code=303)


@app.post("/brew/{order_id}")
async def brew(order_id: str):
    """Manually kick off brewing for an order this Pi already holds."""
    if order_id not in state.brewing:
        asyncio.create_task(brew_and_complete(order_id))
    return RedirectResponse("/", status_code=303)


@app.post("/error/{order_id}")
async def error(order_id: str, message: str = Form("Manual error from Pi UI")):
    try:
        await client.report_error(order_id, message)
    except MachineApiError as exc:
        state.last_error = exc.detail
    return RedirectResponse("/", status_code=303)


@app.get("/healthz")
async def healthz():
    return {"connected": state.connected, "queue_size": len(state.queue)}

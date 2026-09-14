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
import json
from pathlib import Path

import hardware
import websockets
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
        # True while the push websocket to the backend is up ("live" mode);
        # False means we're on the polling fallback.
        self.ws_connected: bool = False
        # order_ids currently being brewed by this Pi.
        self.brewing: set[str] = set()


state = State()


async def refresh_queue():
    """Fetch the queue over HTTP -- the single source of truth."""
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


async def poll_loop():
    """Refresh the queue on a timer.

    This is the fallback transport: while the websocket is up we only poll
    occasionally as a safety net; when it's down we poll at full speed.
    """
    while True:
        await refresh_queue()
        interval = (
            config.SLOW_POLL_INTERVAL if state.ws_connected else config.POLL_INTERVAL
        )
        await asyncio.sleep(interval)


async def _ping_loop(ws):
    """Keep the backend's last_seen presence fresh while the socket is up."""
    while True:
        await asyncio.sleep(config.PING_INTERVAL)
        await ws.send(json.dumps({"type": "ping"}))


async def ws_loop():
    """Hold a push socket to the backend; refetch the queue on every nudge.

    The socket never carries order data -- the backend sends "queue.changed"
    and we refetch over HTTP. Reconnects forever with a short delay.
    """
    while True:
        try:
            async with websockets.connect(
                config.WS_URL,
                additional_headers={"X-Device-Token": config.DEVICE_TOKEN},
            ) as ws:
                state.ws_connected = True
                await refresh_queue()  # snapshot on (re)connect
                pinger = asyncio.create_task(_ping_loop(ws))
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("type") == "queue.changed":
                            await refresh_queue()
                finally:
                    pinger.cancel()
        except Exception as exc:
            state.last_error = f"websocket: {exc}"
        state.ws_connected = False
        await asyncio.sleep(config.WS_RECONNECT_SECONDS)


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
    asyncio.create_task(ws_loop())


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
            "live": state.ws_connected,
            "last_error": state.last_error,
            "pending": pending,
            "in_progress": in_progress,
            "brewing": state.brewing,
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
    return {
        "connected": state.connected,
        "live": state.ws_connected,
        "queue_size": len(state.queue),
    }

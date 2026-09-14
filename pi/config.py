"""Runtime configuration for the NaviPort Raspberry Pi app.

Everything is read from the environment so the exact same image runs unchanged
in local Docker and on a real Pi -- only the env values differ.
"""

import os


class Config:
    # Base URL of the Navi backend API, e.g. http://django:8000/api in local
    # docker, or https://api.navi... on a deployed Pi.
    API_BASE_URL = os.environ.get("NAVI_API_URL", "http://django:8000/api").rstrip("/")

    # The device token issued to this Pi (RaspberryPi.device_token). Sent as the
    # X-Device-Token header on every machine API call.
    DEVICE_TOKEN = os.environ.get("NAVI_DEVICE_TOKEN", "")

    # How often (seconds) to poll the backend for its order queue. Polling is
    # the fallback transport; while the websocket is up we poll at
    # SLOW_POLL_INTERVAL instead, as a safety net.
    POLL_INTERVAL = float(os.environ.get("NAVI_POLL_INTERVAL", "3"))
    SLOW_POLL_INTERVAL = float(os.environ.get("NAVI_SLOW_POLL_INTERVAL", "30"))

    # Websocket to the backend for push updates + presence. Derived from the
    # API URL (http->ws, /api stripped) unless set explicitly.
    WS_URL = os.environ.get("NAVI_WS_URL", "")

    # How often (seconds) to ping over the websocket so the backend's
    # last_seen presence stays fresh.
    PING_INTERVAL = float(os.environ.get("NAVI_PING_INTERVAL", "15"))

    # Delay (seconds) before re-dialing a dropped websocket.
    WS_RECONNECT_SECONDS = float(os.environ.get("NAVI_WS_RECONNECT_SECONDS", "3"))

    # Simulated seconds to "make" a drink before auto/ manual completion.
    BREW_SECONDS = float(os.environ.get("NAVI_BREW_SECONDS", "5"))

    # Port the local queue UI listens on.
    UI_PORT = int(os.environ.get("NAVI_UI_PORT", "9000"))

    # A friendly label for this Pi, shown in the UI.
    DEVICE_NAME = os.environ.get("NAVI_DEVICE_NAME", "NaviPort Pi")

    def __init__(self):
        if not self.WS_URL:
            base = self.API_BASE_URL.removesuffix("/api")
            scheme_swapped = base.replace("https://", "wss://", 1).replace(
                "http://", "ws://", 1
            )
            self.WS_URL = f"{scheme_swapped}/ws/machine/"


config = Config()

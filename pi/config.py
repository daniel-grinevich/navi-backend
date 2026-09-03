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

    # How often (seconds) to poll the backend for its order queue.
    POLL_INTERVAL = float(os.environ.get("NAVI_POLL_INTERVAL", "3"))

    # Simulated seconds to "make" a drink before auto/ manual completion.
    BREW_SECONDS = float(os.environ.get("NAVI_BREW_SECONDS", "5"))

    # Port the local queue UI listens on.
    UI_PORT = int(os.environ.get("NAVI_UI_PORT", "9000"))

    # A friendly label for this Pi, shown in the UI.
    DEVICE_NAME = os.environ.get("NAVI_DEVICE_NAME", "NaviPort Pi")


config = Config()

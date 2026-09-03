"""Hardware abstraction -- the ONLY Pi-specific code.

On a real Pi these functions drive the camera and the espresso machine (GPIO /
serial). In local Docker there's no hardware, so they're stubbed: "scanning"
happens by pasting a token into the UI, and "brewing" is a timed sleep. Swap
this module's internals when you flash a physical Pi; nothing else changes.
"""

import asyncio

from config import config


async def brew(order: dict) -> None:
    """Pretend to make the drink. On real hardware, drive the espresso machine."""
    await asyncio.sleep(config.BREW_SECONDS)


def scan_camera() -> str | None:
    """Read a QR from the camera. Stubbed to None in the simulator.

    On a real Pi this would grab a frame and decode any QR in it (e.g. via
    picamera2 + pyzbar) and return the token string, or None if nothing seen.
    """
    return None

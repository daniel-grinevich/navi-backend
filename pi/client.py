"""Thin async client over the backend's machine order API.

This is the *only* part of the Pi that talks to Navi. It authenticates every
request with the device token, exactly as a deployed Pi would.
"""

import httpx

from config import config


class MachineApiError(Exception):
    """Raised when the backend rejects a machine request."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


class NaviClient:
    def __init__(self):
        self._headers = {"X-Device-Token": config.DEVICE_TOKEN}
        self._base = config.API_BASE_URL

    async def _request(self, method: str, path: str, **kwargs):
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
        if resp.status_code >= 400:
            detail = _safe_detail(resp)
            raise MachineApiError(resp.status_code, detail)
        if resp.content:
            return resp.json()
        return None

    async def fetch_queue(self):
        """Return the orders this Pi should know about (pending + in-progress)."""
        return await self._request("GET", "/machine/orders/queue/")

    async def scan(self, qr_token: str):
        """Claim an order from a scanned QR token (the camera path)."""
        return await self._request(
            "POST", "/machine/orders/scan/", json={"qr_token": qr_token}
        )

    async def start(self, order_id: str):
        """Claim an order directly by id (testing path)."""
        return await self._request("POST", f"/machine/orders/{order_id}/start/")

    async def complete(self, order_id: str):
        return await self._request(
            "POST",
            f"/machine/orders/{order_id}/complete/",
            json={"outcome": "complete"},
        )

    async def report_error(self, order_id: str, message: str):
        return await self._request(
            "POST",
            f"/machine/orders/{order_id}/complete/",
            json={"outcome": "error", "error_message": message},
        )


def _safe_detail(resp) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text or "request failed"
    if isinstance(body, dict):
        return str(body.get("detail") or body)
    return str(body)


client = NaviClient()

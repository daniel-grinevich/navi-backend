"""Thin TaxJar client: look up the combined sales-tax rate for an address.

Used by the nightly job that refreshes EffectiveTaxRate; not called in any
request/scan path. Uses the stdlib so it adds no dependency.
"""

import json
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings

TAXJAR_RATES_URL = "https://api.taxjar.com/v2/rates/{zip}"
REQUEST_TIMEOUT_SECONDS = 10


def fetch_combined_rate(navi_port):
    """Return the combined tax rate (as a Decimal fraction) for a NaviPort's
    address, or None if it can't be determined.

    Raises urllib.error.URLError/HTTPError on a failed request so the caller can
    log and keep the last known rate rather than overwriting it with a bad value.
    """
    if not navi_port.postal_code:
        return None

    params = {"country": navi_port.country or "US"}
    if navi_port.state_or_region:
        params["state"] = navi_port.state_or_region
    if navi_port.city:
        params["city"] = navi_port.city
    if navi_port.address_line_1:
        params["street"] = navi_port.address_line_1

    base_url = TAXJAR_RATES_URL.format(zip=navi_port.postal_code)
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(  # noqa: S310 (https URL, not user-controlled)
        url,
        headers={"Authorization": f"Bearer {settings.TAXJAR_API_KEY}"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        payload = json.loads(response.read())

    combined = payload.get("rate", {}).get("combined_rate")
    if combined is None:
        return None
    return Decimal(str(combined))

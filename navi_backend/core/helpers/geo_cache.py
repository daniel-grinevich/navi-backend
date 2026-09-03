import time

import requests

CODE_200 = 200


def send_geo_request(lat, lng, num_request=0, max_retries=5):
    if num_request >= max_retries:
        err = f"Failed after {max_retries} retries."
        raise Exception(err)  # noqa: TRY002

    time.sleep(num_request * 1)

    response = requests.get(
        f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}",
        headers={"User-Agent": "NaviApi/1.0"},
        timeout=30,
    )

    if response.status_code != CODE_200:
        return send_geo_request(lat, lng, num_request + 1, max_retries)
    return response.json()


def geocode_address_fields(lat, lng):
    """Reverse-geocode coordinates into ``AddressModel`` field values.

    Returns a dict of address field name -> value. Raises ``ValueError`` when the
    geocoder returns no usable address; network/HTTP failures propagate from
    :func:`send_geo_request` so a Celery task can retry them.
    """
    response = send_geo_request(lat, lng)
    address_info = response.get("address", {})

    if not address_info:
        err = "address_info is empty."
        raise ValueError(err)

    road = address_info.get("road", "")
    address_parts = [part.strip() for part in road.split(",")] if road else []

    line_1 = ""
    line_2 = ""
    line_3 = ""
    for index, part in enumerate(address_parts):
        if index == 0:
            house_number = address_info.get("house_number", "")
            line_1 = f"{house_number} {part}".strip()
        elif index == 1:
            line_2 = part
        elif not line_3:
            line_3 = part
        else:
            line_3 += f", {part}"

    return {
        "address_line_1": line_1,
        "address_line_2": line_2,
        "address_line_3": line_3,
        "city": address_info.get("city", ""),
        "state_or_region": address_info.get("state", ""),
        "postal_code": address_info.get("postcode", ""),
        "country": address_info.get("country_code", "US").upper(),
    }

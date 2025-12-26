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

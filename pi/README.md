# NaviPort Raspberry Pi app

The program that runs on a NaviPort's Raspberry Pi: it watches the backend for
orders, claims one when its QR is scanned, "makes" the drink, and reports the
result. The **same image** runs locally under Docker (QEMU-emulated ARM64, on
Balena's Raspberry Pi OS base) and on a real Pi — only env vars and
`hardware.py` differ.

## Layout

| File | Role |
| --- | --- |
| `app.py` | FastAPI app: background queue poller + local queue UI |
| `client.py` | Async wrapper over the backend machine API (token auth) |
| `hardware.py` | **Only** Pi-specific code — camera + espresso stubs |
| `config.py` | All config, read from env |
| `templates/index.html` | The queue UI |
| `Dockerfile` | Balena `raspberrypi4-64-python` base (real ARM64 Pi userland) |

## How the flow works

1. Customer places an order → it sits in status `O` (Ordered). Their phone shows
   `order.qr_token` (a signed, opaque token — not the raw order id) as a QR.
2. The Pi polls `GET /api/machine/orders/queue/` and shows the order under
   **Waiting for pickup**.
3. The QR is scanned → the Pi calls `POST /api/machine/orders/scan/` with the
   token. The backend verifies the signature and **atomically** claims the order
   (`O → S`, locked to this Pi). Exactly one Pi can win the claim.
4. The Pi brews (stubbed sleep), then `POST /api/machine/orders/<id>/complete/`
   with `outcome=complete` → payment captured, `→ D`, invoice generated. On
   failure it sends `outcome=error` → the claim is released and the order
   returns to `O`.
5. The customer's websocket streams every transition live.

The lock is just the order's status column plus `claimed_by`/`claimed_at`: a
single conditional `UPDATE ... WHERE order_status='O'` guarantees one winner, and
a claim older than `CLAIM_LEASE_SECONDS` (5 min) can be reclaimed if a Pi crashes
mid-drink.

## Running locally

```bash
# 1. Bring up the backend (and everything else).
make up            # or: docker compose -f docker-compose.local.yml up

# 2. Register a simulator Pi + NaviPort and grab its device token.
docker compose -f docker-compose.local.yml run --rm django \
    python manage.py register_sim_pi

# 3. Export the token and start the Pi container.
export NAVI_DEVICE_TOKEN=<token from step 2>
docker compose -f docker-compose.local.yml up pi

# 4. Open the queue UI.
open http://localhost:9002
```

To exercise a pickup: create an order via the API, get its `qr_token` (from the
order response, or `register_sim_pi --order <id>`), and paste it into the UI's
scan box — that stands in for holding the phone up to the camera.

## Deploying to a real Pi

Swap the internals of `hardware.py`:
- `scan_camera()` → grab a frame and decode the QR (e.g. `picamera2` + `pyzbar`),
  and have `app.py` feed decoded tokens into the same scan path.
- `brew()` → drive the espresso machine over GPIO/serial.

Set `NAVI_API_URL`, `NAVI_DEVICE_TOKEN`, and `NAVI_DEVICE_NAME`. Everything else
is identical to local.

# Balena's official Raspberry Pi 4 (64-bit) base image: the same ARM64 userland
# and Raspberry Pi OS packages a real Pi runs. On an x86 dev machine Docker runs
# it under QEMU (see the `platform:` in docker-compose.local.yml), so locally you
# exercise genuine ARM, not x86 pretending to be a Pi.
FROM balenalib/raspberrypi4-64-python:3.11-bookworm-run

# Balena images support cross-build QEMU emulation on the host during build.
RUN [ "cross-build-start" ]

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN [ "cross-build-end" ]

EXPOSE 9000

# Reload disabled: this mirrors the read-only app you'd flash onto a real Pi.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]

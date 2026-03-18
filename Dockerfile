# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# 1. Environment & JIT Setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages" \

WORKDIR /app

# 2. The "Single-Pass" System Install
# We combine the repo setup, package install, and cleanup into ONE layer.
# This prevents Docker from creating intermediate snapshots on the SD card.
RUN apt-get update && apt-get install -y --no-install-recommends wget gnupg && \
    wget -qO /usr/share/keyrings/raspberrypi.asc https://archive.raspberrypi.com/debian/raspberrypi.gpg.key && \
    echo "deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi.asc] http://archive.raspberrypi.com/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libcamera-apps-lite \
    python3-libcamera \
    python3-picamera2 \
    python3-lgpio \
    python3-gpiozero \
    curl && \
    apt-get purge -y wget gnupg && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 3. The "Single-Pass" Python Install
COPY requirements.txt .
# By putting Pillow on the same line as requirements.txt, pip resolves 
# everything in one single fast sweep instead of running twice.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt "Pillow>=10.2.0"

# 4. App Code (Must stay at the absolute bottom!)
COPY . .

CMD ["python", "main.py"]
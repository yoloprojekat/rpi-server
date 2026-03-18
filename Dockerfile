# syntax=docker/dockerfile:1
# Downgraded to 3.11 to perfectly match the Raspberry Pi OS hardware binaries
FROM python:3.11-slim-bookworm

# 1. Environment Setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages"

WORKDIR /app

# 2. The "Single-Pass" System Install
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

# 3. The "Single-Pass" Python Install & Pillow Security Patch
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt "Pillow>=10.2.0"

# 4. App Code
COPY . .

CMD ["python", "main.py"]
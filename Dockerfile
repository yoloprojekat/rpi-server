# Use Debian 13 (Trixie) slim for ARM64
FROM arm64v8/debian:trixie-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install prerequisites to add the Raspberry Pi Repository
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 2. Add the Raspberry Pi Foundation repository and GPG key
# This allows apt to find 'python3-picamera2' and 'libcamera-ipp-raspberrypi'
RUN curl -fsSL http://archive.raspberrypi.org/debian/raspberrypi.gpg.key | gpg --dearmor -o /etc/apt/trusted.gpg.d/raspberrypi-archive-keyring.gpg \
    && echo "deb http://archive.raspberrypi.org/debian/ trixie main" > /etc/apt/sources.list.d/raspi.list

# 3. Install System-level hardware dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-picamera2 \
    python3-av \
    python3-numpy \
    python3-aiohttp \
    python3-gpiozero \
    python3-lgpio \
    python3-pip \
    libcamera-v4l2 \
    libcamera-ipp-raspberrypi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 4. Install Python-specific WebRTC and CORS tools
# Using --break-system-packages is required for Debian 12+ internally
RUN pip install --no-cache-dir --break-system-packages aiohttp-cors aiortc

# 5. Copy your application
COPY main.py .

# Run the script
ENTRYPOINT ["python3", "main.py"]
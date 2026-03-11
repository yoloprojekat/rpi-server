# Use the new Debian 13 Stable base for ARM64
FROM arm64v8/debian:trixie-slim

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install System-level hardware dependencies
# We install these via apt because they are optimized for the Pi's hardware
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

# Install Python-specific WebRTC and CORS tools
# --break-system-packages is safe here because it's an isolated container
RUN pip install --break-system-packages aiohttp-cors aiortc

# Copy your Python script into the container
COPY main.py .

# Run the script when the container starts
ENTRYPOINT ["python3", "main.py"]
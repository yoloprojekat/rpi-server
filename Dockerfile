# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# 1. Install build-only dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    swig \
    wget \
    unzip \
    pkg-config \
    binutils \
    cmake \
    ninja-build \
    libcap-dev \
    libgpiod-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Upgrade pip and build Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # Pre-install numpy<2 here so wheel building uses the correct C-API headers
    pip install --no-cache-dir "numpy<2" && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# Stage 2: Final Runtime
FROM python:3.11-slim-bookworm

# 1. Fix PYTHONPATH and Python Behavior
# This points Docker's Python to the OS packages so it finds the apt-installed libcamera
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages"

WORKDIR /app

# 2. Copy compiled C libraries from builder
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 3. Add Raspberry Pi OS repository & Install hardware libraries (INCLUDING picamera2 & Pi 5 GPIO)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends wget gnupg && \
    wget -qO /usr/share/keyrings/raspberrypi.asc https://archive.raspberrypi.com/debian/raspberrypi.gpg.key && \
    echo "deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi.asc] http://archive.raspberrypi.com/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list && \
    apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libcamera-apps-lite \
    python3-libcamera \
    python3-kms++ \
    python3-picamera2 \
    python3-lgpio \
    python3-gpiozero \
    libwebcam0 \
    libcap2 \
    gpiod \
    libgpiod2 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && apt-get purge -y wget gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python packages from wheels and patch vulnerabilities
# pip overrides the apt-installed pillow with the secure version, and fixes the numpy ABI
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* "numpy<2.0.0" "pillow>=10.2.0" && \
    rm -rf /wheels requirements.txt

# 5. Copy application code
COPY . .

CMD ["python", "main.py"]
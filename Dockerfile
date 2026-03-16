# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# 1. Install build-only dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# 2. Compile lgpio C library and strip debug symbols
RUN wget -q https://github.com/joan2937/lg/archive/master.zip && \
    unzip -q master.zip && \
    cd lg-master && make && make install && \
    strip --strip-unneeded /usr/local/lib/lib*.so* && \
    cd .. && rm -rf master.zip lg-master

# 3. Upgrade pip and build Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# Stage 2: Final Runtime
FROM python:3.11-slim-bookworm

# 1. Fix PYTHONPATH and Python Behavior
# We MUST point Docker's custom Python to the OS dist-packages so it finds libcamera
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages"

WORKDIR /app

# 2. Copy compiled C libraries from builder
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 3. Add Raspberry Pi OS repository & Install hardware libraries
RUN apt-get update && apt-get install -y --no-install-recommends wget gnupg && \
    # Fetch Raspberry Pi GPG key
    wget -qO /usr/share/keyrings/raspberrypi.asc https://archive.raspberrypi.com/debian/raspberrypi.gpg.key && \
    # Add Raspberry Pi repository (forced to arm64 to prevent QEMU confusion)
    echo "deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi.asc] http://archive.raspberrypi.com/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list && \
    # Update again and install the Pi-specific camera stack + general hardware deps
    apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libcamera-apps-lite \
    python3-libcamera \
    python3-kms++ \
    python3-picamera2 \
    libwebcam0 \
    libcap2 \
    gpiod \
    libgpiod2 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    # Clean up wget/gnupg to keep the image strictly minimal
    && apt-get purge -y wget gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python packages from wheels
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels requirements.txt

# 5. Copy application code
COPY . .

CMD ["python", "main.py"]
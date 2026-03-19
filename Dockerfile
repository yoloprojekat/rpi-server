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

# 2. Compile lgpio C library
RUN wget -q https://github.com/joan2937/lg/archive/master.zip && \
    unzip -q master.zip && \
    cd lg-master && make && make install && \
    strip --strip-unneeded /usr/local/lib/lib*.so* && \
    cd .. && rm -rf master.zip lg-master

# 3. Build Wheels (Ultralytics/Torch takes a while here)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir "numpy<2" && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# Stage 2: Final Runtime
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages"

WORKDIR /app

# 1. Copy compiled C libraries
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 2. RPi OS Repo & Hardware Libraries
RUN apt-get update && apt-get install -y --no-install-recommends wget gnupg && \
    wget -qO /usr/share/keyrings/raspberrypi.asc https://archive.raspberrypi.com/debian/raspberrypi.gpg.key && \
    echo "deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi.asc] http://archive.raspberrypi.com/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libcamera-apps-lite \
    python3-libcamera \
    python3-kms++ \
    python3-picamera2 \
    python3-lgpio \
    python3-gpiozero \
    libcap2 \
    gpiod \
    libgpiod2 \
    # --- ADDED FOR OPENCV & YOLO ---
    libglib2.0-0 \
    libgl1-mesa-glx \
    libsm6 \
    libxext6 \
    libxrender1 \
    && apt-get purge -y wget gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 3. Install Python packages from wheels
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* "numpy<2.0.0" && \
    rm -rf /wheels requirements.txt

# 4. Copy application code
COPY . .

# Ensure the model file is present (or downloaded during build)
# RUN python3 -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"

# Use your specific port for the competition
EXPOSE 1607

CMD ["python", "main.py"]
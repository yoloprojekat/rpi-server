# ==========================================
# Stage 1: Builder
# ==========================================
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
    libcamera-dev \
    libgpiod-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Compile lgpio C library and strip debug symbols
RUN wget -q https://github.com/joan2937/lg/archive/master.zip && \
    unzip -q master.zip && \
    cd lg-master && make && make install && \
    strip --strip-unneeded /usr/local/lib/lib*.so* && \
    cd .. && rm -rf master.zip lg-master

# 3. Upgrade pip/setuptools and build Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# ==========================================
# Stage 2: Final Runtime
# ==========================================
FROM python:3.11-slim-bookworm

# 1. Set environment variables early
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# CRUCIAL ADDITION: Point the container's Python environment to the system packages directory
# Without this, Python 3.11 won't see the apt-installed libcamera and picamera2 modules.
ENV PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH}"

WORKDIR /app

# 2. Copy compiled C libraries from builder
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 3. Install ONLY runtime libraries
# Merged your existing runtime libraries with the required libcamera Python bindings
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libwebcam0 \
    libcap2 \
    gpiod \
    libgpiod2 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libcamera-apps-lite \
    python3-libcamera \
    python3-kms++ \
    python3-picamera2 \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python packages from wheels and clean up immediately
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels requirements.txt

# 5. Copy application code last
COPY . .

CMD ["python", "main.py"]
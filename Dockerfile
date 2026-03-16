# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# 1. Install build-only dependencies
# ADDED: libcap-dev (fixes python-prctl error)
# ADDED: cmake, ninja-build, libcamera-dev, libgpiod-dev (prevents OpenCV & Picamera2 wheel errors)
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
# Upgrading pip and setuptools first prevents legacy `setup.py` metadata generation failures
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# Stage 2: Final Runtime
FROM python:3.11-slim-bookworm

# 1. Set environment variables early
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Copy compiled C libraries from builder
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 3. Install ONLY runtime libraries
# ADDED: libcap2 (The runtime equivalent of libcap-dev so python-prctl can execute)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libwebcam0 \
    libcap2 \
    gpiod \
    libgpiod2 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python packages from wheels and clean up immediately
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels requirements.txt

# 5. Copy application code last
COPY . .

CMD ["python", "main.py"]
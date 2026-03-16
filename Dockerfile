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
    && rm -rf /var/lib/apt/lists/*

# 2. Compile lgpio C library and strip debug symbols
# The `strip` command significantly reduces the size of the compiled .so files
RUN wget -q https://github.com/joan2937/lg/archive/master.zip && \
    unzip -q master.zip && \
    cd lg-master && make && make install && \
    strip --strip-unneeded /usr/local/lib/lib*.so* && \
    cd .. && rm -rf master.zip lg-master

# 3. Build Python wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


# Stage 2: Final Runtime
FROM python:3.11-slim-bookworm

# 1. Set environment variables early
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Copy compiled C libraries from builder
# Doing this before apt-get maximizes Docker's layer cache since these rarely change
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/
COPY --from=builder /usr/local/include/lgpio.h /usr/local/include/
RUN ldconfig

# 3. Install ONLY runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcamera0.0 \
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

# 5. Copy application code last (this layer changes most frequently)
COPY . .

CMD ["python", "main.py"]
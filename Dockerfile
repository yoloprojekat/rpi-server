FROM python:3.13-slim-bookworm

WORKDIR /app

# 1. Instalacija sistemskih zavisnosti + SWIG koji je falio
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    swig \
    python3-dev \
    wget \
    unzip \
    pkg-config \
    libcap-dev \
    libcamera-ipa \
    libglib2.0-0 \
    libwebcam0 \
    gpiod \
    libgpiod-dev \
    libgl1-mesa-glx \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# 2. Kompajliranje lgpio C biblioteke (mora biti pre pip instalacije)
RUN wget https://github.com/joan2937/lg/archive/master.zip && \
    unzip master.zip && \
    cd lg-master && \
    make && \
    make install && \
    cd .. && \
    rm -rf master.zip lg-master && \
    ldconfig

# 3. Osvežavanje pip-a i instalacija Python biblioteka
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. Kopiranje ostatka koda
COPY . .

# 5. Pokretanje aplikacije
CMD ["python", "-u", "main.py"]
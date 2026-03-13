FROM python:3.13-slim-bookworm

WORKDIR /app

# 1. Instalacija sistemskih zavisnosti
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    swig \
    python3-dev \
    # KLJUČNE BIBLIOTEKE ZA KAMERU:
    libcamera-dev \
    libcamera-ipa \
    python3-libcamera \ 
    # Ostalo
    wget \
    unzip \
    pkg-config \
    libcap-dev \
    libwebcam0 \
    gpiod \
    libgpiod-dev \
    libgl1-mesa-glx \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# 2. Kompajliranje lgpio (ovo ti je već radilo)
RUN wget https://github.com/joan2937/lg/archive/master.zip && \
    unzip master.zip && \
    cd lg-master && make && make install && \
    cd .. && rm -rf master.zip lg-master && ldconfig

# 3. Instalacija Python zavisnosti
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. FIX ZA LIBCAMERA: Ručno mapiranje ako ga pip ne vidi
# Ovo osigurava da Python vidi libcamera modul
RUN ln -s /usr/lib/python3/dist-packages/libcamera /usr/local/lib/python3.13/site-packages/libcamera || true

COPY . .
CMD ["python", "-u", "main.py"]
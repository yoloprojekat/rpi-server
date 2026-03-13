FROM python:3.12-slim-bookworm

WORKDIR /app

# 1. Instalacija sistemskih zavisnosti
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    swig \
    python3-dev \
    # Biblioteke za kameru koje su dostupne u Debianu
    libcamera-dev \
    libcamera-ipa \
    libwebcam0 \
    # Ostalo
    wget \
    unzip \
    pkg-config \
    libcap-dev \
    gpiod \
    libgpiod-dev \
    libgl1-mesa-glx \
    # OpenCV sistemske zavisnosti
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 2. Kompajliranje lgpio C biblioteke
RUN wget https://github.com/joan2937/lg/archive/master.zip && \
    unzip master.zip && \
    cd lg-master && make && make install && \
    cd .. && rm -rf master.zip lg-master && ldconfig

# 3. Osvežavanje pip-a i instalacija ključnih alata
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 4. Instalacija Python zavisnosti
# OpenCV-python-headless je bolji za Docker jer ne vuče GUI zavisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pokretanje sa unbuffered output-om
CMD ["python", "-u", "main.py"]
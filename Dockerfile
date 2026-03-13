FROM python:3.13-slim-bookworm

WORKDIR /app

# 1. Instalacija osnovnih alata, hardverskih biblioteka i alata za kompajliranje
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
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

# 2. Ručno kompajliranje originalne lgpio C biblioteke 
# Ovo direktno rešava "Failed to build lgpio" grešku u pip-u
RUN wget https://github.com/joan2937/lg/archive/master.zip && \
    unzip master.zip && \
    cd lg-master && \
    make && \
    make install && \
    cd .. && \
    rm -rf master.zip lg-master && \
    ldconfig

# 3. Osvežavanje pip-a i instalacija Python zavisnosti
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Kopiranje koda aplikacije
COPY . .

# 5. Pokretanje servera
CMD ["python", "-u", "main.py"]
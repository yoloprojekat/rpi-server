# Koristimo zvanični Python imidž baziran na Debian Trixie (13)
FROM python:3.13-slim-bookworm

# Postavljanje radnog direktorijuma
WORKDIR /app

# Instalacija sistemskih zavisnosti
# libcamera-ipa i libglib2.0 su neophodni za Picamera2
# liblgpio-dev je neophodan za kontrolu pinova na RPi 5
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcamera-ipa \
    libglib2.0-0 \
    libwebcam0 \
    liblgpio-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Kopiranje requirements.txt i instalacija Python zavisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiranje izvornog koda
COPY . .

# Portovi: 1606 (UDP komande), 1607 (HTTP Stream)
EXPOSE 1606/udp
EXPOSE 1607

# Pokretanje aplikacije
CMD ["python", "main.py"]
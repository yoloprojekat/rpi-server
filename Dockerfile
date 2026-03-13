FROM python:3.13-slim-bookworm

WORKDIR /app

# Instalacija sistemskih zavisnosti
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Alati za kompajliranje (neophodni za python-prctl i lgpio)
    build-essential \
    gcc \
    libcap-dev \
    # Hardverske biblioteke
    libcamera-ipa \
    libglib2.0-0 \
    libwebcam0 \
    gpiod \
    libgpiod-dev \
    libgl1-mesa-glx \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Kopiranje requirements.txt i instalacija
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiranje ostatka koda
COPY . .

# Pokretanje aplikacije
CMD ["python", "-u", "main.py"]
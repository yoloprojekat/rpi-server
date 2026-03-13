FROM python:3.13-slim-bookworm

WORKDIR /app

# Instalacija neophodnih sistemskih biblioteka
# Koristimo libgpiod-dev umesto liblgpio-dev jer je standardniji u Debianu
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Pokretanje aplikacije sa unbuffered output-om
CMD ["python", "-u", "main.py"]
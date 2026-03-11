<div align="center">

🐳 Pametno Vozilo - Docker Kontrolni Server

Kontejnerizovan Backend za Raspberry Pi 5 (Debian 13 Trixie)

<p align="center">
<i>Produkciono okruženje: Kontejnerizovan mrežni gateway i hardverska orkestracija optimizovana za RPi 5.</i>
</p>

</div>

🏗️ Docker Arhitektura i Benefiti

Implementacija Docker kontejnera na Debian 13 Stable sistemu rešava kritične izazove embedded razvoja i donosi sledeće prednosti:

Izolacija Zavisnosti (No Dependency Hell): Biblioteke kao što su aiortc i PyAV zahtevaju specifične verzije OpenSSL i FFmpeg. Docker izoluje ove binarne fajlove od host sistema, sprečavajući pucanje aplikacije prilikom sistemskih ažuriranja.

Host OS Zaštita (PEP 668): Debian 13 striktno sprovodi zaštitu sistemskog Python okruženja. Korišćenjem kontejnera, izbegavamo komplikovane virtuelne sredine na hostu i koristimo prednosti izolovane instalacije paketa.

Deterministički Deployment ($O(1)$): Vreme potrebno za setup novog uređaja smanjeno je sa 45+ minuta (kompilacija drajvera) na manje od 2 minuta (pull gotovog image-a).

Direktan Hardverski Pristup: Korišćenjem privileged: true i mapiranjem /dev particija, kontejner zadržava nativan pristup libcamera i lgpio interfejsima uz performanse identične bare-metal izvršavanju.

Mrežna Optimizacija: Upotreba network_mode: "host" eliminiše Docker bridge overhead, omogućavajući milisekundnu latenciju za UDP komande i nesmetanu WebRTC signalizaciju.

🚀 Ključni Moduli

🛰️ Real-Time Komunikacija

UDP Command Center: Asinhrona obrada komandi kretanja na portu 1606. Optimizovano za minimalni jitter u kontroli motora.

WebRTC Vision Engine: P2P video striming niskih latencija putem WebRTC /offer endpointa na portu 1607.

📸 Vision & Safety Engineering

Shared Camera Track: Arhitektura omogućava da N WebRTC klijenata istovremeno prate strim koristeći jedan jedini memorijski bafer, čime se drastično smanjuje opterećenje procesora ($O(1)$ scaling).

Motor Watchdog: Fail-safe mehanizam koji automatski gasi PWM signale ukoliko mrežna komunikacija kasni više od 0.5s.

⚙️ Brzi Start (Deployment)

Za pokretanje servera na Raspberry Pi 5 uređaju:

# 1. Kloniranje projekta
git clone [https://github.com/TvojUsername/rpi-server.git](https://github.com/TvojUsername/rpi-server.git)
cd rpi-server

# 2. Build i pokretanje u pozadini
docker compose up --build -d

# 3. Provera logova
docker compose logs -f


🛠 Tehnološki Stack

Komponenta

Tehnologija

Uloga

Baza

Docker (Debian 13 Trixie)

Izolacija i prenosivost

Logika

Python 3.13 (Asyncio)

Srce serverske logike

Kamera

python3-picamera2

Nativni RPi 5 video capture

GPIO

lgpio / gpiozero

Precizna kontrola motora

Mreža

aiortc (WebRTC)

Video prenos ultra-niske latencije

🔌 Hardverska Mapa Pinova (BCM)

Global PWM (Enable A+B): GPIO 18

Motor A (Prednji Levi): GPIO 17, 27

Motor B (Prednji Desni): GPIO 22, 23

Motor C (Zadnji Levi): GPIO 24, 25

Motor D (Zadnji Desni): GPIO 5, 6

<div align="center">

Autor: Danilo Stoletović • Mentor: Dejan Batanjac

ETŠ „Nikola Tesla“ Niš • 2026

</div>
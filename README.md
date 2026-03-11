<div align="center">

# 🐳 Pametno Vozilo - Docker Kontrolni Server
### *Kontejnerizovan Backend za Raspberry Pi 5 (Debian 13 Trixie)*

---

<p align="center">
  <i>Produkciono okruženje: Kontejnerizovan mrežni gateway i hardverska orkestracija optimizovana za RPi 5.</i>
</p>

[![Python](https://img.shields.io/badge/Python-3.13-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Deployment-Docker-2496ed?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Raspberry Pi](https://img.shields.io/badge/Hardware-RPi_5-c51a4a?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/)
[![WebRTC](https://img.shields.io/badge/Network-WebRTC-075985?style=for-the-badge&logo=webrtc&logoColor=white)](https://webrtc.org/)

</div>

---

## 🏗️ Docker Arhitektura i Benefiti

Implementacija Docker kontejnera na **Debian 13 Stable** sistemu rešava kritične izazove embedded razvoja i donosi sledeće prednosti:

* **Izolacija Zavisnosti (No Dependency Hell):** Biblioteke kao što su `aiortc` i `PyAV` zahtevaju specifične verzije `OpenSSL` i `FFmpeg`. Docker izoluje ove binarne fajlove od host sistema, sprečavajući pucanje aplikacije prilikom sistemskih ažuriranja.
* **Host OS Zaštita (PEP 668):** Debian 13 striktno sprovodi zaštitu sistemskog Python okruženja. Korišćenjem kontejnera, izbegavamo komplikovane virtuelne sredine na hostu i koristimo prednosti izolovane instalacije paketa.
* **Deterministički Deployment ($O(1)$):** Vreme potrebno za setup novog uređaja smanjeno je sa 45+ minuta (kompilacija drajvera) na manje od 2 minuta (povlačenje gotovog image-a).
* **Direktan Hardverski Pristup:** Korišćenjem `privileged: true` i mapiranjem `/dev` particija, kontejner zadržava nativan pristup `libcamera` i `lgpio` interfejsima uz performanse identične direktnom izvršavanju na hostu.
* **Mrežna Optimizacija:** Upotreba `network_mode: "host"` eliminiše Docker bridge overhead, omogućavajući milisekundnu latenciju za UDP komande i nesmetanu WebRTC signalizaciju.

---



## 🚀 Ključni Moduli

### 🛰️ Real-Time Komunikacija
* **UDP Command Center:** Asinhrona obrada komandi kretanja na portu `1606`. Optimizovano za minimalni jitter u kontroli motora.
* **WebRTC Vision Engine:** P2P video striming niskih latencija putem WebRTC `/offer` endpointa na portu `1607`.

### 📸 Vision & Safety Engineering
* **Shared Camera Track:** Arhitektura omogućava da N WebRTC klijenata istovremeno prate strim koristeći jedan jedini memorijski bafer, čime se drastično smanjuje opterećenje procesora ($O(1)$ scaling).
* **Motor Watchdog:** Fail-safe mehanizam koji automatski gasi PWM signale ukoliko mrežna komunikacija kasni više od 0.5 sekundi.

---

## ⚙️ Brzi Start (Deployment)

Za pokretanje servera na Raspberry Pi 5 uređaju:

```bash
# 1. Kloniranje projekta
git clone https://github.com/yoloprojekat/rpi-server.git

cd rpi-server

# 2. Build i pokretanje u pozadini
docker compose up --build -d

# 3. Provera logova u realnom vremenu
docker compose logs -f
```
### 🛠 Tehnološki Stack

Sistem je strukturiran u slojevima kako bi se osigurale maksimalne performanse na Raspberry Pi 5 hardveru uz potpunu izolaciju softverskih zavisnosti.

| Komponenta | Tehnologija | Uloga u Sistemu |
| :--- | :--- | :--- |
| **Virtualizacija** | **Docker** (Debian 13 Trixie) | Izolacija zavisnosti i $O(1)$ deployment |
| **Runtime** | **Python 3.13** (Asyncio) | Asinhrona orkestracija procesa i I/O operacija |
| **Video Engine** | **Picamera2** & **PyAV** | Nativni capture i procesiranje frejmova |
| **Streaming** | **WebRTC** (`aiortc`) | P2P video prenos ultra-niske latencije |
| **Kontrola** | **UDP Sockets** | Low-latency prenos komandi kretanja |
| **Hardware I/O** | **lgpio** / **gpiozero** | Precizna PWM i digitalna kontrola pinova |



---

### 🔌 Hardverska Mapa Pinova (BCM)

Konfiguracija pinova je optimizovana za **Raspberry Pi 5** i **L298N** motor drajvere. Za kontrolu se koristi BCM numeracija pinova.

#### 🕹️ Kontrola Brzine (PWM)
* **Global PWM (Enable A+B):** `GPIO 18` (Fizički Pin 12) — *Frekvencija: 50Hz*

#### ⚙️ Motorna Logika (Digital Output)
Ova tabela definiše parove pinova koji kontrolišu smer rotacije svakog od četiri motora.

| Pozicija Motora | Smer 1 (IN1/3) | Smer 2 (IN2/4) |
| :--- | :--- | :--- |
| **Prednji Levi (A)** | `GPIO 17` | `GPIO 27` |
| **Prednji Desni (B)** | `GPIO 22` | `GPIO 23` |
| **Zadnji Levi (C)** | `GPIO 24` | `GPIO 25` |
| **Zadnji Desni (D)** | `GPIO 5` | `GPIO 6` |



> [!IMPORTANT]
> **Napomena o uzemljenju:** Prilikom povezivanja, obavezno povežite **GND** (uzemljenje) L298N drajvera sa jednim od **GND** pinova na Raspberry Pi 5. Bez zajedničkog uzemljenja, PWM signal neće biti stabilan i motori mogu raditi nepredvidivo.
<div align="center">

Autor: Danilo Stoletović • Mentor: Dejan Batanjac

ETŠ „Nikola Tesla“ Niš • 2026

</div>
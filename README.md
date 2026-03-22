<div align="center">

# 🐳 Pametno Vozilo - Docker Kontrolni Server
### *Kontejnerizovan Backend za Raspberry Pi 5 (Debian 13 Trixie)*

---

<p align="center">
  <i>Edukativna platforma: Optimizovan mrežni gateway za hardversku orkestraciju, prilagođen studentima.</i>
</p>

[![Python](https://img.shields.io/badge/Python-3.13-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Deployment-Docker-2496ed?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Raspberry Pi](https://img.shields.io/badge/Hardware-RPi_5-c51a4a?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/)
[![HTTP](https://img.shields.io/badge/Stream-HTTP_MJPEG-0ea5e9?style=for-the-badge&logo=fastapi&logoColor=white)](https://en.wikipedia.org/wiki/Motion_JPEG)

</div>

## 🏗️ Docker Arhitektura i Benefiti

Implementacija Docker kontejnera na **Debian 13 (Trixie)** sistemu rešava kritične izazove embedded razvoja i donosi sledeće prednosti:

* **Izolacija Zavisnosti (No Dependency Hell):** Specifične verzije biblioteka za kameru i GPIO su izolovane od host sistema, sprečavajući pucanje aplikacije prilikom sistemskih ažuriranja.
* **Host OS Zaštita (PEP 668):** Debian 13 striktno štiti sistemski Python. Kontejner omogućava slobodnu instalaciju paketa bez narušavanja stabilnosti OS-a.
* **Deterministički Deployment:** Vreme potrebno za setup novog uređaja smanjeno je sa 45+ minuta na manje od 2 minuta povlačenjem gotovog image-a.
* **Direktan Hardverski Pristup:** Korišćenjem `privileged: true` i mapiranjem `/dev` particija, kontejner zadržava nativan pristup hardveru uz performanse identične direktnom izvršavanju.

---

## 🔄 Evolucija Arhitekture: Od WebRTC ka HTTP Stream-u

Tokom razvoja, doneta je svesna odluka o prelasku sa WebRTC na **HTTP MJPEG Stream**. Primećeno je da je WebRTC u ovom kontekstu bio **"overengineering"** koji je otežavao učenje studentima koji koriste ovu edukativnu platformu.

**Zašto HTTP Stream?**
1. **Jednostavnost:** Protokol je čist i razumljiv, što je ključno za edukativnu platformu.
2. **Lakši Debugging:** Video feed je dostupan direktno u browseru bez kompleksne signalizacije.
3. **Manje Opterećenje:** Uklanjanjem WebRTC stack-a, oslobođeni su resursi procesora za bržu obradu komandi kretanja.
---

## 🚀 Ključni Moduli

### 🛰️ Komunikacija
* **UDP Command Center:** Zadržan kao najbrži način za slanje komandi kretanja na portu `1606`. Optimizovano za kontrolu u realnom vremenu.
* **HTTP Video Server:** Streamer na portu `1607`. Koristi `multipart/x-mixed-replace` standard za prenos frejmova direktno sa kamere.

### 📸 Vision & Safety
* **Shared Camera Track:** Arhitektura omogućava da više klijenata istovremeno prati strim bez dupliranja opterećenja na procesoru.
* **Motor Watchdog:** Sigurnosni mehanizam koji automatski zaustavlja PWM signale ako mrežna komunikacija kasni više od 0.5 sekundi (fail-safe).

---

## 🛠 Tehnološki Stack

Sistem je strukturiran tako da osigura maksimalne performanse na RPi 5 hardveru uz potpunu izolaciju softvera.

| Komponenta | Tehnologija | Uloga u Sistemu |
| :--- | :--- | :--- |
| **Virtualizacija** | **Docker** (Debian 13) | Izolacija zavisnosti i instant deployment |
| **Runtime** | **Python 3.13** | Glavni mozak sistema (asinhrono izvršavanje) |
| **Video Engine** | **Picamera2** | Direktna kontrola RPi 5 kamere |
| **Streaming** | **HTTP MJPEG** | Jednostavan i robustan video prenos |
| **Kontrola** | **UDP Sockets** | Prenos komandi kretanja bez zastoja |
| **Hardware I/O** | **lgpio** | Precizna PWM kontrola motora na RPi 5 |

---

## 🔌 Hardverska Mapa Pinova (BCM)

Konfiguracija pinova je optimizovana za **Raspberry Pi 5** i **L298N** motor drajvere.

### 🕹️ Kontrola Brzine (PWM)
* **Global PWM (Enable A+B):** `GPIO 18` (Fizički Pin 12) — *Frekvencija: 50Hz*

### ⚙️ Motorna Logika (Digital Output)
Definiše pinove koji kontrolišu smer rotacije četiri motora.

| Pozicija Motora | Smer 1 (IN1/3) | Smer 2 (IN2/4) |
| :--- | :--- | :--- |
| **Prednji Levi (A)** | `GPIO 17` | `GPIO 27` |
| **Prednji Desni (B)** | `GPIO 22` | `GPIO 23` |
| **Zadnji Levi (C)** | `GPIO 24` | `GPIO 25` |
| **Zadnji Desni (D)** | `GPIO 5` | `GPIO 6` |

---

> [!IMPORTANT]
> **Napomena o uzemljenju:** Prilikom povezivanja, obavezno povežite **GND** (uzemljenje) L298N drajvera sa jednim od **GND** pinova na Raspberry Pi 5. Bez zajedničkog uzemljenja, kontrolni signali neće raditi ispravno i motori mogu postati nepredvidivi.

---

<div align="center">

Autor: **Danilo Stoletović** • Mentor: **Dejan Batanjac**
**ETŠ „Nikola Tesla“ Niš • 2026**

</div>

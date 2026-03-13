import asyncio
import logging
import time
import sys
import cv2
import numpy as np
from aiohttp import web
import aiohttp_cors
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from picamera2 import Picamera2

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RPI-HTTP-STREAM")

# --- HARDWARE SETUP ---
try:
    factory = LGPIOFactory()
    # Speed Control (Enable Pin) - Global PWM na GPIO 18
    ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
    
    # Motor Logic Pins (BCM mapiranje prema tabeli iz README)
    # Redosled: A1, A2, B1, B2, C1, C2, D1, D2
    motor_pins = [DigitalOutputDevice(p, pin_factory=factory) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
except Exception as e:
    logger.error(f"Hardware initialization failed: {e}")
    sys.exit(1)

# --- SHARED STATE ---
LAST_CMD_TIME = 0.0
LATEST_FRAME = None
FRAME_EVENT = asyncio.Event()

# --- CAMERA & STREAMING LOGIC ---
async def camera_loop(picam2):
    """Hvata frejmove sa kamere i enkoduje ih u JPEG za stream."""
    global LATEST_FRAME
    loop = asyncio.get_running_loop()
    while True:
        try:
            # Hvatanje RGB slike sa kamere
            raw_frame = await loop.run_in_executor(None, picam2.capture_array, "main")
            
            # Konverzija u JPEG format
            success, buffer = cv2.imencode('.jpg', cv2.cvtColor(raw_frame, cv2.COLOR_RGB2BGR))
            if success:
                LATEST_FRAME = buffer.tobytes()
                FRAME_EVENT.set()
                FRAME_EVENT.clear()
            
            await asyncio.sleep(0.04)  # ~25 FPS balans performansi i latencije
        except Exception as e:
            logger.error(f"Camera Error: {e}")
            await asyncio.sleep(1)

async def video_feed(request):
    """HTTP endpoint koji servira MJPEG stream."""
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)

    logger.info("Novi klijent povezan na video stream.")
    try:
        while True:
            await FRAME_EVENT.wait()
            if LATEST_FRAME:
                # MJPEG standardni format frejma
                frame_data = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + LATEST_FRAME + b'\r\n'
                )
                await response.write(frame_data)
    except Exception as e:
        logger.info(f"Klijent prekinuo stream: {e}")
    return response

# --- MOTOR CONTROL & WATCHDOG ---
async def handle_commands(request):
    """UDP (ili u ovom slučaju HTTP) komandni endpoint."""
    global LAST_CMD_TIME
    data = await request.json()
    # Logika kretanja ovde (npr. motor_pins[0].on(), itd.)
    LAST_CMD_TIME = time.time()
    return web.json_response({"status": "ok"})

async def watchdog():
    """Gasi motore ako komanda ne stigne na vreme."""
    while True:
        if ENABCD.value > 0 and (time.time() - LAST_CMD_TIME > 0.5):
            logger.warning("Watchdog: Sigurnosno zaustavljanje zbog gubitka signala.")
            ENABCD.value = 0
            for pin in motor_pins:
                pin.off()
        await asyncio.sleep(0.1)

# --- MAIN ENTRY ---
async def main():
    # Inicijalizacija kamere (RPi 5 optimizacija)
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(config)
    picam2.start()

    # Pokretanje pozadinskih zadataka
    asyncio.create_task(camera_loop(picam2))
    asyncio.create_task(watchdog())

    # Web Server podešavanje
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

    # Rute
    app.router.add_get('/video_feed', video_feed)
    app.router.add_post('/control', handle_commands)
    
    # Dodavanje CORS-a na rute
    for route in list(app.router.routes()):
        cors.add(route)

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Pokretanje servera na portu 1607
    site = web.TCPSite(runner, "0.0.0.0", 1607)
    await site.start()

    logger.info("------------------------------------------")
    logger.info("RPI-SERVER [Debian 13] Online!")
    logger.info("Video Stream: http://<RPi_IP_Adresa>:1607/video_feed")
    logger.info("------------------------------------------")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server ugašen.")
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
    # Speed Control (Enable Pin) - Global PWM on GPIO 18
    ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
    
    # Motor Logic Pins (BCM mapping)
    # Order: A1, A2, B1, B2, C1, C2, D1, D2
    motor_pins = [DigitalOutputDevice(p, pin_factory=factory) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
except Exception as e:
    logger.error(f"Hardware initialization failed: {e}")
    sys.exit(1)

# --- SHARED STATE ---
LAST_CMD_TIME = 0.0
LATEST_FRAME = b''
# Use Condition instead of Event to safely broadcast to multiple clients
FRAME_COND = asyncio.Condition() 

# --- CAMERA & STREAMING LOGIC ---
def capture_and_encode(picam2: Picamera2) -> bytes | None:
    """Synchronous function to handle CPU-bound image processing."""
    try:
        raw_frame = picam2.capture_array("main")
        # Convert and encode
        success, buffer = cv2.imencode('.jpg', cv2.cvtColor(raw_frame, cv2.COLOR_RGB2BGR))
        if success:
            return buffer.tobytes()
    except Exception as e:
        logger.error(f"Encoding Error: {e}")
    return None

async def camera_loop(picam2: Picamera2):
    """Captures frames from the camera and safely broadcasts them."""
    global LATEST_FRAME
    while True:
        try:
            # Offload blocking capture and encode to a separate thread
            frame_bytes = await asyncio.to_thread(capture_and_encode, picam2)
            
            if frame_bytes:
                async with FRAME_COND:
                    LATEST_FRAME = frame_bytes
                    FRAME_COND.notify_all() # Notify all connected clients at once
            
            await asyncio.sleep(0.04)  # ~25 FPS pacing
        except Exception as e:
            logger.error(f"Camera Loop Error: {e}")
            await asyncio.sleep(1)

async def video_feed(request: web.Request):
    """HTTP endpoint serving the MJPEG stream."""
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
            'Cache-Control': 'no-cache, private',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)

    logger.info(f"Novi klijent povezan na video stream: {request.remote}")
    try:
        while True:
            async with FRAME_COND:
                await FRAME_COND.wait() # Wait for the next frame signal
                frame = LATEST_FRAME
            
            if frame:
                frame_data = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
                await response.write(frame_data)
    except (ConnectionResetError, BrokenPipeError, aiohttp.web.ClientDisconnectedError):
        # Gracefully handle normal client disconnections
        logger.info(f"Klijent {request.remote} prekinuo stream.")
    except Exception as e:
        logger.error(f"Stream error for {request.remote}: {e}")
    
    return response

# --- MOTOR CONTROL & WATCHDOG ---
async def handle_commands(request: web.Request):
    """HTTP command endpoint for motor control."""
    global LAST_CMD_TIME
    try:
        data = await request.json()
        # Logika kretanja ovde (npr. motor_pins[0].on(), itd.)
        
        LAST_CMD_TIME = time.time()
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Error handling command: {e}")
        return web.json_response({"error": "Bad Request"}, status=400)

async def watchdog():
    """Shuts down motors if a command isn't received in time."""
    while True:
        # Check if motors are active AND time has expired
        if ENABCD.value > 0 and (time.time() - LAST_CMD_TIME > 0.5):
            logger.warning("Watchdog: Sigurnosno zaustavljanje zbog gubitka signala.")
            ENABCD.value = 0
            for pin in motor_pins:
                pin.off()
        await asyncio.sleep(0.1)

# --- MAIN ENTRY ---
async def main():
    # Camera Initialization
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(config)
    picam2.start()

    # Start background tasks
    asyncio.create_task(camera_loop(picam2))
    asyncio.create_task(watchdog())

    # Web Server setup
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

    # Routes
    app.router.add_get('/video_feed', video_feed)
    app.router.add_post('/control', handle_commands)
    
    # Apply CORS
    for route in list(app.router.routes()):
        cors.add(route)

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Start server
    site = web.TCPSite(runner, "0.0.0.0", 1607)
    await site.start()

    logger.info("------------------------------------------")
    logger.info("RPI-SERVER [Debian 13] Online!")
    logger.info("Video Stream: http://<RPi_IP_Adresa>:1607/video_feed")
    logger.info("------------------------------------------")
    
    # Keep the server running infinitely
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server ugašen od strane korisnika.")
    finally:
        # Ensure hardware safely turns off upon exit
        try:
            ENABCD.value = 0
            for pin in motor_pins:
                pin.off()
            factory.close()
        except NameError:
            pass
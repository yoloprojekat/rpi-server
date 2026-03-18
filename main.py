import asyncio
import logging
import time
import sys
import aiohttp
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
LAST_CMD_TIME = time.monotonic()
LATEST_FRAME = b''
FRAME_COND = asyncio.Condition() 

# --- MOVEMENT LOGIC & CONSTANTS ---
SPEED_NORMAL = 0.3
SPEED_ROTATION = 0.15

MOVEMENTS = {
    "napred":    (1, 1, 1, 1),
    "nazad":     (-1, -1, -1, -1),
    "levo":      (-1, 1, -1, 1),
    "desno":     (1, -1, 1, -1),
    "rot_levo":  (-1, -1, 1, 1),
    "rot_desno": (1, 1, -1, -1),
    "stop":      (0, 0, 0, 0),
}

ROTATION_CMDS = frozenset(["rot_levo", "rot_desno"])

def set_motor_state(in1, in2, state):
    if state == 1: 
        in1.on()
        in2.off()
    elif state == -1: 
        in1.off()
        in2.on()
    else: 
        in1.off()
        in2.off()

def stop_motors():
    ENABCD.value = 0
    for pin in motor_pins: 
        pin.off()

def execute_move(states, duty_cycle=SPEED_NORMAL):
    ENABCD.value = duty_cycle
    for i, state in enumerate(states):
        set_motor_state(motor_pins[i * 2], motor_pins[i * 2 + 1], state)

# --- CAMERA & STREAMING LOGIC ---
def capture_and_encode(picam2: Picamera2) -> bytes | None:
    """Synchronous function. Uses hardware MJPEG stream to bypass CPU encoding."""
    try:
        # We fetch the frame from the 'main' stream which is configured as MJPEG.
        # It is ALREADY a compressed JPEG byte string, so we skip OpenCV entirely!
        frame_data = picam2.capture_array("main")
        return frame_data.tobytes()
    except Exception as e:
        logger.error(f"Hardware Encoding Error: {e}")
    return None

async def camera_loop(picam2: Picamera2):
    """Captures frames from the camera and safely broadcasts them."""
    global LATEST_FRAME
    while True:
        try:
            # Offload blocking capture to a separate thread
            frame_bytes = await asyncio.to_thread(capture_and_encode, picam2)
            
            if frame_bytes:
                async with FRAME_COND:
                    LATEST_FRAME = frame_bytes
                    FRAME_COND.notify_all() # Notify all connected clients at once
            
            # 0.033 seconds = ~30 FPS pacing
            await asyncio.sleep(0.033)  
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
    except (ConnectionResetError, BrokenPipeError, aiohttp.ClientDisconnectedError):
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
        cmd = data.get("cmd", "stop").lower()
        
        LAST_CMD_TIME = time.monotonic()
        logger.debug(f"Primljena komanda: {cmd}")
        
        if cmd == "stop":
            stop_motors()
        elif cmd in MOVEMENTS:
            speed = SPEED_ROTATION if cmd in ROTATION_CMDS else SPEED_NORMAL
            execute_move(MOVEMENTS[cmd], duty_cycle=speed)
        else:
            logger.warning(f"Unknown command received: {cmd}")
            stop_motors()
        
        return web.json_response({"status": "ok", "cmd": cmd})
    except Exception as e:
        logger.error(f"Error handling command: {e}")
        return web.json_response({"error": "Bad Request"}, status=400)

async def watchdog():
    """Shuts down motors if a command isn't received in time."""
    while True:
        # Check if motors are active AND time has expired (2.0s for D-Pad compatibility)
        if ENABCD.value > 0 and (time.monotonic() - LAST_CMD_TIME > 2.0):
            logger.warning("Watchdog: Sigurnosno zaustavljanje zbog gubitka signala.")
            stop_motors()
        await asyncio.sleep(0.1)

# --- MAIN ENTRY ---
async def main():
    # Hardware Accelerated Camera Initialization
    picam2 = Picamera2()
    # Set format to MJPEG so the Pi 5 ISP handles the compression, not the CPU.
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "MJPEG"})
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
    logger.info("Video Stream: http://pametno-vozilo.local:1607/video_feed")
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
            stop_motors()
            factory.close()
        except NameError:
            pass
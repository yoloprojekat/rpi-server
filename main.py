import asyncio
import logging
import time
import sys
import io
import aiohttp
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError
import aiohttp_cors
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RPI-HTTP-STREAM")

# --- HARDWARE SETUP ---
try:
    factory = LGPIOFactory()
    # Speed Control (Enable Pin) - Global PWM on GPIO 18
    ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
    
    # Motor Logic Pins (BCM mapping)
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

# --- CAMERA HARDWARE CALLBACK ---
class AsyncStreamingOutput(io.BufferedIOBase):
    """
    This class catches the hardware-encoded JPEG bytes from the Pi 5's encoder 
    (which runs in a C++ background thread) and bridges them into our Python asyncio loop.
    """
    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def write(self, buf):
        global LATEST_FRAME
        LATEST_FRAME = bytes(buf)
        # Fire a thread-safe signal to the asyncio loop to wake up all connected phones
        asyncio.run_coroutine_threadsafe(self._notify(), self.loop)
        return len(buf)

    async def _notify(self):
        async with FRAME_COND:
            FRAME_COND.notify_all()

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
                await FRAME_COND.wait() # Wait for the hardware interrupt signal
                frame = LATEST_FRAME
            
            if frame:
                frame_data = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
                await response.write(frame_data)
    except (ConnectionResetError, BrokenPipeError, ClientConnectionResetError):
        # Gracefully handle normal client disconnections (like Docker healthchecks and app minimizations)
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
        if ENABCD.value > 0 and (time.monotonic() - LAST_CMD_TIME > 2.0):
            logger.warning("Watchdog: Sigurnosno zaustavljanje zbog gubitka signala.")
            stop_motors()
        await asyncio.sleep(0.1)

# --- MAIN ENTRY ---
async def main():
    loop = asyncio.get_running_loop()

    # Hardware Accelerated Camera Initialization
    picam2 = Picamera2()
    
    # 1. Let the ISP configure the optimal raw stream for 640x480
    config = picam2.create_video_configuration(main={"size": (640, 480)})
    picam2.configure(config)
    picam2.start()

    # 2. Attach the separate hardware MJPEG encoder and pipe it to our async output
    stream_output = AsyncStreamingOutput(loop)
    picam2.start_recording(MJPEGEncoder(), FileOutput(stream_output))

    # Start background tasks
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
    logger.info("RPI-SERVER [Debian 12] Online! (Hardware Accelerated)")
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
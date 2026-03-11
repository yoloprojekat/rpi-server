import asyncio
import logging
import time
import sys
from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from picamera2 import Picamera2

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RPI-STABLE")

# --- HARDWARE SETUP ---
try:
    factory = LGPIOFactory()
    # Speed Control (Enable Pin)
    ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
    # Motor Logic Pins (17, 27, 22, 23, 24, 25, 5, 6)
    motor_pins = [DigitalOutputDevice(p, pin_factory=factory) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
except Exception as e:
    logger.error(f"Hardware initialization failed: {e}")
    sys.exit(1)

# --- SHARED STATE ---
LAST_CMD_TIME = 0.0
LATEST_FRAME = None
FRAME_EVENT = asyncio.Event()

# --- WEBRTC TRACK ---
class SharedCameraTrack(VideoStreamTrack):
    async def recv(self):
        pts, time_base = await self.next_timestamp()
        await FRAME_EVENT.wait()
        if LATEST_FRAME is None:
            return None
        frame = VideoFrame.from_ndarray(LATEST_FRAME, format="rgb24")
        frame.pts, frame.time_base = pts, time_base
        return frame

# --- BACKGROUND TASKS ---
async def camera_loop(picam2):
    global LATEST_FRAME
    loop = asyncio.get_running_loop()
    while True:
        try:
            LATEST_FRAME = await loop.run_in_executor(None, picam2.capture_array, "main")
            FRAME_EVENT.set()
            FRAME_EVENT.clear()
            await asyncio.sleep(0.033) # ~30 FPS
        except Exception as e:
            logger.error(f"Camera Error: {e}")
            await asyncio.sleep(1)

async def watchdog():
    while True:
        if ENABCD.value > 0 and (time.time() - LAST_CMD_TIME > 0.5):
            logger.warning("Watchdog: Stopping motors due to timeout.")
            ENABCD.value = 0
            for pin in motor_pins: pin.off()
        await asyncio.sleep(0.1)

# --- WEBRTC SIGNALING ---
async def rtc_offer(request):
    params = await request.json()
    pc = RTCPeerConnection()
    pc.addTrack(SharedCameraTrack())
    await pc.setRemoteDescription(RTCSessionDescription(sdp=params["sdp"], type=params["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

# --- MAIN ENTRY ---
async def main():
    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"}))
    picam2.start()

    asyncio.create_task(camera_loop(picam2))
    asyncio.create_task(watchdog())

    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*")})
    cors.add(app.router.add_post("/offer", rtc_offer))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 1607).start()

    logger.info("RPI-SERVER [Debian 13 Stable] Online.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
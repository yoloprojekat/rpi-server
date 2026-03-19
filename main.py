import asyncio
import logging
import time
import sys
import cv2
import numpy as np
import aiohttp
from aiohttp import web
import aiohttp_cors
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from picamera2 import Picamera2
from ultralytics import YOLO

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RPI-YOLO-SERVER")

# --- HARDWARE SETUP ---
try:
    factory = LGPIOFactory()
    # Speed Control (Enable Pin) - Global PWM on GPIO 18
    ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
    
    # Motor Logic Pins: A1, A2, B1, B2, C1, C2, D1, D2
    motor_pins = [DigitalOutputDevice(p, pin_factory=factory) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
except Exception as e:
    logger.error(f"Hardware initialization failed: {e}")
    sys.exit(1)

# --- SHARED STATE (INITIALIZED) ---
LAST_CMD_TIME = 0.0
LATEST_FRAME = b''           # Raw JPEG bytes for streaming
DETECTION_RESULTS = None     # Shared YOLO boxes
FRAME_COND = asyncio.Condition() 
FRAME_COUNT = 0  # Add this to track frames for throttling

IS_DETECTION_ON = False      # Toggle for drawing boxes/names
IS_FOLLOW_ON = False         # Toggle for motor movement
IS_YOLO_RUNNING = False      # Master toggle (Legacy support)

# --- YOLO SETUP ---
try:
    # Loading YOLOv26 (NMS-Free optimized)
    model = YOLO("yolo26n.pt") 
    logger.info("YOLOv26 Model Loaded Successfully.")
except Exception as e:
    logger.error(f"Failed to load YOLO model: {e}")

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
        in1.on(); in2.off()
    elif state == -1: 
        in1.off(); in2.on()
    else: 
        in1.off(); in2.off()

def stop_motors():
    ENABCD.value = 0
    for pin in motor_pins: pin.off()

def execute_move(states, duty_cycle=SPEED_NORMAL):
    ENABCD.value = duty_cycle
    for i, state in enumerate(states):
        set_motor_state(motor_pins[i * 2], motor_pins[i * 2 + 1], state)

# --- YOLO DETECTION & FOLLOW LOOP ---
async def yolo_detection_loop():
    global IS_DETECTION_ON, IS_FOLLOW_ON, DETECTION_RESULTS, LAST_CMD_TIME
    logger.info("YOLO Detection Loop Ready.")
    
    while True:
        # If both AI features are off, idle to save CPU
        if not IS_DETECTION_ON and not IS_FOLLOW_ON:
            DETECTION_RESULTS = None
            await asyncio.sleep(0.5)
            continue

        if LATEST_FRAME:
            # Inference on the latest camera frame
            nparr = np.frombuffer(LATEST_FRAME, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is not None:
                results = model.predict(img, conf=0.4, verbose=False)
                # Store results for the drawing function (capture_and_encode)
                DETECTION_RESULTS = results[0].boxes if len(results) > 0 else None
                
                # ONLY execute movement if following is enabled
                if IS_FOLLOW_ON and DETECTION_RESULTS is not None:
                    # Steering logic (30% dead zone: 0.35 to 0.65)
                    box = DETECTION_RESULTS[0].xyxy[0].cpu().numpy()
                    center_x = (box[0] + box[2]) / 2 / img.shape[1]
                    
                    if center_x < 0.35: cmd = "levo"
                    elif center_x > 0.65: cmd = "desno"
                    else: cmd = "napred"
                    
                    execute_move(MOVEMENTS[cmd])
                    LAST_CMD_TIME = time.time()
                elif IS_FOLLOW_ON and DETECTION_RESULTS is None:
                    stop_motors()

        await asyncio.sleep(0.05) # ~20 FPS pacing

# --- CAMERA & STREAMING LOGIC ---
def capture_and_encode(picam2: Picamera2) -> bytes | None:
    global DETECTION_RESULTS, IS_DETECTION_ON, FRAME_COUNT
    try:
        raw_frame = picam2.capture_array("main")
        img = cv2.cvtColor(raw_frame, cv2.COLOR_RGB2BGR)
        
        # Increment frame counter
        FRAME_COUNT = (FRAME_COUNT + 1) % 25 

        # ONLY DRAW 5 TIMES PER SECOND (Every 5th frame)
        # This keeps the video smooth but the AI overlay efficient
        if IS_DETECTION_ON and (FRAME_COUNT % 5 == 0):
            h, w, _ = img.shape
            # Draw Dead Zone Guides
            cv2.line(img, (int(w * 0.35), 0), (int(w * 0.35), h), (255, 255, 255), 1)
            cv2.line(img, (int(w * 0.65), 0), (int(w * 0.65), h), (255, 255, 255), 1)

            if DETECTION_RESULTS is not None:
                for box in DETECTION_RESULTS:
                    b = box.xyxy[0].cpu().numpy().astype(int)
                    label_name = model.names[int(box.cls[0])].upper()
                    # Draw Bounding Box
                    cv2.rectangle(img, (b[0], b[1]), (b[2], b[3]), (0, 255, 127), 2)
                    cv2.putText(img, label_name, (b[0], b[1] - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 127), 2)

        success, buffer = cv2.imencode('.jpg', img)
        if success: return buffer.tobytes()
    except Exception as e:
        logger.error(f"Encoding Error: {e}")
    return None

async def camera_loop(picam2: Picamera2):
    global LATEST_FRAME
    while True:
        try:
            frame_bytes = await asyncio.to_thread(capture_and_encode, picam2)
            if frame_bytes:
                async with FRAME_COND:
                    LATEST_FRAME = frame_bytes
                    FRAME_COND.notify_all()
            await asyncio.sleep(0.04)
        except Exception as e:
            logger.error(f"Camera Loop Error: {e}")
            await asyncio.sleep(1)

async def video_feed(request: web.Request):
    response = web.StreamResponse(status=200, reason='OK', headers={
        'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
        'Cache-Control': 'no-cache, private', 'Connection': 'keep-alive',
    })
    await response.prepare(request)
    try:
        while True:
            async with FRAME_COND:
                await FRAME_COND.wait()
                frame = LATEST_FRAME
            if frame:
                await response.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    except Exception: logger.info("Client disconnected from stream.")
    return response

# --- HTTP HANDLERS ---
async def handle_commands(request: web.Request):
    global LAST_CMD_TIME
    try:
        data = await request.json()
        cmd = data.get("cmd", "stop").lower()
        LAST_CMD_TIME = time.time()
        if cmd == "stop": stop_motors()
        elif cmd in MOVEMENTS:
            speed = SPEED_ROTATION if cmd in ROTATION_CMDS else SPEED_NORMAL
            execute_move(MOVEMENTS[cmd], duty_cycle=speed)
        return web.json_response({"status": "ok", "cmd": cmd})
    except Exception: return web.json_response({"error": "Bad Request"}, status=400)

async def toggle_detection(request: web.Request):
    global IS_DETECTION_ON
    try:
        data = await request.json()
        IS_DETECTION_ON = data.get("enable", False)
        logger.info(f"AI Vision Toggled: {IS_DETECTION_ON}")
        return web.json_response({"status": "success", "detection": IS_DETECTION_ON})
    except Exception as e:
        logger.error(f"JSON Decode Error: {e}")
        return web.json_response({"status": "error", "message": "Invalid JSON format"}, status=400)

async def toggle_follow(request: web.Request):
    global IS_FOLLOW_ON
    data = await request.json()
    IS_FOLLOW_ON = data.get("enable", False)
    if not IS_FOLLOW_ON: stop_motors()
    logger.info(f"AI Following Toggled: {IS_FOLLOW_ON}")
    return web.json_response({"follow": IS_FOLLOW_ON})

async def watchdog():
    while True:
        if ENABCD.value > 0 and (time.time() - LAST_CMD_TIME > 2.0):
            logger.warning("Watchdog: Safety stop triggered.")
            stop_motors()
        await asyncio.sleep(0.1)

# --- MAIN ENTRY ---
async def main():
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(config); picam2.start()

    asyncio.create_task(camera_loop(picam2))
    asyncio.create_task(yolo_detection_loop())
    asyncio.create_task(watchdog())

    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
    })

    # REGISTERING ROUTES
    app.router.add_get('/video_feed', video_feed)
    app.router.add_post('/control', handle_commands)
    app.router.add_post('/toggle_detection', toggle_detection)
    app.router.add_post('/toggle_follow', toggle_follow)
    
    for route in list(app.router.routes()): cors.add(route)

    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 1607).start()

    logger.info("------------------------------------------")
    logger.info("RPI-YOLO-SERVER Online (Port 1607)")
    logger.info("------------------------------------------")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    finally:
        stop_motors()
        factory.close()
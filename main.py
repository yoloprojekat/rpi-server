import asyncio
import logging
import os
import sys
import time
import cv2
import numpy as np
import aiohttp
from aiohttp import web
import aiohttp_cors

# --- OPTIONAL DEPENDENCY IMPORTS WITH ROBUST FALLBACKS ---
try:
    import torch
except ImportError:
    torch = None

try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    PWMOutputDevice = DigitalOutputDevice = LGPIOFactory = None

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("RPI-YOLO-SERVER")

SERVER_START_TIME = time.time()

# --- HARDWARE SETUP (Raspberry Pi 5 RP1 & Legacy Support) ---
class MockPin:
    """Mock pin device for local testing and non-GPIO environments."""
    def __init__(self, pin): self.pin = pin
    def on(self): pass
    def off(self): pass
    def close(self): pass

class MockPWM:
    """Mock PWM device for local testing and non-GPIO environments."""
    def __init__(self, pin, frequency=50):
        self.pin = pin
        self.frequency = frequency
        self.value = 0.0
    def close(self): pass

ENABCD = None
motor_pins = []
factory = None

def init_hardware():
    global ENABCD, motor_pins, factory
    if LGPIOFactory is None or PWMOutputDevice is None:
        logger.warning("gpiozero/lgpio not installed. Running with Mock GPIO hardware.")
        ENABCD = MockPWM(18)
        motor_pins = [MockPin(p) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
        return

    # Attempt RPi 5 controller (chip 4 = RP1 southbridge), fallback to chip 0, then default
    for chip_id in [4, 0, None]:
        try:
            if chip_id is not None:
                factory = LGPIOFactory(chip=chip_id)
                logger.info(f"Initialized LGPIOFactory on gpiochip{chip_id}")
            else:
                factory = LGPIOFactory()
                logger.info("Initialized default LGPIOFactory")

            ENABCD = PWMOutputDevice(18, frequency=50, pin_factory=factory)
            motor_pins = [DigitalOutputDevice(p, pin_factory=factory) for p in [17, 27, 22, 23, 24, 25, 5, 6]]
            logger.info("Hardware GPIO initialized successfully.")
            return
        except Exception as e:
            logger.warning(f"Failed initializing GPIO with chip={chip_id}: {e}")

    logger.error("All hardware GPIO initializations failed. Falling back to Mock GPIO.")
    ENABCD = MockPWM(18)
    motor_pins = [MockPin(p) for p in [17, 27, 22, 23, 24, 25, 5, 6]]

init_hardware()

# --- SERVER STATE ---
class ServerState:
    def __init__(self):
        self.last_cmd_time = 0.0
        self.raw_frame = None            # Clean BGR numpy frame (for YOLO & clean stream)
        self.stream_frame = b''          # Clean JPEG bytes
        self.ai_stream_frame = b''       # Annotated JPEG bytes (with boxes & deadzone lines)
        self.detections = []             # Decoupled detection data (bounding boxes, class, conf)
        self.is_detection_on = False     # Toggle for drawing boxes
        self.is_follow_on = False        # Toggle for motor movement
        self.frame_id = 0                # Monotonically increasing frame counter
        self.camera_ready = False
        self.yolo_ready = False
        self.condition = asyncio.Condition()

state = ServerState()

# --- YOLO SETUP ---
model = None
try:
    if YOLO is not None:
        model_path = os.getenv("YOLO_MODEL_PATH", "yolo26n.pt")
        model = YOLO(model_path)
        state.yolo_ready = True
        logger.info(f"YOLO Model ({model_path}) Loaded Successfully.")
    else:
        logger.warning("Ultralytics YOLO is not installed. AI features disabled.")
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

def set_motor_state(in1, in2, state_val):
    if state_val == 1:
        in1.on(); in2.off()
    elif state_val == -1:
        in1.off(); in2.on()
    else:
        in1.off(); in2.off()

def stop_motors():
    if ENABCD is not None:
        ENABCD.value = 0
    for pin in motor_pins:
        pin.off()

def is_motor_active():
    return ENABCD is not None and getattr(ENABCD, "value", 0) > 0

def execute_move(states, duty_cycle=SPEED_NORMAL):
    if ENABCD is not None:
        ENABCD.value = duty_cycle
    for i, s in enumerate(states):
        set_motor_state(motor_pins[i * 2], motor_pins[i * 2 + 1], s)

# --- YOLO INFERENCE WORKER (Runs off-thread to avoid blocking event loop) ---
def run_yolo_inference(img: np.ndarray, conf: float = 0.35) -> list[dict]:
    """
    Executes YOLO inference in a worker thread.
    Uses torch.inference_mode() to eliminate computational graph tracking,
    preventing memory leaks over long durations.
    Returns lightweight Python dictionaries instead of keeping PyTorch tensors in memory.
    """
    if model is None or img is None:
        return []

    try:
        if torch is not None:
            with torch.inference_mode():
                results = model.predict(img, conf=conf, verbose=False)
        else:
            results = model.predict(img, conf=conf, verbose=False)

        parsed_detections = []
        if len(results) > 0 and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy().astype(int).tolist()
                cls_id = int(boxes.cls[i].item())
                confidence = float(boxes.conf[i].item())
                class_name = model.names.get(cls_id, str(cls_id)).upper() if hasattr(model, "names") else str(cls_id)
                parsed_detections.append({
                    "box": xyxy,
                    "class_name": class_name,
                    "conf": confidence
                })
        return parsed_detections
    except Exception as e:
        logger.error(f"YOLO Inference Worker Error: {e}")
        return []

# --- YOLO DETECTION & FOLLOW LOOP ---
async def yolo_detection_loop():
    logger.info("YOLO Detection Loop Initialized.")

    while True:
        try:
            # Idle to save CPU if both AI features are off
            if not state.is_detection_on and not state.is_follow_on:
                state.detections = []
                await asyncio.sleep(0.2)
                continue

            # Work on a copy of the clean raw BGR frame (never with old bounding boxes drawn!)
            current_frame = None
            if state.raw_frame is not None:
                current_frame = state.raw_frame.copy()

            if current_frame is not None and model is not None:
                # Offload CPU-heavy inference to background thread pool
                detections = await asyncio.to_thread(run_yolo_inference, current_frame, 0.35)
                state.detections = detections

                # Autonomous Following Logic
                if state.is_follow_on:
                    if len(detections) > 0:
                        target = detections[0]
                        box = target["box"]
                        img_w = current_frame.shape[1]
                        center_x = (box[0] + box[2]) / (2.0 * img_w)

                        # Steering logic (30% dead zone: 0.35 to 0.65)
                        if center_x < 0.35:
                            cmd = "levo"
                        elif center_x > 0.65:
                            cmd = "desno"
                        else:
                            cmd = "napred"

                        speed = SPEED_ROTATION if cmd in ROTATION_CMDS else SPEED_NORMAL
                        execute_move(MOVEMENTS[cmd], duty_cycle=speed)
                        state.last_cmd_time = time.time()
                    else:
                        # Target lost: immediately stop motors to prevent runaway robot
                        stop_motors()

            await asyncio.sleep(0.05)  # ~20 FPS inference pacing

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Unexpected error in yolo_detection_loop: {e}", exc_info=True)
            await asyncio.sleep(0.5)

# --- CAMERA CAPTURE & ENCODING LOOP ---
def generate_fallback_frame(text="CAMERA OFFLINE") -> np.ndarray:
    """Generates a test frame when Picamera2 is unavailable."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, text, (140, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    return frame

def annotate_frame(img: np.ndarray, detections: list[dict]) -> bytes | None:
    """Renders zone boundaries and bounding boxes onto a frame copy."""
    try:
        annotated = img.copy()
        h, w = annotated.shape[:2]

        # Tracking zone guidelines (35% and 65%)
        cv2.line(annotated, (int(w * 0.35), 0), (int(w * 0.35), h), (255, 255, 255), 1)
        cv2.line(annotated, (int(w * 0.65), 0), (int(w * 0.65), h), (255, 255, 255), 1)

        for det in detections:
            box = det["box"]
            name = det["class_name"]
            conf = det["conf"]

            cv2.rectangle(annotated, (box[0], box[1]), (box[2], box[3]), (0, 255, 127), 2)
            label = f"{name} {conf:.2f}"
            cv2.putText(annotated, label, (box[0], max(box[1] - 5, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 127), 2)

        success, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes() if success else None
    except Exception as e:
        logger.error(f"Annotation error: {e}")
        return None

def capture_camera_frame(picam2: Picamera2 | None) -> np.ndarray:
    """Captures a native BGR888 frame from Picamera2 or fallback."""
    if picam2 is not None:
        try:
            return picam2.capture_array("main")
        except Exception as e:
            logger.error(f"Camera capture error: {e}")
    return generate_fallback_frame("WAITING FOR CAMERA")

async def camera_loop(picam2: Picamera2 | None):
    logger.info("Camera Stream Loop Initialized.")
    frame_throttle = 0

    while True:
        try:
            # Capture frame in thread pool to avoid blocking async loop
            raw_bgr = await asyncio.to_thread(capture_camera_frame, picam2)
            state.raw_frame = raw_bgr
            state.camera_ready = (picam2 is not None)

            # Encode clean JPEG stream
            success, clean_buf = cv2.imencode('.jpg', raw_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            clean_bytes = clean_buf.tobytes() if success else b''

            # Encode AI annotated frame if enabled (update annotation at ~10 FPS to save CPU)
            ai_bytes = b''
            if state.is_detection_on:
                frame_throttle = (frame_throttle + 1) % 3
                if frame_throttle == 0 or not state.ai_stream_frame:
                    ai_bytes = await asyncio.to_thread(annotate_frame, raw_bgr, state.detections)
                else:
                    ai_bytes = state.ai_stream_frame

            async with state.condition:
                state.stream_frame = clean_bytes
                if ai_bytes:
                    state.ai_stream_frame = ai_bytes
                state.frame_id += 1
                state.condition.notify_all()

            await asyncio.sleep(0.033)  # ~30 FPS capture rate

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Camera loop error: {e}")
            await asyncio.sleep(0.5)

# --- HTTP HANDLERS ---
async def video_feed(request: web.Request):
    """
    High-performance, zero-leak MJPEG stream handler with explicit backpressure.
    Uses await response.drain() to prevent unconstrained buffer accumulation in memory,
    which was the primary cause of OOM crashes after ~5 minutes.
    """
    response = web.StreamResponse(status=200, reason='OK', headers={
        'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
        'Cache-Control': 'no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
        'Connection': 'keep-alive',
    })
    await response.prepare(request)
    last_sent_frame_id = -1

    try:
        while True:
            async with state.condition:
                # Wait for next available camera frame
                await state.condition.wait()

                # Frame-drop mechanism: if consumer lagged, skip to latest frame
                if state.frame_id == last_sent_frame_id:
                    continue
                last_sent_frame_id = state.frame_id

                frame_bytes = state.ai_stream_frame if state.is_detection_on and state.ai_stream_frame else state.stream_frame

            if frame_bytes:
                header = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                )
                await response.write(header + frame_bytes + b'\r\n')
                # BACKPRESSURE CONTROL: Pause if write buffer is full until network transports flush
                await response.drain()

    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        logger.info("Client cleanly disconnected from video stream.")
    except Exception as e:
        logger.warning(f"Video feed exception: {e}")
    finally:
        try:
            await response.write_eof()
        except Exception:
            pass
    return response

async def handle_commands(request: web.Request):
    try:
        data = await request.json()
        cmd = data.get("cmd", "stop").lower()
        state.last_cmd_time = time.time()

        if cmd == "stop":
            stop_motors()
        elif cmd in MOVEMENTS:
            speed = SPEED_ROTATION if cmd in ROTATION_CMDS else SPEED_NORMAL
            execute_move(MOVEMENTS[cmd], duty_cycle=speed)
        else:
            return web.json_response({"error": f"Unknown command: {cmd}"}, status=400)

        return web.json_response({"status": "ok", "cmd": cmd})
    except Exception as e:
        logger.error(f"Command Error: {e}")
        return web.json_response({"error": "Bad Request"}, status=400)

async def toggle_detection(request: web.Request):
    try:
        data = await request.json()
        state.is_detection_on = bool(data.get("enable", False))
        if not state.is_detection_on:
            state.detections = []
            state.ai_stream_frame = b''
        logger.info(f"AI Vision Toggled: {state.is_detection_on}")
        return web.json_response({"status": "success", "detection": state.is_detection_on})
    except Exception as e:
        logger.error(f"Detection toggle error: {e}")
        return web.json_response({"error": "Invalid JSON format"}, status=400)

async def toggle_follow(request: web.Request):
    try:
        data = await request.json()
        state.is_follow_on = bool(data.get("enable", False))
        if not state.is_follow_on:
            stop_motors()
        logger.info(f"AI Following Toggled: {state.is_follow_on}")
        return web.json_response({"status": "success", "follow": state.is_follow_on})
    except Exception as e:
        logger.error(f"Follow toggle error: {e}")
        return web.json_response({"error": "Invalid JSON format"}, status=400)

async def health_check(request: web.Request):
    """Dedicated lightweight healthcheck endpoint for Docker and monitoring."""
    uptime = time.time() - SERVER_START_TIME
    return web.json_response({
        "status": "ok",
        "camera_active": state.camera_ready,
        "yolo_active": state.yolo_ready,
        "detection_enabled": state.is_detection_on,
        "follow_enabled": state.is_follow_on,
        "uptime_seconds": round(uptime, 1)
    })

# --- WATCHDOG ---
async def watchdog():
    """Safety watchdog: automatically halts motors if no command received for 2 seconds."""
    logger.info("Motor Safety Watchdog Active.")
    while True:
        try:
            if is_motor_active() and (time.time() - state.last_cmd_time > 2.0):
                logger.warning("Watchdog: Safety timeout exceeded (>2s). Stopping motors.")
                stop_motors()
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Watchdog error: {e}")
            await asyncio.sleep(0.5)

# --- MAIN ENTRY ---
async def main():
    picam2 = None
    if Picamera2 is not None:
        try:
            picam2 = Picamera2()
            # Configure native BGR888 format directly (eliminates per-frame cvtColor CPU overhead)
            config = picam2.create_video_configuration(main={"size": (640, 480), "format": "BGR888"})
            picam2.configure(config)
            picam2.start()
            logger.info("Picamera2 started successfully in BGR888 mode.")
        except Exception as e:
            logger.warning(f"Picamera2 init failed (will use fallback frames): {e}")
            picam2 = None
    else:
        logger.warning("Picamera2 not installed. Using fallback video stream.")

    # Background Tasks
    camera_task = asyncio.create_task(camera_loop(picam2))
    yolo_task = asyncio.create_task(yolo_detection_loop())
    watchdog_task = asyncio.create_task(watchdog())

    # Web Application & Routing
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
    })

    app.router.add_get('/health', health_check)
    app.router.add_get('/video_feed', video_feed)
    app.router.add_post('/control', handle_commands)
    app.router.add_post('/toggle_detection', toggle_detection)
    app.router.add_post('/toggle_follow', toggle_follow)

    for route in list(app.router.routes()):
        cors.add(route)

    # AppRunner with 5-minute keepalive timeout for persistent streaming
    runner = web.AppRunner(app, keepalive_timeout=300.0)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 1607)
    await site.start()

    logger.info("==========================================")
    logger.info("RPI-YOLO-SERVER Online (Port 1607)")
    logger.info("Health Check: http://localhost:1607/health")
    logger.info("Video Stream: http://localhost:1607/video_feed")
    logger.info("==========================================")

    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Shutting down server tasks...")
        camera_task.cancel()
        yolo_task.cancel()
        watchdog_task.cancel()
        stop_motors()
        if picam2 is not None:
            try: picam2.stop()
            except Exception: pass
        if factory is not None:
            try: factory.close()
            except Exception: pass
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server terminated by user (KeyboardInterrupt).")
    finally:
        stop_motors()
        if factory is not None:
            try: factory.close()
            except Exception: pass
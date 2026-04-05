from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time
import threading
import requests
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

print("=" * 55)
print("HIDESPEC - AUTO-SAVE CAMERA STREAM SERVER")
print("YOLOv8n Detection with Pi Camera Module 3")
print("=" * 55)

# ============================================
# LOW-LAG SETTINGS
# ============================================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

YOLO_IMGSZ = 224
YOLO_CONF = 0.25
DETECT_EVERY_N_FRAMES = 5

JPEG_QUALITY = 50
TARGET_FPS = 8
FRAME_DELAY = 1.0 / TARGET_FPS

# ============================================
# AUTO-SAVE SETTINGS
# ============================================
API_BASE_URL = "http://127.0.0.1:5000"
INSPECTIONS_API_URL = f"{API_BASE_URL}/api/inspections"

AUTO_SAVE_ENABLED = True
AUTO_SAVE_COOLDOWN_SECONDS = 5
SAVE_SNAPSHOT_ON_DETECTION = True

BASE_DIR = Path(__file__).resolve().parent
CAPTURES_DIR = BASE_DIR / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

print("\nLoading YOLO model...")
model = YOLO("best.pt")
print("Model loaded: best.pt")
print(f"Classes: {model.names}")

print("Starting camera...")
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"},
    buffer_count=2
)
picam2.configure(config)
picam2.start()
time.sleep(2)
print(f"Camera started: {FRAME_WIDTH}x{FRAME_HEIGHT}")
print("Capture loop started.\n")

last_raw_frame = None
last_annotated = None
last_detections = []
frame_counter = 0

last_inference_ms = 0.0
last_encode_ms = 0.0
stream_fps = 0.0
last_stream_time = time.time()

last_auto_save_time = 0.0
last_saved_hide_id = None

state_lock = threading.Lock()


def make_hide_id():
    return f"HIDE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def save_local_snapshot(frame_bgr, hide_id):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{hide_id}_{timestamp}.jpg"
    file_path = CAPTURES_DIR / filename

    ok = cv2.imwrite(str(file_path), frame_bgr)
    if ok:
        return str(file_path)
    return None


def post_inspection_record(hide_id, detections, snapshot_path=None):
    payload = {
        "hide_id": hide_id,
        "defects": detections,
        "snapshot_path": snapshot_path,
    }

    try:
        response = requests.post(
            INSPECTIONS_API_URL,
            json=payload,
            timeout=3
        )
        if response.ok:
            print(f"[AUTO-SAVE] Inspection saved: {hide_id}")
            return True
        else:
            print(f"[AUTO-SAVE] Failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"[AUTO-SAVE] POST error: {e}")
        return False


def maybe_auto_save(frame_rgb, detections):
    global last_auto_save_time, last_saved_hide_id

    if not AUTO_SAVE_ENABLED:
        return

    if not detections:
        return

    now = time.time()
    if now - last_auto_save_time < AUTO_SAVE_COOLDOWN_SECONDS:
        return

    hide_id = make_hide_id()
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    snapshot_path = None
    if SAVE_SNAPSHOT_ON_DETECTION:
        snapshot_path = save_local_snapshot(frame_bgr, hide_id)

    ok = post_inspection_record(
        hide_id=hide_id,
        detections=detections,
        snapshot_path=snapshot_path
    )

    if ok:
        last_auto_save_time = now
        last_saved_hide_id = hide_id


def run_detection(frame):
    global last_detections, last_inference_ms

    start = time.time()
    results = model(frame, imgsz=YOLO_IMGSZ, conf=YOLO_CONF, verbose=False)
    last_inference_ms = round((time.time() - start) * 1000, 1)

    result = results[0]
    annotated = result.plot()

    detections = []
    boxes = result.boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            label = model.names.get(cls_id, str(cls_id))
            detections.append({
                "type": label,
                "label": label,
                "confidence": conf,
            })

    last_detections = detections
    return annotated, detections


def mjpeg_generator():
    global last_raw_frame, last_annotated, frame_counter
    global last_encode_ms, stream_fps, last_stream_time

    while True:
        loop_start = time.time()

        try:
            frame = picam2.capture_array()

            with state_lock:
                last_raw_frame = frame.copy()
                frame_counter += 1
                current_frame_number = frame_counter

            if last_annotated is None or current_frame_number % DETECT_EVERY_N_FRAMES == 0:
                annotated, detections = run_detection(frame)

                with state_lock:
                    last_annotated = annotated

                maybe_auto_save(frame, detections)

            else:
                with state_lock:
                    if last_annotated is None:
                        last_annotated = frame.copy()

            with state_lock:
                frame_to_send = last_annotated.copy()

            frame_bgr = cv2.cvtColor(frame_to_send, cv2.COLOR_RGB2BGR)

            encode_start = time.time()
            ok, buffer = cv2.imencode(
                ".jpg",
                frame_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            )
            last_encode_ms = round((time.time() - encode_start) * 1000, 1)

            if not ok:
                continue

            now = time.time()
            elapsed = now - last_stream_time
            if elapsed > 0:
                stream_fps = round(1.0 / elapsed, 1)
            last_stream_time = now

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

            loop_elapsed = time.time() - loop_start
            sleep_time = FRAME_DELAY - loop_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        except Exception as e:
            print(f"Stream error: {e}")
            time.sleep(0.05)


@app.route("/video_feed")
def video_feed():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/stream/status")
def stream_status():
    return jsonify({
        "status": "running",
        "resolution": f"{FRAME_WIDTH}x{FRAME_HEIGHT}",
        "detections": last_detections,
        "performance": {
            "detect_every_n_frames": DETECT_EVERY_N_FRAMES,
            "imgsz": YOLO_IMGSZ,
            "jpeg_quality": JPEG_QUALITY,
            "target_fps": TARGET_FPS,
            "actual_stream_fps": stream_fps,
            "last_inference_ms": last_inference_ms,
            "last_encode_ms": last_encode_ms,
        },
        "auto_save": {
            "enabled": AUTO_SAVE_ENABLED,
            "cooldown_seconds": AUTO_SAVE_COOLDOWN_SECONDS,
            "last_saved_hide_id": last_saved_hide_id,
        }
    })


@app.route("/api/stream/snapshot")
def snapshot():
    try:
        with state_lock:
            frame = last_raw_frame.copy() if last_raw_frame is not None else None

        if frame is None:
            frame = picam2.capture_array()

        annotated, _ = run_detection(frame)
        frame_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)

        ok, buffer = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        )
        if not ok:
            return ("Snapshot encode failed", 500)

        return Response(buffer.tobytes(), mimetype="image/jpeg")

    except Exception as e:
        return (f"Snapshot failed: {e}", 500)


@app.route("/")
def home():
    return f"""
    <html>
      <body style="text-align:center;background:#111;color:white;font-family:Arial">
        <h1>HideSpec Live Stream</h1>
        <p>
          Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT} |
          YOLO imgsz: {YOLO_IMGSZ} |
          Detect every: {DETECT_EVERY_N_FRAMES} frames |
          JPEG quality: {JPEG_QUALITY}
        </p>
        <p>
          Auto-save: {"ON" if AUTO_SAVE_ENABLED else "OFF"} |
          Cooldown: {AUTO_SAVE_COOLDOWN_SECONDS}s
        </p>
        <img src="/video_feed" width="900" style="max-width:100%;height:auto;border:1px solid #333;" />
      </body>
    </html>
    """


if __name__ == "__main__":
    print("Video stream: http://0.0.0.0:5001/video_feed")
    print("Stream status: http://0.0.0.0:5001/api/stream/status")
    print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
    print("\nLow-lag + auto-save settings:")
    print(f"- Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print(f"- YOLO imgsz: {YOLO_IMGSZ}")
    print(f"- Detect every: {DETECT_EVERY_N_FRAMES} frames")
    print(f"- JPEG quality: {JPEG_QUALITY}")
    print(f"- Target FPS: {TARGET_FPS}")
    print(f"- Auto-save: {AUTO_SAVE_ENABLED}")
    print(f"- Cooldown: {AUTO_SAVE_COOLDOWN_SECONDS}s")
    print(f"- API: {INSPECTIONS_API_URL}\n")

    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
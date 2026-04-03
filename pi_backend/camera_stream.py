from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time
import threading

app = Flask(__name__)

print("=" * 55)
print("HIDESPEC - LOW LATENCY CAMERA STREAM SERVER")
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

state_lock = threading.Lock()


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
    return annotated


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
                annotated = run_detection(frame)
                with state_lock:
                    last_annotated = annotated
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
    })


@app.route("/api/stream/snapshot")
def snapshot():
    try:
        with state_lock:
            frame = last_raw_frame.copy() if last_raw_frame is not None else None

        if frame is None:
            frame = picam2.capture_array()

        annotated = run_detection(frame)
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
        <img src="/video_feed" width="900" style="max-width:100%;height:auto;border:1px solid #333;" />
      </body>
    </html>
    """


if __name__ == "__main__":
    print("Video stream: http://0.0.0.0:5001/video_feed")
    print("Stream status: http://0.0.0.0:5001/api/stream/status")
    print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
    print("\nLow-lag settings:")
    print(f"- Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print(f"- YOLO imgsz: {YOLO_IMGSZ}")
    print(f"- Detect every: {DETECT_EVERY_N_FRAMES} frames")
    print(f"- JPEG quality: {JPEG_QUALITY}")
    print(f"- Target FPS: {TARGET_FPS}\n")

    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
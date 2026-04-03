"""
Live Camera Stream with YOLOv8n Detection Overlay
Runs on Raspberry Pi 5 with Pi Camera Module 3.
Streams MJPEG video with bounding boxes drawn on detected defects.

IMPORTANT: Uses Picamera2 (NOT cv2.VideoCapture) for Pi 5 Bookworm compatibility.

Install requirements:
    sudo apt install -y python3-picamera2 python3-libcamera
    pip install ultralytics flask flask-cors opencv-python-headless --break-system-packages

Run: python3 camera_stream.py
Stream: http://0.0.0.0:5001/video_feed
"""

from flask import Flask, Response, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import cv2
import threading
import time
import numpy as np

app = Flask(__name__)
CORS(app)

# ─── Configuration ────────────────────────────────────────────
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.5
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS_TARGET = 15

# Class names and colors (BGR for OpenCV)
CLASS_CONFIG = {
    0: {"name": "color_defect", "color": (62, 136, 240), "label": "Color Defect"},
    1: {"name": "fold", "color": (255, 166, 88), "label": "Fold"},
    2: {"name": "hole", "color": (73, 81, 248), "label": "Hole"},
}

# ─── Global State ─────────────────────────────────────────────
picam = None
model = None
current_frame = None
current_detections = []
frame_lock = threading.Lock()
is_running = False
detection_enabled = True
use_picamera2 = False


def initialize():
    """Load model and start camera using Picamera2."""
    global picam, model, is_running, use_picamera2

    print("Loading YOLOv8n model...")
    model = YOLO(MODEL_PATH)
    print(f"Model loaded: {MODEL_PATH}")
    print(f"Classes: {model.names}")

    # Try Picamera2 first (correct method for Pi 5 Bookworm)
    print("Starting camera with Picamera2...")
    try:
        from picamera2 import Picamera2
        picam = Picamera2()
        config = picam.create_preview_configuration(
            main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"}
        )
        picam.configure(config)
        picam.start()
        time.sleep(1)  # Let camera warm up
        use_picamera2 = True
        is_running = True
        print(f"Picamera2 started: {FRAME_WIDTH}x{FRAME_HEIGHT}")
        return True
    except ImportError:
        print("WARNING: picamera2 not installed. Run: sudo apt install python3-picamera2")
        print("Falling back to cv2.VideoCapture (may not work on Pi 5)...")
    except Exception as e:
        print(f"WARNING: Picamera2 failed: {e}")
        print("Falling back to cv2.VideoCapture...")

    # Fallback to OpenCV (works on laptops for testing, may fail on Pi 5)
    try:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            picam = cap  # Store as picam variable for unified access
            use_picamera2 = False
            is_running = True
            print(f"OpenCV camera started: {FRAME_WIDTH}x{FRAME_HEIGHT}")
            return True
        else:
            print("ERROR: OpenCV cannot open camera either!")
    except Exception as e:
        print(f"ERROR: OpenCV camera failed: {e}")

    # No camera available — use test frame mode
    print("No camera available. Running in TEST MODE with generated frames.")
    use_picamera2 = False
    is_running = True
    return False


def capture_frame():
    """Capture a single frame from whichever camera method is available."""
    global picam, use_picamera2

    if picam is None:
        return generate_test_frame()

    if use_picamera2:
        try:
            # Picamera2 returns RGB, OpenCV needs BGR
            frame = picam.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            return frame
        except Exception as e:
            print(f"Picamera2 capture error: {e}")
            return generate_test_frame()
    else:
        try:
            ret, frame = picam.read()
            if ret:
                return frame
        except:
            pass
        return generate_test_frame()


def draw_detections(frame, results):
    """Draw bounding boxes and labels on the frame."""
    detections = []

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue

        for box in boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if confidence < CONFIDENCE_THRESHOLD:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            config = CLASS_CONFIG.get(cls_id, {"name": "unknown", "color": (128, 128, 128), "label": "Unknown"})

            color = config["color"]

            # Draw bounding box with thicker line
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Draw filled label background
            label = f"{config['label']} {confidence:.0%}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), (x1 + label_size[0] + 6, y1), color, -1)

            # Draw label text (white on colored background)
            cv2.putText(frame, label, (x1 + 3, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            detections.append({
                "type": config["name"],
                "label": config["label"],
                "confidence": round(confidence, 2),
                "bbox": [x1, y1, x2 - x1, y2 - y1],
            })

    # Draw defect count overlay (top-left)
    count_text = f"Defects: {len(detections)}"
    cv2.putText(frame, count_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (62, 136, 240), 2, cv2.LINE_AA)

    # Draw timestamp (top-right)
    timestamp = time.strftime("%H:%M:%S")
    cv2.putText(frame, timestamp, (FRAME_WIDTH - 120, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)

    # Draw "LIVE" indicator with red dot (top-right area)
    cv2.circle(frame, (FRAME_WIDTH - 150, 27), 5, (0, 0, 255), -1)
    cv2.putText(frame, "LIVE", (FRAME_WIDTH - 140, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

    # Draw HideSpec watermark (bottom-right)
    cv2.putText(frame, "HideSpec", (FRAME_WIDTH - 100, FRAME_HEIGHT - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1, cv2.LINE_AA)

    return frame, detections


def capture_loop():
    """Continuously capture frames and run detection."""
    global current_frame, current_detections, is_running

    while is_running:
        frame = capture_frame()

        if frame is None:
            time.sleep(0.1)
            continue

        if detection_enabled and model is not None:
            results = model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
            frame, detections = draw_detections(frame, results)
        else:
            detections = []

        with frame_lock:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            current_frame = buffer.tobytes()
            current_detections = detections

        time.sleep(1.0 / FPS_TARGET)


def generate_test_frame():
    """Generate a test frame when no camera is available."""
    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
    frame[:] = (30, 25, 20)

    # Draw a fake leather hide rectangle
    cv2.rectangle(frame, (100, 80), (540, 400), (80, 120, 160), -1)
    cv2.rectangle(frame, (100, 80), (540, 400), (100, 140, 180), 2)

    # Add texture
    for i in range(100, 540, 15):
        for j in range(80, 400, 15):
            noise = np.random.randint(-8, 8)
            cv2.circle(frame, (i, j), 1, (80 + noise, 120 + noise, 160 + noise), -1)

    cv2.putText(frame, "TEST MODE - No Camera Connected", (110, 230),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, "Connect Pi Camera Module 3", (150, 260),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(frame, "sudo apt install python3-picamera2", (120, 290),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1, cv2.LINE_AA)

    return frame


def generate_frames():
    """Generator that yields MJPEG frames for streaming."""
    while True:
        with frame_lock:
            if current_frame is None:
                time.sleep(0.05)
                continue
            frame = current_frame

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        time.sleep(1.0 / FPS_TARGET)


# ─── Routes ───────────────────────────────────────────────────

@app.route('/video_feed')
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/stream/status')
def stream_status():
    """Returns current stream status and latest detections."""
    return jsonify({
        "streaming": is_running,
        "detection_enabled": detection_enabled,
        "resolution": f"{FRAME_WIDTH}x{FRAME_HEIGHT}",
        "fps_target": FPS_TARGET,
        "detections": current_detections,
        "model": MODEL_PATH,
        "camera_method": "Picamera2" if use_picamera2 else "OpenCV",
    })


@app.route('/api/stream/toggle_detection')
def toggle_detection():
    """Toggle detection overlay on/off."""
    global detection_enabled
    detection_enabled = not detection_enabled
    return jsonify({"detection_enabled": detection_enabled})


@app.route('/api/stream/snapshot')
def snapshot():
    """Returns a single JPEG snapshot."""
    with frame_lock:
        if current_frame is None:
            return jsonify({"error": "No frame available"}), 404
        return Response(current_frame, mimetype='image/jpeg')


# ─── Main ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print()
    print("=" * 55)
    print("  HIDESPEC — LIVE CAMERA STREAM SERVER")
    print("  YOLOv8n Detection with Pi Camera Module 3")
    print("=" * 55)
    print()

    cam_ok = initialize()

    if cam_ok:
        print(f"Camera method: {'Picamera2' if use_picamera2 else 'OpenCV'}")
    else:
        print("Running in TEST MODE (no camera)")

    # Start capture thread
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()
    print("Capture loop started.")

    print()
    print(f"  Video stream:  http://0.0.0.0:5001/video_feed")
    print(f"  Stream status: http://0.0.0.0:5001/api/stream/status")
    print(f"  Snapshot:      http://0.0.0.0:5001/api/stream/snapshot")
    print()
    print("  Open the video_feed URL in a browser to verify.")
    print("=" * 55)
    print()

    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

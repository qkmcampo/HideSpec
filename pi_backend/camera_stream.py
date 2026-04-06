from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time
import threading
import serial

app = Flask(__name__)

model = YOLO("best.pt")

arduino = None
arduino_connected = False
try:
    arduino = serial.Serial("/dev/ttyACM0", 9600, timeout=1)
    time.sleep(2)
    arduino_connected = True
except Exception as e:
    print(f"Arduino not connected: {e}")

picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (416, 416), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()
time.sleep(2)

CONF_THRESHOLD = 0.25
BAD_DEFECT_THRESHOLD = 3

# Helps avoid false triggers from one noisy frame
REQUIRED_CONSECUTIVE_BAD_FRAMES = 3

# Reset after leather disappears
MISSING_FRAMES_TO_RESET = 15

state_lock = threading.Lock()

bad_triggered = False
servo_busy = False
consecutive_bad_frames = 0
missing_frames = 0
leather_present = False
max_defects_seen = 0
current_defect_count = 0
current_status = "SCANNING..."
last_result = None
last_command_sent = None
last_raw_frame = None
last_annotated = None
last_detections = []


def trigger_bad_servo():
    global servo_busy, last_command_sent

    with state_lock:
        if servo_busy:
            return
        servo_busy = True
        last_command_sent = "B"

    try:
        print("BAD leather detected -> sending B to Arduino")
        if arduino_connected and arduino:
            arduino.write(b'B')
        time.sleep(20)
    finally:
        with state_lock:
            servo_busy = False


def generate_frames():
    global bad_triggered, servo_busy, consecutive_bad_frames
    global missing_frames, leather_present, max_defects_seen
    global current_defect_count, current_status, last_result
    global last_raw_frame, last_annotated, last_detections

    frame_count = 0
    defect_count = 0

    while True:
        frame = picam2.capture_array()
        last_raw_frame = frame.copy()
        frame_count += 1

        if frame_count % 2 == 0 or last_annotated is None:
            results = model(frame, imgsz=416, conf=CONF_THRESHOLD, verbose=False)
            result = results[0]

            defect_count = 0
            detections = []

            for box in result.boxes:
                conf = float(box.conf[0])
                if conf >= CONF_THRESHOLD:
                    defect_count += 1
                    cls_id = int(box.cls[0].item())
                    label = model.names.get(cls_id, str(cls_id))
                    detections.append({
                        "type": label,
                        "label": label,
                        "confidence": conf,
                    })

            current_defect_count = defect_count
            last_detections = detections
            last_annotated = result.plot()

            with state_lock:
                if defect_count > 0:
                    leather_present = True
                    missing_frames = 0
                    max_defects_seen = max(max_defects_seen, defect_count)
                else:
                    if leather_present:
                        missing_frames += 1

                # Only trigger on BAD leather
                if not bad_triggered and not servo_busy:
                    if defect_count >= BAD_DEFECT_THRESHOLD:
                        consecutive_bad_frames += 1
                    else:
                        consecutive_bad_frames = 0

                    if consecutive_bad_frames >= REQUIRED_CONSECUTIVE_BAD_FRAMES:
                        bad_triggered = True
                        threading.Thread(target=trigger_bad_servo, daemon=True).start()

                # Reset when leather is gone
                if leather_present and missing_frames >= MISSING_FRAMES_TO_RESET:
                    print(f"Leather finished. Max defects seen: {max_defects_seen}")

                    if bad_triggered:
                        print("Result: BAD leather")
                        last_result = "BAD"
                    else:
                        print("Result: GOOD leather")
                        last_result = "GOOD"

                    bad_triggered = False
                    consecutive_bad_frames = 0
                    missing_frames = 0
                    leather_present = False
                    max_defects_seen = 0
                    current_defect_count = 0

        with state_lock:
            if servo_busy:
                current_status = "BAD DETECTED | Servo active"
            elif leather_present:
                current_status = f"INSPECTING | defects={current_defect_count} | max={max_defects_seen}"
            else:
                current_status = "SCANNING..."

        display_frame = last_annotated.copy() if last_annotated is not None else frame.copy()
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR)

        success, buffer = cv2.imencode(
            ".jpg",
            display_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        )
        if not success:
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Cache-Control: no-cache, no-store, must-revalidate\r\n'
            b'Pragma: no-cache\r\n'
            b'Expires: 0\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )


@app.route("/video_feed")
def video_feed():
    response = Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/stream/status")
def stream_status():
    with state_lock:
        return jsonify({
            "status": "running",
            "machine": {
                "arduino_connected": arduino_connected,
                "leather_present": leather_present,
                "servo_busy": servo_busy,
                "bad_triggered": bad_triggered,
                "consecutive_bad_frames": consecutive_bad_frames,
                "missing_frames": missing_frames,
                "max_defects_seen": max_defects_seen,
                "current_defect_count": current_defect_count,
                "current_result": current_status,
                "last_command_sent": last_command_sent,
                "last_result": last_result,
            },
            "detections": last_detections,
        })


@app.route("/api/stream/snapshot")
def snapshot():
    if last_annotated is None:
        return ("No snapshot available", 404)

    frame_bgr = cv2.cvtColor(last_annotated, cv2.COLOR_RGB2BGR)
    success, buffer = cv2.imencode(
        ".jpg",
        frame_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    )
    if not success:
        return ("Snapshot encode failed", 500)

    return Response(buffer.tobytes(), mimetype="image/jpeg")


@app.route("/")
def index():
    return """
    <html>
      <body style="text-align:center;font-family:Arial">
        <h1>Leather Defect Detection Live Feed</h1>
        <img src="/video_feed" width="720">
      </body>
    </html>
    """


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5001, threaded=True)
    finally:
        if arduino:
            arduino.close()
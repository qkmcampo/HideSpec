from flask import Flask, Response, jsonify
from ultralytics import YOLO
from picamera2 import Picamera2
import cv2
import time

app = Flask(__name__)

print("=" * 55)
print("HIDESPEC — LIVE CAMERA STREAM SERVER")
print("YOLOv8n Detection with Pi Camera Module 3")
print("=" * 55)

print("\nLoading YOLO model...")
model = YOLO("best.pt")
print("Model loaded: best.pt")
print(f"Classes: {model.names}")

print("Starting camera...")
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()
time.sleep(2)
print("Camera started: 640x480")
print("Capture loop started.\n")

last_annotated = None
last_detections = []
frame_counter = 0

def run_detection(frame):
    global last_detections
    results = model(frame, imgsz=320, conf=0.25, verbose=False)
    annotated = results[0].plot()

    detections = []
    boxes = results[0].boxes
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
    global last_annotated, frame_counter

    while True:
        try:
            frame = picam2.capture_array()
            frame_counter += 1

            if last_annotated is None or frame_counter % 3 == 0:
                last_annotated = run_detection(frame)

            frame_bgr = cv2.cvtColor(last_annotated, cv2.COLOR_RGB2BGR)
            ok, buffer = cv2.imencode(
                ".jpg",
                frame_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), 65]
            )
            if not ok:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        except Exception as e:
            print(f"Stream error: {e}")
            time.sleep(0.1)

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
        "resolution": "640x480",
        "detections": last_detections,
    })

@app.route("/api/stream/snapshot")
def snapshot():
    try:
        frame = picam2.capture_array()
        annotated = run_detection(frame)
        frame_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        ok, buffer = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        )
        if not ok:
            return ("Snapshot encode failed", 500)
        return Response(buffer.tobytes(), mimetype="image/jpeg")
    except Exception as e:
        return (f"Snapshot failed: {e}", 500)

@app.route("/")
def home():
    return """
    <html>
      <body style="text-align:center;background:#111;color:white;font-family:Arial">
        <h1>HideSpec Live Stream</h1>
        <img src="/video_feed" width="900" />
      </body>
    </html>
    """

if __name__ == "__main__":
    print("Video stream: http://0.0.0.0:5001/video_feed")
    print("Stream status: http://0.0.0.0:5001/api/stream/status")
    print("Snapshot: http://0.0.0.0:5001/api/stream/snapshot")
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
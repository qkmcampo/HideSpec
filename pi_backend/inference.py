"""
Leather Hide Inspection — FINAL Inference Pipeline

✔ Auto-detection (no manual input)
✔ Saves directly to DB (hidespec.db)
✔ Compatible with analytics API
✔ Works with Picamera2 (Pi 5)
✔ Ready for real-time dashboard
"""

from ultralytics import YOLO
from db_manager import InspectionDB
import cv2
import time
import os
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.5
CAPTURE_INTERVAL = 5  # seconds
IMAGE_SAVE_DIR = "captures"

MAX_DEFECTS_FOR_GOOD = 1
BAD_IF_ANY = ["hole", "cut"]

CLASS_NAMES = {
    0: "color_defect",
    1: "fold",
    2: "hole",
}

# ─── INIT ─────────────────────────────────────────────────
print("Loading YOLO model...")
model = YOLO(MODEL_PATH)

db = InspectionDB()
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

hide_counter = 0


# ─── CAMERA SETUP ─────────────────────────────────────────
def setup_camera():
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        config = cam.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        cam.configure(config)
        cam.start()
        time.sleep(1)
        print("Camera initialized (Picamera2)")
        return cam, True
    except Exception as e:
        print(f"Picamera2 failed → {e}")

    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        print("Camera initialized (OpenCV)")
        return cap, False

    return None, False


def capture_image(camera, is_picam):
    if is_picam:
        frame = camera.capture_array()
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    else:
        ret, frame = camera.read()
        return frame if ret else None


def release_camera(camera, is_picam):
    if is_picam:
        camera.stop()
    else:
        camera.release()


# ─── CORE LOGIC ───────────────────────────────────────────
def classify_hide(defects):
    if len(defects) > MAX_DEFECTS_FOR_GOOD:
        return "Bad"

    for d in defects:
        if d["type"] in BAD_IF_ANY:
            return "Bad"

    return "Good"


def run_inference(image):
    results = model(image, conf=CONFIDENCE_THRESHOLD, verbose=False)

    defects = []
    for result in results:
        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                defects.append({
                    "type": CLASS_NAMES.get(cls_id, "unknown"),
                    "confidence": round(conf, 2),
                    "x": int(x1),
                    "y": int(y1),
                    "w": int(x2 - x1),
                    "h": int(y2 - y1),
                })

    return defects


# ─── 🔥 CRITICAL: DB SAVE ─────────────────────────────────
def process_hide(image, hide_id):
    defects = run_inference(image)
    classification = classify_hide(defects)

    image_path = os.path.join(IMAGE_SAVE_DIR, f"{hide_id}.jpg")
    cv2.imwrite(image_path, image)

    # 🔥 MUST MATCH db_manager.py
    inspection_id = db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=len(defects),
        image_path=image_path,
        created_at=datetime.utcnow().isoformat()
    )

    print(
        f"[INSPECT] {hide_id} → {classification} "
        f"({len(defects)} defects: "
        f"{', '.join(d['type'] for d in defects) if defects else 'none'})"
    )


# ─── AUTO DETECTION LOOP ─────────────────────────────────
def run_auto_detection():
    global hide_counter

    camera, is_picam = setup_camera()
    if camera is None:
        print("No camera detected")
        return

    print("\n=== AUTO DETECTION STARTED ===")
    print(f"Capturing every {CAPTURE_INTERVAL} seconds...\n")

    try:
        while True:
            hide_counter += 1
            hide_id = f"HIDE-{hide_counter:04d}"

            frame = capture_image(camera, is_picam)
            if frame is None:
                print("Capture failed")
                time.sleep(1)
                continue

            process_hide(frame, hide_id)

            time.sleep(CAPTURE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        release_camera(camera, is_picam)


# ─── ENTRY ───────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== HideSpec Live Detection ===")
    run_auto_detection()
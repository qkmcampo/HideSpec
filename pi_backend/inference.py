"""
Leather Hide Inspection — Inference Pipeline (FIXED FOR ANALYTICS)

✔ Saves data correctly for analytics
✔ Uses Picamera2 (Pi 5 compatible)
✔ Writes ISO timestamps
✔ Ensures defects JSON is valid
"""

from ultralytics import YOLO
from db_manager import InspectionDB
import cv2
import time
import os
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.5
IMAGE_SAVE_DIR = "captures"

MAX_DEFECTS_FOR_GOOD = 1
BAD_IF_ANY = ["hole", "cut"]

CLASS_NAMES = {
    0: "color_defect",
    1: "fold",
    2: "hole",
}

# ─── Initialize ───────────────────────────────────────────────
print("Loading YOLOv8 model...")
model = YOLO(MODEL_PATH)
print(f"Model loaded: {MODEL_PATH}")

db = InspectionDB()
print("Database connected.")

os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

hide_counter = 0


# ─── Camera Setup ─────────────────────────────────────────────
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
        print("Camera: Picamera2 initialized")
        return cam, True
    except:
        print("Picamera2 failed → using OpenCV fallback")

    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        return cap, False

    return None, False


def capture_image(camera, is_picamera2):
    if camera is None:
        return None

    if is_picamera2:
        try:
            frame = camera.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        except:
            return None
    else:
        ret, frame = camera.read()
        return frame if ret else None


def release_camera(camera, is_picamera2):
    if camera is None:
        return
    if is_picamera2:
        camera.stop()
    else:
        camera.release()


# ─── Core Logic ───────────────────────────────────────────────

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
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                defects.append({
                    "type": CLASS_NAMES.get(cls_id, "unknown"),
                    "confidence": round(confidence, 2),
                    "x": int(x1),
                    "y": int(y1),
                    "w": int(x2 - x1),
                    "h": int(y2 - y1),
                })

    return defects


# ─── 🔥 FIXED PART (IMPORTANT) ───────────────────────────────

def process_hide(image, hide_id):
    """
    This is the MOST IMPORTANT function for analytics.
    """

    defects = run_inference(image)
    classification = classify_hide(defects)

    # Save image
    image_path = os.path.join(IMAGE_SAVE_DIR, f"{hide_id}.jpg")
    cv2.imwrite(image_path, image)

    # 🔥 FIX: Proper DB save (MATCHES api_server.py)
    inspection_id = db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=len(defects),
        image_path=image_path,
        created_at=datetime.utcnow().isoformat()  # ✅ REQUIRED
    )

    inspection = db.get_inspection(inspection_id)

    print(
        f"[INSPECT] {hide_id} → {classification} "
        f"({len(defects)} defects: "
        f"{', '.join(d['type'] for d in defects) if defects else 'none'})"
    )

    return inspection


# ─── Main Loop ────────────────────────────────────────────────

def run_with_camera():
    global hide_counter

    camera, is_picam2 = setup_camera()
    if camera is None:
        print("ERROR: No camera")
        return

    print("\n=== LIVE INSPECTION MODE ===")
    print("Press ENTER to inspect | q to quit\n")

    try:
        while True:
            user_input = input(">> Inspect next hide: ")
            if user_input.lower() == 'q':
                break

            hide_counter += 1
            hide_id = f"HIDE-{hide_counter:04d}"

            frame = capture_image(camera, is_picam2)
            if frame is None:
                print("Capture failed")
                continue

            process_hide(frame, hide_id)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        release_camera(camera, is_picam2)
        print("Camera released")


# ─── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== HideSpec Inference ===")
    run_with_camera()
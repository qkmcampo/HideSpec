"""
Leather Hide Inspection — Inference Pipeline
Runs on Raspberry Pi 5. Uses your trained YOLOv8 model.
Saves results to SQLite → mobile/web app picks them up automatically.

IMPORTANT: Uses Picamera2 (NOT cv2.VideoCapture) for Pi 5 Bookworm compatibility.

Install requirements:
    sudo apt install -y python3-picamera2 python3-libcamera
    pip install ultralytics flask flask-cors flask-socketio opencv-python-headless --break-system-packages

Usage:
    python3 inference.py
"""

from ultralytics import YOLO
from db_manager import InspectionDB
import cv2
import time
import json
import os
import numpy as np

# ─── Configuration ────────────────────────────────────────────
MODEL_PATH = "best.pt"
CONFIDENCE_THRESHOLD = 0.5
IMAGE_SAVE_DIR = "captures"

# Classification rules (from your paper):
# Bad = 2 or more defects OR any hole detected
MAX_DEFECTS_FOR_GOOD = 1
BAD_IF_ANY = ["hole", "cut"]

# Class names from your trained model (extracted from best.pt)
CLASS_NAMES = {
    0: "color_defect",
    1: "fold",
    2: "hole",
}

# ─── Initialize ───────────────────────────────────────────────
print("Loading YOLOv8 model...")
model = YOLO(MODEL_PATH)
print(f"Model loaded: {MODEL_PATH}")
print(f"Classes: {model.names}")

db = InspectionDB()
print("Database connected.")

os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

hide_counter = 0


# ─── Camera Setup ─────────────────────────────────────────────
def setup_camera():
    """
    Initialize camera using Picamera2 (Pi 5 Bookworm).
    Falls back to OpenCV for testing on laptops.
    Returns (camera_object, is_picamera2)
    """
    # Try Picamera2 first (correct for Pi 5)
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        config = cam.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        cam.configure(config)
        cam.start()
        time.sleep(1)
        print("Camera: Picamera2 initialized successfully")
        return cam, True
    except ImportError:
        print("WARNING: picamera2 not installed. Trying OpenCV fallback...")
    except Exception as e:
        print(f"WARNING: Picamera2 failed ({e}). Trying OpenCV fallback...")

    # Fallback to OpenCV (for testing on laptops)
    try:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("Camera: OpenCV VideoCapture initialized")
            return cap, False
        else:
            print("ERROR: OpenCV cannot open camera!")
    except Exception as e:
        print(f"ERROR: OpenCV failed: {e}")

    return None, False


def capture_image(camera, is_picamera2):
    """Capture a single image from the camera."""
    if camera is None:
        print("ERROR: No camera available!")
        return None

    if is_picamera2:
        try:
            frame = camera.capture_array()
            # Picamera2 returns RGB, convert to BGR for OpenCV
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            return frame
        except Exception as e:
            print(f"Capture error: {e}")
            return None
    else:
        ret, frame = camera.read()
        if ret:
            return frame
        print("ERROR: Failed to read frame from OpenCV camera!")
        return None


def release_camera(camera, is_picamera2):
    """Properly release the camera."""
    if camera is None:
        return
    if is_picamera2:
        try:
            camera.stop()
        except:
            pass
    else:
        try:
            camera.release()
        except:
            pass


# ─── Helper Functions ─────────────────────────────────────────

def classify_hide(defects):
    """
    Determine if hide is Good or Bad based on defect rules.
    From your paper: Bad if 2+ defects or any hole detected.
    """
    if len(defects) > MAX_DEFECTS_FOR_GOOD:
        return "Bad"

    for defect in defects:
        if defect["type"] in BAD_IF_ANY:
            return "Bad"

    return "Good"


def run_inference(image):
    """
    Run YOLOv8 inference on a single image.
    Returns list of detected defects.
    """
    results = model(image, conf=CONFIDENCE_THRESHOLD, verbose=False)

    defects = []
    for result in results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                defect = {
                    "type": CLASS_NAMES.get(cls_id, "unknown"),
                    "confidence": round(confidence, 2),
                    "x": int(x1),
                    "y": int(y1),
                    "w": int(x2 - x1),
                    "h": int(y2 - y1),
                }
                defects.append(defect)

    return defects


def process_hide(image, hide_id):
    """
    Full inspection pipeline for one leather hide.
    Detects defects, classifies, saves to database.
    Returns the inspection record.
    """
    defects = run_inference(image)
    classification = classify_hide(defects)

    image_path = os.path.join(IMAGE_SAVE_DIR, f"{hide_id}.jpg")
    cv2.imwrite(image_path, image)

    inspection_id = db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=len(defects),
        image_path=image_path,
    )

    inspection = db.get_inspection(inspection_id)

    print(f"[INSPECT] {hide_id} → {classification} "
          f"({len(defects)} defects: {', '.join(d['type'] for d in defects) if defects else 'none'})")

    return inspection


# ─── Main Loop ────────────────────────────────────────────────

def run_with_camera():
    """
    Continuous inspection using the Pi camera (Picamera2).
    """
    global hide_counter

    camera, is_picam2 = setup_camera()
    if camera is None:
        print("ERROR: Cannot open any camera!")
        print("Make sure the camera cable is connected and run:")
        print("  sudo apt install python3-picamera2 python3-libcamera")
        return

    print(f"\n{'=' * 50}")
    print(f"  LEATHER HIDE INSPECTION SYSTEM")
    print(f"  YOLOv8 Model: {MODEL_PATH}")
    print(f"  Camera: {'Picamera2' if is_picam2 else 'OpenCV'}")
    print(f"  Press ENTER to inspect a hide")
    print(f"  Press 'q' to quit")
    print(f"{'=' * 50}\n")

    try:
        while True:
            user_input = input(">> Press ENTER to inspect next hide (q to quit): ")
            if user_input.lower() == 'q':
                break

            hide_counter += 1
            hide_id = f"HIDE-{hide_counter:04d}"

            frame = capture_image(camera, is_picam2)
            if frame is None:
                print("ERROR: Failed to capture image! Check camera connection.")
                continue

            result = process_hide(frame, hide_id)

    except KeyboardInterrupt:
        print("\nStopping inspection...")
    finally:
        release_camera(camera, is_picam2)
        print("Camera released. System stopped.")


def run_with_test_images(image_folder="test_images"):
    """
    Test the pipeline using images from a folder.
    No camera needed.
    """
    global hide_counter

    if not os.path.exists(image_folder):
        print(f"ERROR: Folder '{image_folder}' not found!")
        print(f"Create it and put some leather hide images inside.")
        return

    image_files = [f for f in os.listdir(image_folder)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]

    if not image_files:
        print(f"No images found in '{image_folder}'!")
        return

    print(f"\nFound {len(image_files)} test images in '{image_folder}'")
    print("Processing...\n")

    for img_file in sorted(image_files):
        hide_counter += 1
        hide_id = f"HIDE-{hide_counter:04d}"

        image_path = os.path.join(image_folder, img_file)
        image = cv2.imread(image_path)

        if image is None:
            print(f"WARNING: Cannot read {img_file}, skipping...")
            continue

        result = process_hide(image, hide_id)
        time.sleep(1)

    print(f"\nDone! Processed {hide_counter} hides.")
    print("Open HideSpec on your phone to see the results.")


# ─── Entry Point ──────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'=' * 50}")
    print(f"  HideSpec — Leather Hide Inspection")
    print(f"  Team 10 · TIP QC")
    print(f"{'=' * 50}")
    print(f"\nSelect mode:")
    print(f"  1 = Camera (live inspection with Pi Camera)")
    print(f"  2 = Test images (from folder)")
    print()

    mode = input("Enter 1 or 2: ").strip()

    if mode == "2":
        folder = input("Image folder path (default: test_images): ").strip()
        if not folder:
            folder = "test_images"
        run_with_test_images(folder)
    else:
        run_with_camera()

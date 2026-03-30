"""
Leather Hide Inspection — Inference Pipeline
Runs on Raspberry Pi 5. Uses your trained YOLOv8 model.
Saves results to SQLite → mobile app picks them up automatically.

Usage:
    1. Put your best.pt model file in the same folder
    2. Run: python inference.py
    3. Run api_server.py in a separate terminal
    4. Open HideSpec on your phone
"""

from ultralytics import YOLO
from db_manager import InspectionDB
import cv2
import time
import json

# ─── Configuration ────────────────────────────────────────────
MODEL_PATH = "best.pt"          # ← Your trained YOLOv8 model file
CONFIDENCE_THRESHOLD = 0.5      # Minimum confidence to count as defect
CAMERA_INDEX = 0                # Camera index (0 = default Pi camera)
IMAGE_SAVE_DIR = "captures"     # Folder to save inspection images

# Classification rules (from your paper):
# Bad = 2 or more defects OR any hole detected
MAX_DEFECTS_FOR_GOOD = 1        # 0 or 1 defects = Good
BAD_IF_ANY = ["hole", "cut"]           # Any of these defect types = automatic Bad

# Class names from your trained model (extracted from best.pt)
CLASS_NAMES = {
    0: "color_defect",
    1: "fold",
    2: "hole",
    3: "cut",
}

# ─── Initialize ───────────────────────────────────────────────
print("Loading YOLOv8 model...")
model = YOLO(MODEL_PATH)
print(f"Model loaded: {MODEL_PATH}")

db = InspectionDB()
print("Database connected.")

import os
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

hide_counter = 0

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
    # Run YOLOv8 inference
    defects = run_inference(image)
    
    # Classify as Good or Bad
    classification = classify_hide(defects)
    
    # Save captured image
    image_path = os.path.join(IMAGE_SAVE_DIR, f"{hide_id}.jpg")
    cv2.imwrite(image_path, image)
    
    # Save to database (mobile app reads from here)
    inspection_id = db.save_inspection(
        hide_id=hide_id,
        classification=classification,
        defects=defects,
        total_defects=len(defects),
        image_path=image_path,
    )
    
    # Get the full record to return
    inspection = db.get_inspection(inspection_id)
    
    print(f"[INSPECT] {hide_id} → {classification} "
          f"({len(defects)} defects: {', '.join(d['type'] for d in defects) if defects else 'none'})")
    
    return inspection


# ─── Main Loop ────────────────────────────────────────────────
# Option A: Camera-based (use this when hardware is assembled)

def run_with_camera():
    """
    Continuous inspection using the Pi camera.
    Waits for IR sensor trigger (simulated with keyboard for now).
    """
    global hide_counter
    
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("ERROR: Cannot open camera!")
        return
    
    print("\n" + "=" * 50)
    print("  LEATHER HIDE INSPECTION SYSTEM")
    print("  YOLOv8 Model: " + MODEL_PATH)
    print("  Press ENTER to inspect a hide")
    print("  Press 'q' to quit")
    print("=" * 50 + "\n")
    
    try:
        while True:
            # In real prototype: this would be triggered by IR sensor
            # For testing: press Enter to capture and inspect
            user_input = input(">> Press ENTER to inspect next hide (q to quit): ")
            if user_input.lower() == 'q':
                break
            
            hide_counter += 1
            hide_id = f"HIDE-{hide_counter:04d}"
            
            # Capture image
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to capture image!")
                continue
            
            # Process the hide
            result = process_hide(frame, hide_id)
            
    except KeyboardInterrupt:
        print("\nStopping inspection...")
    finally:
        cap.release()
        print("Camera released. System stopped.")


# Option B: Test with images from a folder (no camera needed)

def run_with_test_images(image_folder="test_images"):
    """
    Test the pipeline using images from a folder.
    Useful for testing before hardware is ready.
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
        time.sleep(1)  # Small delay between inspections
    
    print(f"\nDone! Processed {hide_counter} hides.")
    print("Open HideSpec on your phone to see the results.")


# ─── Entry Point ──────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  HideSpec — Leather Hide Inspection")
    print("  Team 10 · TIP QC")
    print("=" * 50)
    print("\nSelect mode:")
    print("  1 = Camera (live inspection)")
    print("  2 = Test images (from folder)")
    print()
    
    mode = input("Enter 1 or 2: ").strip()
    
    if mode == "2":
        folder = input("Image folder path (default: test_images): ").strip()
        if not folder:
            folder = "test_images"
        run_with_test_images(folder)
    else:
        run_with_camera()

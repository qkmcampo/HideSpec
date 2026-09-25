"""
Main System Host (app5.py)
Threaded execution engine separating real-time vision/hardware control
from Web HTTP streaming, while also driving the calibrated projector overlay.
"""

from flask import Flask, Response, jsonify, render_template
from ultralytics import YOLO
from picamera2 import Picamera2
from leather_cv import LeatherCV
from return_control import screen_or_return
from projector import ProjectorMapper
import cv2
import numpy as np
import glob
import time
import serial
import threading
import os
import json
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
try:
    import resource
except ImportError:
    resource = None


app = Flask(__name__)
resume_return_event = threading.Event()


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Cache-Control"] = "no-store"
    return response


# =====================================================
# Camera / Detection Configuration
# =====================================================

# Lower inference size substantially reduces Raspberry Pi latency while
# Ultralytics still returns boxes in the original 1400x1600 frame coordinates.
# If very small-defect recall drops, try 736 instead of returning to 960.
IMG_SIZE = 640
FRAME_WIDTH = 1400
FRAME_HEIGHT = 1600

# ----- Physical area calibration -----
# Measured reference leather: 17 cm x 25 cm = 425 cm^2.
# With the current fixed camera height/zoom/inspection plane, the corrected
# segmentation measured that leather at approximately 226,291 pixels.
#
# Keep ALL vision calculations in pixels internally; convert only the reported
# physical area values for the dashboard / thesis metrics.
AREA_CALIBRATION_PIXELS = 226291.0
AREA_CALIBRATION_CM2 = 17.0 * 25.0
PIXELS_PER_CM2 = AREA_CALIBRATION_PIXELS / AREA_CALIBRATION_CM2

def pixels_to_cm2(pixel_area):
    """Convert calibrated image area in px^2 to physical cm^2."""
    if pixel_area is None or pixel_area <= 0:
        return 0.0
    return float(pixel_area) / PIXELS_PER_CM2

CONF_THRESHOLD = 0.35
MIN_DEFECT_WIDTH = 15
MIN_DEFECT_HEIGHT = 15

# ----- Pixel-accurate defect coverage -----
# YOLO boxes are used only to LOCALIZE each defect.  Coverage is estimated
# from actual anomalous pixels inside each box instead of counting the entire
# rectangular bounding box as defective.
DEFECT_MASK_RING_PAD_RATIO = 0.35
DEFECT_MASK_MIN_RING_PIXELS = 120
DEFECT_MASK_MIN_COMPONENT_PX = 12
DEFECT_MASK_DRAW = True

# ----- Grading rules (see leather_cv.py) -----
# BAD if defect area >= 20 % of the piece  (ISO 17551:2018, Grade II/III line)
# BAD if more than 4 defects on the piece   (packer grading: No.2 allows <= 4)
# BAD if any defect of a CRITICAL class is found.
#   Empty by default, so a piece with 1-2 small holes is judged by count and
#   area like everything else. Put ("hole",) back here if your team decides
#   any hole must reject the piece outright.
DEFECT_RATIO_THRESH = 20.0
MAX_DEFECT_COUNT = 4
CRITICAL_CLASSES = ()

# ----- Camera exposure lock -----
# Auto-exposure was re-adjusting every time a bright or dark piece entered the
# frame, which shifted the whole belt brightness and broke segmentation.
# Exposure/white balance are now measured once on the EMPTY belt and locked.
# Lower EXPOSURE_SCALE (e.g. 0.8) if white/cream leather looks blown out;
# raise it (e.g. 1.2) if dark leather looks too black.
LOCK_EXPOSURE = True
EXPOSURE_SCALE = 0.9


# =====================================================
# Projector Configuration
# =====================================================

PROJECTOR_WIDTH = 1024
PROJECTOR_HEIGHT = 768

# Current Raspberry Pi extended desktop layout:
# HDMI-A-1 monitor    = 1920x1080 at (0, 0)
# HDMI-A-2 projector  = 1024x768 at (1920, 0)
#
# The projector is now used in true fullscreen so its image fills
# the whole 1024x768 projector field.
PROJECTOR_X = 1920
PROJECTOR_Y = 0
PROJECTOR_WINDOW = "PROJECTOR"

# Height of the violet stop/trigger band in CAMERA pixels.
# Its lower edge is automatically aligned with the lowest edge
# of the calibrated projector field in the camera view.
PROJECTION_TRIGGER_BAND_HEIGHT = 150

# Time after STOP before we accept a fresh YOLO frame for projection.
PROJECTION_SETTLE_DELAY = 0.35

# How long the actual defect overlay should remain visible.
PROJECTION_DISPLAY_DURATION = 5.0

# Number of consecutive frames that the inspection zone must be clear
# before the projector is armed for the NEXT leather piece.
PROJECTION_REARM_CLEAR_FRAMES = 5


# =====================================================
# Model / CV Initialization
# =====================================================

MODEL_PATH = "best_ncnn_model" if os.path.exists("best_ncnn_model") else "best.pt"
model = YOLO(MODEL_PATH)
CLASS_NAMES = model.names


def model_size_mb(path):
    if os.path.isfile(path):
        return round(os.path.getsize(path) / (1024 * 1024), 2)
    if os.path.isdir(path):
        total = sum(
            os.path.getsize(os.path.join(root, name))
            for root, _dirs, files in os.walk(path)
            for name in files
        )
        return round(total / (1024 * 1024), 2)
    return None


def memory_usage_mb():
    if resource is None:
        return None
    # Linux reports ru_maxrss in kilobytes.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)


MODEL_SIZE_MB = model_size_mb(MODEL_PATH)


def performance_snapshot(inference_ms=0.0):
    inference_ms = float(inference_ms or 0)
    return {
        "model": MODEL_PATH,
        "model_size_mb": MODEL_SIZE_MB,
        "input_size": IMG_SIZE,
        "inference_ms": round(inference_ms, 1),
        "inference_fps": round(1000 / inference_ms, 2) if inference_ms > 0 else None,
        "memory_mb": memory_usage_mb(),
        "macs": None,
        "macs_status": "Requires model profiling",
        "recall": None,
        "recall_status": "Requires labeled ground-truth test results",
    }

cv_engine = LeatherCV(
    frame_width=FRAME_WIDTH,
    frame_height=FRAME_HEIGHT,
    defect_ratio_thresh=DEFECT_RATIO_THRESH,
    max_defect_count=MAX_DEFECT_COUNT,
    critical_classes=CRITICAL_CLASSES,
)

projector_mapper = ProjectorMapper(
    width=PROJECTOR_WIDTH,
    height=PROJECTOR_HEIGHT,
    calibration_file="projector_homography.npy",
)

if projector_mapper.is_calibrated():
    print("[PROJECTOR] Camera-projector mapping ready.")
else:
    print("[PROJECTOR] WARNING: projector_homography.npy not available.")


def get_projector_camera_geometry():
    """
    Convert the four fullscreen projector corners back into camera coordinates.

    Returns:
        polygon: 4x2 int32 camera-coordinate polygon
        lower_edge_y: average Y of the physically lowest projector edge
                      in the camera image

    This lets the violet inspection band automatically follow the calibrated
    projector field instead of relying on hard-coded Y coordinates.
    """
    if not projector_mapper.is_calibrated():
        return None, 875

    try:
        H_inv = np.linalg.inv(projector_mapper.H)

        projector_corners = np.array(
            [[[
                [0.0, 0.0],
                [PROJECTOR_WIDTH - 1.0, 0.0],
                [PROJECTOR_WIDTH - 1.0, PROJECTOR_HEIGHT - 1.0],
                [0.0, PROJECTOR_HEIGHT - 1.0],
            ]]],
            dtype=np.float32,
        ).reshape(1, 4, 2)

        camera_corners = cv2.perspectiveTransform(
            projector_corners,
            H_inv
        )[0]

        # Evaluate all four polygon edges and select the one that appears
        # lowest in the camera image (largest mean Y).
        edges = [
            (camera_corners[0], camera_corners[1]),
            (camera_corners[1], camera_corners[2]),
            (camera_corners[2], camera_corners[3]),
            (camera_corners[3], camera_corners[0]),
        ]

        lower_edge = max(
            edges,
            key=lambda edge: (edge[0][1] + edge[1][1]) / 2.0
        )

        lower_edge_y = int(round(
            (lower_edge[0][1] + lower_edge[1][1]) / 2.0
        ))

        lower_edge_y = max(
            0,
            min(FRAME_HEIGHT - 1, lower_edge_y)
        )

        polygon = np.round(camera_corners).astype(np.int32)

        return polygon, lower_edge_y

    except Exception as exc:
        print(f"[PROJECTOR] Could not derive camera footprint: {exc}")
        return None, 875


PROJECTOR_CAMERA_POLYGON, PROJECTOR_ENTRY_Y = get_projector_camera_geometry()


# =====================================================
# Target / Inspection Zones
# =====================================================

# Mechanical marker target band.
# Keep the wider band that worked better physically. Reliability is improved
# in software by processing only one Y-row at a time instead of making the
# trigger rectangle extremely thin.
CENTER_X_MIN = 20
CENTER_X_MAX = 1380
CENTER_Y_MIN = 100
CENTER_Y_MAX = 220

# -----------------------------------------------------------------
# Mechanical marker early-arm / arrival prediction
# -----------------------------------------------------------------
# The physical marker is STILL the yellow 100..220 camera-Y band above.
# The problem seen in the latest test was that YOLO still saw the defect at
# Y=333 and Y=252, then lost the box before its centre ever reached Y=220.
#
# We therefore remember a defect BEFORE it reaches the physical marker.  Once
# its centre reaches MARK_ARM_Y, its recent Y motion is used to estimate when
# it will reach an EARLY software stop point before the physical marker.  The
# worker sends STOP there so conveyor coasting carries the defect toward the
# real Y=100..220 marking area, then lets the belt settle and sends MARK:<steps>.
#
# This is deliberately separate from the physical marker coordinates.
# The physical marker location itself is NOT moved by this calibration.
#
# The worker
# waits only for that short travel interval, sends STOP slightly early, lets
# the belt settle, and then sends the normal MARK:<steps> command using the
# remembered X coordinate.
MARK_MEMORY_Y_MAX = 590       # shifted 90 px earlier to preserve tracking lead
MARK_ARM_Y = 470              # shifted 90 px earlier to preserve prediction window

# CALIBRATION AFTER PHYSICAL TEST:
# First physical correction:
#   Y=200 -> Y=320 moved the software stop 120 camera pixels earlier and corrected
#   approximately 4 cm of conveyor over-travel.
#
# Latest physical correction:
#   The mark is still about 3 cm past the physical marking line. Using the same
#   calibration (~30 px per cm), another 3 cm corresponds to about 90 pixels.
#   Because conveyor travel is toward SMALLER Y, an EARLIER stop uses a LARGER
#   camera-Y value, so the predictive stop target is moved from Y=320 to Y=410.
#
# The physical yellow marker band itself remains unchanged at Y=100..220.
MARK_TARGET_Y = 410           # another ~3 cm earlier; NOT the physical marker line
MARK_EARLY_STOP_LEAD_SEC = 0.18
MARK_BELT_SETTLE_DELAY = 0.20
MARK_MIN_SPEED_PX_S = 20.0
MARK_FALLBACK_SPEED_PX_S = 75.0
MARK_MAX_WAIT_SEC = 3.0
MARK_MEMORY_TIMEOUT_SEC = 5.0

# Defects separated by more than this in Y are NOT stamped during the same
# conveyor stop. They receive their own stop when the conveyor resumes.
SAME_ROW_TOLERANCE = 35

# Persistent tracker settings for multiple moving defects.
TRACK_MAX_DISTANCE = 180
TRACK_MAX_MISSED = 4

# Hold the completed hide state after it leaves the camera so the leather
# has enough time to physically reach the segregation gate. During this
# interval, the previous GOOD/BAD servo position is preserved and the system
# is NOT re-armed for a new segregation decision.
LEATHER_EXIT_RESET_DELAY = 5.0

# Center inspection / projection pause zone.
#
# Fixed to the position marked by the red rectangle in the latest camera view.
# Camera resolution is 1400x1600. The requested rectangle corresponds
# approximately to Y = 560..910 in the full camera frame.
#
# The leather triggers the inspection pause as soon as its bounding rectangle
# overlaps this violet band.
MIDDLE_Y_MIN = 560
MIDDLE_Y_MAX = 910

print(
    f"[PROJECTOR] Violet trigger band fixed at "
    f"Y = {MIDDLE_Y_MIN}..{MIDDLE_Y_MAX}."
)

# Total stop time = settling delay + visible projection time.
# Total pause automatically follows settling delay + display duration.
PAUSE_DURATION = PROJECTION_SETTLE_DELAY + PROJECTION_DISPLAY_DURATION


# =====================================================
# Mechanical Marker Calibration (kept unchanged)
# =====================================================

X_OFFSET_PX = -25
REF_X1_PX = 350
REF_STEPS1 = 7200
REF_X2_PX = 1000
REF_STEPS2 = 18000
STEPS_PER_PIXEL = (REF_STEPS2 - REF_STEPS1) / (REF_X2_PX - REF_X1_PX)


# =====================================================
# System State
# =====================================================

is_currently_stopped = False
pending_marks = []

is_center_paused = False
pause_start_time = 0.0
has_paused_for_current_hide = False
projection_zone_clear_frames = 0

# Projection state
projection_active = False
projection_captured = False
frozen_projection_detections = []

# Segregation state
# The 360-degree servo starts PHYSICALLY positioned at GOOD and is stopped.
# Arduino converts SEG:GOOD / SEG:BAD into timed 1.5-second movements.
# servo_state is the last known physical diverter side, not an angle.
segregation_sent_for_current_hide = False
servo_state = "GOOD"
current_hide_id = None
current_inspection_saved = False

# Shared camera stream buffer
frame_lock = threading.Lock()
output_frame_bytes = None

# Shared projector frame
projector_lock = threading.Lock()
projector_frame = np.zeros(
    (PROJECTOR_HEIGHT, PROJECTOR_WIDTH, 3),
    dtype=np.uint8,
)

latest_stats = {
    "grade": "NO LEATHER",
    "ratio": 0.0,
    "reason": "empty belt",
    "piece_area": 0,
    "piece_area_cm2": 0.0,
    "defect_pixels": 0,
    "defect_area_cm2": 0.0,
    "pixels_per_cm2": round(PIXELS_PER_CM2, 3),
    "status": "BELT: RUNNING",
    "projector_status": (
        "READY" if projector_mapper.is_calibrated() else "NOT CALIBRATED"
    ),
    "projected_defects": 0,
    "servo_state": "GOOD",
    "defect_count": 0,
    "hide_id": None,
    "inspection_saved": False,
    "camera_connected": True,
    "updated_at": time.time(),
    "performance": performance_snapshot(),
}

API_SERVER_URL = os.getenv("HIDESPEC_API_URL", "http://127.0.0.1:5001")
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)


def save_inspection_record(hide_id, detections, grade, ratio, piece_area, status_text, frame=None):
    snapshot_name = f"{hide_id}.jpg"
    snapshot_path = f"/captures/{snapshot_name}"
    if frame is not None:
        snapshot_file = os.path.join(CAPTURES_DIR, snapshot_name)
        encoded_ok, encoded = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
        )
        if encoded_ok:
            try:
                with open(snapshot_file, "wb") as capture_file:
                    capture_file.write(encoded.tobytes())
                print(f"[CAPTURE] Saved {snapshot_file}", flush=True)
            except OSError as error:
                print(f"[CAPTURE] Failed to write {snapshot_file}: {error}", flush=True)
                snapshot_path = None
        else:
            print(f"[CAPTURE] Failed to encode {snapshot_file}", flush=True)
            snapshot_path = None
    else:
        print(f"[CAPTURE] No inspection frame available for {hide_id}", flush=True)
        snapshot_path = None

    payload = {
        "hide_id": hide_id,
        "defects": [
            {
                "type": name,
                "confidence": round(float(conf), 4),
                "x": int(x1), "y": int(y1),
                "w": int(x2 - x1), "h": int(y2 - y1),
            }
            for name, _class_id, x1, y1, x2, y2, conf, _cx, _cy in detections
        ],
        "defect_area_percent": round(float(ratio or 0), 1),
        "leather_area": int(piece_area or 0),
        "defect_area": int((piece_area or 0) * float(ratio or 0) / 100.0),
        "classification": "Bad" if grade == "BAD" else "Good",
        "snapshot_path": snapshot_path,
        "machine_status": status_text,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
    }
    request_object = urlrequest.Request(
        f"{API_SERVER_URL}/api/inspections",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(request_object, timeout=5) as response:
            response.read()
        print(f"[DB] Inspection saved for {hide_id}", flush=True)
        return True
    except HTTPError as error:
        print(f"[DB] Save failed for {hide_id}: HTTP {error.code}", flush=True)
    except URLError as error:
        print(f"[DB] Save failed for {hide_id}: {error.reason}", flush=True)
    except Exception as error:
        print(f"[DB] Save failed for {hide_id}: {error}", flush=True)
    return False


# =====================================================
# Defect Tracker
# =====================================================

class DefectTracker:
    """
    Persistent, class-aware tracker for conveyor defects.

    The previous tracker deleted an ID immediately when one YOLO frame missed
    a defect and matched only by raw centroid distance. With multiple defects
    this could cause ID swaps or new IDs, which directly hurts marking logic.
    """

    def __init__(
        self,
        max_distance=TRACK_MAX_DISTANCE,
        max_missed=TRACK_MAX_MISSED,
    ):
        self.next_id = 0
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.tracked = {}

    def update(self, current_detections):
        updated = {}
        used_indices = set()

        for tid, track in self.tracked.items():
            # Predict one inference step ahead using the previous motion.
            predicted_x = track["cx"] + track.get("vx", 0.0)
            predicted_y = track["cy"] + track.get("vy", 0.0)

            best_idx = -1
            best_dist = float("inf")

            for idx, detection in enumerate(current_detections):
                if idx in used_indices:
                    continue

                # Match only the same defect class.
                if detection[1] != track["cls_id"]:
                    continue

                cx = detection[7]
                cy = detection[8]

                dist = np.hypot(
                    cx - predicted_x,
                    cy - predicted_y,
                )

                if dist < best_dist and dist <= self.max_distance:
                    best_dist = dist
                    best_idx = idx

            if best_idx != -1:
                detection = current_detections[best_idx]
                cx = detection[7]
                cy = detection[8]

                updated[tid] = {
                    "cx": cx,
                    "cy": cy,
                    "vx": cx - track["cx"],
                    "vy": cy - track["cy"],
                    "cls_id": detection[1],
                    "missed": 0,
                }

                used_indices.add(best_idx)

            else:
                missed = track["missed"] + 1

                if missed <= self.max_missed:
                    kept = dict(track)
                    kept["missed"] = missed
                    updated[tid] = kept

        # Assign IDs to truly new detections.
        for idx, detection in enumerate(current_detections):
            if idx in used_indices:
                continue

            cx = detection[7]
            cy = detection[8]

            updated[self.next_id] = {
                "cx": cx,
                "cy": cy,
                "vx": 0.0,
                "vy": 0.0,
                "cls_id": detection[1],
                "missed": 0,
            }

            self.next_id += 1

        self.tracked = updated

        # Marker decisions use only defects seen on THIS YOLO inference.
        return {
            tid: (track["cx"], track["cy"])
            for tid, track in self.tracked.items()
            if track["missed"] == 0
        }

    def current_positions(self):
        return {
            tid: (track["cx"], track["cy"])
            for tid, track in self.tracked.items()
            if track["missed"] == 0
        }

    def reset(self):
        self.tracked.clear()
        self.next_id = 0


# =====================================================
# Utility Functions
# =====================================================

def get_class_color(class_id):
    palette = [
        (0, 255, 255),
        (255, 0, 255),
        (255, 255, 0),
        (0, 165, 255),
        (255, 0, 0),
        (0, 255, 0),
        (128, 0, 255),
        (0, 128, 255),
    ]
    return palette[class_id % len(palette)]



def _fallback_defect_roi_mask(width, height, class_name):
    """Fallback shape only when local colour segmentation is unreliable."""
    mask = np.zeros((height, width), dtype=np.uint8)
    if width <= 0 or height <= 0:
        return mask

    name = str(class_name).lower()

    if "paint" in name or "stain" in name or "hole" in name:
        # Paint spots / holes in this project are generally compact.  An ellipse
        # is much closer to their physical area than a full YOLO rectangle.
        center = (width // 2, height // 2)
        axes = (
            max(1, int(width * 0.46)),
            max(1, int(height * 0.46)),
        )
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
        return mask

    if "fold" in name:
        # A fold is usually a long narrow region.  Use a conservative central
        # strip rather than counting its entire box.
        if width >= height:
            y1 = max(0, int(height * 0.32))
            y2 = min(height, int(height * 0.68))
            cv2.rectangle(mask, (0, y1), (width - 1, max(y1, y2 - 1)), 255, -1)
        else:
            x1 = max(0, int(width * 0.32))
            x2 = min(width, int(width * 0.68))
            cv2.rectangle(mask, (x1, 0), (max(x1, x2 - 1), height - 1), 255, -1)
        return mask

    cv2.rectangle(mask, (0, 0), (width - 1, height - 1), 255, -1)
    return mask


def _estimate_defect_roi_mask(
    frame_lab,
    piece_mask,
    class_name,
    x1,
    y1,
    x2,
    y2,
):
    """
    Estimate the ACTUAL defect pixels inside one YOLO box.

    A ring immediately around the box supplies the local normal-leather colour.
    Pixels inside the box that differ strongly from that local leather reference
    become the defect mask.  This works especially well for paint stains and
    holes while remaining usable for fold/shadow defects.
    """
    h_frame, w_frame = piece_mask.shape[:2]

    x1 = max(0, min(w_frame - 1, int(x1)))
    y1 = max(0, min(h_frame - 1, int(y1)))
    x2 = max(x1 + 1, min(w_frame, int(x2)))
    y2 = max(y1 + 1, min(h_frame, int(y2)))

    box_w = x2 - x1
    box_h = y2 - y1
    box_area = box_w * box_h

    if box_area <= 0:
        return np.zeros((box_h, box_w), dtype=np.uint8), "invalid"

    pad = max(
        12,
        int(round(max(box_w, box_h) * DEFECT_MASK_RING_PAD_RATIO)),
    )

    ex1 = max(0, x1 - pad)
    ey1 = max(0, y1 - pad)
    ex2 = min(w_frame, x2 + pad)
    ey2 = min(h_frame, y2 + pad)

    expanded_piece = piece_mask[ey1:ey2, ex1:ex2] > 0
    ring = expanded_piece.copy()

    bx1 = x1 - ex1
    by1 = y1 - ey1
    bx2 = x2 - ex1
    by2 = y2 - ey1
    ring[by1:by2, bx1:bx2] = False

    ring_pixels = frame_lab[ey1:ey2, ex1:ex2][ring]
    roi_piece = piece_mask[y1:y2, x1:x2] > 0

    if ring_pixels.shape[0] < DEFECT_MASK_MIN_RING_PIXELS:
        fallback = _fallback_defect_roi_mask(box_w, box_h, class_name)
        fallback[~roi_piece] = 0
        return fallback, "fallback:no-ring"

    reference = np.median(ring_pixels, axis=0).astype(np.float32)

    ring_delta = np.linalg.norm(
        ring_pixels.astype(np.float32) - reference,
        axis=1,
    )
    ring_median = float(np.median(ring_delta))
    ring_mad = float(np.median(np.abs(ring_delta - ring_median)))
    robust_sigma = 1.4826 * ring_mad

    name = str(class_name).lower()

    if "paint" in name or "stain" in name:
        min_delta = 13.0
        sigma_mult = 3.0
    elif "hole" in name:
        min_delta = 10.0
        sigma_mult = 2.6
    elif "fold" in name:
        min_delta = 7.0
        sigma_mult = 2.2
    else:
        min_delta = 10.0
        sigma_mult = 2.7

    threshold = max(
        min_delta,
        ring_median + sigma_mult * max(robust_sigma, 1.0),
    )
    threshold = min(threshold, 55.0)

    roi_lab = frame_lab[y1:y2, x1:x2].astype(np.float32)
    delta = np.linalg.norm(roi_lab - reference, axis=2)

    candidate = (delta >= threshold) & roi_piece

    # Holes are commonly much darker than local leather even when their chroma
    # is similar, so give darkness an explicit path into the mask.
    if "hole" in name:
        dark_threshold = reference[0] - max(10.0, 1.5 * robust_sigma)
        candidate |= (roi_lab[:, :, 0] <= dark_threshold) & roi_piece

    # Folds may be mainly a luminance crease rather than a hue change.
    if "fold" in name:
        light_delta = np.abs(roi_lab[:, :, 0] - reference[0])
        candidate |= (
            light_delta >= max(7.0, threshold * 0.42)
        ) & roi_piece

    local = candidate.astype(np.uint8) * 255
    local = cv2.morphologyEx(
        local,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    local = cv2.morphologyEx(
        local,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )

    # For compact defects keep the strongest connected component.  This removes
    # normal leather texture elsewhere inside the YOLO box.
    if "paint" in name or "stain" in name or "hole" in name:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(
            (local > 0).astype(np.uint8),
            connectivity=8,
        )

        if n > 1:
            best_label = 0
            best_area = 0
            cx = box_w // 2
            cy = box_h // 2

            center_label = int(labels[min(cy, box_h - 1), min(cx, box_w - 1)])
            if center_label > 0:
                center_area = int(stats[center_label, cv2.CC_STAT_AREA])
                if center_area >= DEFECT_MASK_MIN_COMPONENT_PX:
                    best_label = center_label
                    best_area = center_area

            if best_label == 0:
                for label in range(1, n):
                    area = int(stats[label, cv2.CC_STAT_AREA])
                    if area > best_area:
                        best_area = area
                        best_label = label

            if best_label > 0 and best_area >= DEFECT_MASK_MIN_COMPONENT_PX:
                local = (labels == best_label).astype(np.uint8) * 255
            else:
                local[:] = 0

    local[~roi_piece] = 0

    area_px = cv2.countNonZero(local)
    fill = area_px / float(max(box_area, 1))

    # A result that is nearly empty or nearly the whole box means the local
    # colour estimate was unreliable.  Use a shape-aware fallback rather than
    # returning to the old full-rectangle area calculation.
    if "paint" in name or "stain" in name or "hole" in name:
        if fill < 0.08 or fill > 0.92:
            local = _fallback_defect_roi_mask(box_w, box_h, class_name)
            local[~roi_piece] = 0
            return local, f"fallback:fill={fill:.2f}"

    if "fold" in name and fill > 0.92:
        local = _fallback_defect_roi_mask(box_w, box_h, class_name)
        local[~roi_piece] = 0
        return local, f"fallback:fill={fill:.2f}"

    return local, f"local:thr={threshold:.1f},fill={fill:.2f}"


def detect_defects(frame, contour=None):
    """
    Run YOLO for localization, then estimate real defect pixels inside each box.

    The old implementation filled every YOLO box as a solid rectangle.  A round
    paint stain therefore counted the empty corners of its box as defect area.
    This version uses the box only as an ROI and measures a local pixel mask.
    """
    t0 = time.perf_counter()

    empty_mask = np.zeros(
        (FRAME_HEIGHT, FRAME_WIDTH),
        dtype=np.uint8,
    )

    if contour is None:
        return [], 0, 0.0, empty_mask

    results = model(
        frame,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        verbose=False,
    )

    detections = []
    defect_mask = empty_mask
    piece_mask = cv_engine.piece_mask(contour)
    frame_lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            x1 = max(0, min(FRAME_WIDTH - 1, x1))
            y1 = max(0, min(FRAME_HEIGHT - 1, y1))
            x2 = max(x1 + 1, min(FRAME_WIDTH, x2))
            y2 = max(y1 + 1, min(FRAME_HEIGHT, y2))

            box_w = x2 - x1
            box_h = y2 - y1

            if box_w < MIN_DEFECT_WIDTH or box_h < MIN_DEFECT_HEIGHT:
                continue

            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            name = CLASS_NAMES[cls_id]

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            if cv2.pointPolygonTest(
                contour,
                (float(cx), float(cy)),
                False,
            ) < 0:
                continue

            detections.append(
                (
                    name,
                    cls_id,
                    x1,
                    y1,
                    x2,
                    y2,
                    conf,
                    cx,
                    cy,
                )
            )

            roi_mask, area_method = _estimate_defect_roi_mask(
                frame_lab,
                piece_mask,
                name,
                x1,
                y1,
                x2,
                y2,
            )

            existing = defect_mask[y1:y2, x1:x2]
            defect_mask[y1:y2, x1:x2] = cv2.bitwise_or(
                existing,
                roi_mask,
            )

            masked_px = cv2.countNonZero(roi_mask)
            box_px = box_w * box_h

            print(
                f"[AREA] {name} conf={conf:.2f} "
                f"box={box_px}px mask={masked_px}px "
                f"fill={masked_px / max(box_px, 1):.1%} "
                f"method={area_method}",
                flush=True,
            )

    # Union with the refined leather mask so no background pixel contributes to
    # the numerator, and overlapping defect detections are counted only once.
    defect_mask = cv2.bitwise_and(defect_mask, piece_mask)
    total_defect_px = cv2.countNonZero(defect_mask)

    inference_ms = (time.perf_counter() - t0) * 1000.0

    return (
        detections,
        total_defect_px,
        inference_ms,
        defect_mask,
    )

def calculate_steps(defect_x):
    adjusted_x = defect_x + X_OFFSET_PX
    pixel_delta = adjusted_x - REF_X1_PX
    target_steps = REF_STEPS1 + (pixel_delta * STEPS_PER_PIXEL)
    return int(max(0, target_steps))


def set_projector_frame(frame):
    """Thread-safe update of the image shown by the projector window."""
    global projector_frame

    with projector_lock:
        projector_frame = frame.copy()


def clear_projector():
    """Set projector output to a completely black frame."""
    set_projector_frame(projector_mapper.create_blank())


def project_detections(detections):
    """Create a frozen projector overlay from accepted YOLO detections."""
    if not projector_mapper.is_calibrated():
        print("[PROJECTOR] Cannot project: calibration unavailable.")
        clear_projector()
        return False

    overlay = projector_mapper.create_overlay(detections)
    set_projector_frame(overlay)
    return True


# =====================================================
# Arduino Communication
# =====================================================

def connect_arduino(baud=9600, timeout=1):
    candidates = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))

    if not candidates:
        print("[SERIAL] No Arduino detected - vision testing mode.")
        return None

    for port in candidates:
        try:
            ser = serial.Serial(port, baud, timeout=timeout)
            time.sleep(2)
            print(f"[SERIAL] Connected on {port}")
            return ser
        except (serial.SerialException, OSError) as exc:
            print(f"[SERIAL] {port} unavailable: {exc}")

    return None


arduino = connect_arduino()


# Startup Homing Routine (kept unchanged)
if arduino is not None:
    print("\n[SYSTEM] Running startup safety homing...")
    arduino.reset_input_buffer()
    arduino.write(b"HOME\n")

    while True:
        if arduino.in_waiting > 0:
            response = arduino.readline().decode("utf-8").strip()

            if response == "HOMED":
                print("[SUCCESS] Marker homed. Starting conveyor...")
                time.sleep(0.5)
                arduino.write(b"START\n")
                break

            elif "ERROR" in response:
                print(f"[HARDWARE FAULT] {response}")
                break


# =====================================================
# Camera Initialization
# =====================================================

picam2 = Picamera2()
picam2.configure(
    picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (FRAME_WIDTH, FRAME_HEIGHT)}
    )
)
picam2.start()
time.sleep(2)   # let auto-exposure settle - BELT MUST BE EMPTY HERE

if LOCK_EXPOSURE:
    try:
        meta = picam2.capture_metadata()
        controls = {
            "AeEnable": False,
            "AwbEnable": False,
            "ExposureTime": int(meta["ExposureTime"] * EXPOSURE_SCALE),
            "AnalogueGain": float(meta["AnalogueGain"]),
        }
        if "ColourGains" in meta:
            controls["ColourGains"] = tuple(meta["ColourGains"])
        picam2.set_controls(controls)
        time.sleep(1.0)   # a few frames for the locked settings to apply
        print(
            f"[CAMERA] Exposure locked: {controls['ExposureTime']} us, "
            f"gain {controls['AnalogueGain']:.2f}"
        )
    except Exception as exc:
        print(f"[CAMERA] Could not lock exposure ({exc}); running on auto.")

# Background Belt Calibration (empty belt, locked exposure)
init_frame = picam2.capture_array()
cv_engine.calibrate_belt(init_frame)


def publish_screening_frame(frame, contour, area, grade, reason, status, fraction):
    """Publish the return workflow through the existing /stats and video routes."""
    global output_frame_bytes, latest_stats
    if contour is not None:
        cv2.drawContours(frame, [contour], -1, (0, 165, 255), 2)
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 165, 255), 3)
        cv2.putText(frame, grade, (x, max(25, y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
    for i, text in enumerate((status, f"GRADE: {grade}",
                              f"SHAPE MATCH: {fraction:.0%}", reason)):
        cv2.putText(frame, text, (25, 50 + 40 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
    latest_stats = {
        "grade": grade, "ratio": 0.0, "reason": reason,
        # Keep pixel values for internal/debug compatibility.
        "piece_area": int(area),
        # Human-readable physical units for the dashboard.
        "piece_area_cm2": round(pixels_to_cm2(area), 1),
        "defect_pixels": 0,
        "defect_area_cm2": 0.0,
        "pixels_per_cm2": round(PIXELS_PER_CM2, 3),
        "status": status,
        "projector_status": "OFF", "projected_defects": 0,
        "servo_state": servo_state, "inference_ms": 0.0,
        "shape_match": round(fraction, 3), "color_match": round(fraction, 3), "defect_evaluated": False,
    }
    ok, buffer = cv2.imencode(".jpg", cv2.resize(frame, (720, 822)),
                             [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ok:
        with frame_lock:
            output_frame_bytes = buffer.tobytes()


# =====================================================
# Main Vision / Hardware Worker
# =====================================================

def inspection_worker():
    """Continuous vision, projector, grading and mechanical-control loop."""
    global is_currently_stopped, pending_marks
    global is_center_paused, pause_start_time, has_paused_for_current_hide
    global projection_zone_clear_frames
    global projection_active, projection_captured, frozen_projection_detections
    global segregation_sent_for_current_hide, servo_state
    global current_hide_id, current_inspection_saved
    global latest_stats, output_frame_bytes

    tracker = DefectTracker()
    marked_defect_ids = set()
    queued_defect_ids = set()
    current_mark = None

    # Marker memory survives short YOLO dropouts near the top of the camera.
    # Each value stores the last reliable X/Y plus an estimated upward conveyor
    # speed in camera pixels/second.
    marker_memory = {}

    # Time-based hide-exit reset. A frame counter is unreliable because the
    # effective FPS changes with YOLO inference load.
    no_leather_since = None
    hide_exit_reset_done = False

    # Diverter safety hold:
    # After a classified leather fully leaves the camera, the current GOOD/BAD
    # diverter side is protected for another LEATHER_EXIT_RESET_DELAY seconds.
    # If the next leather needs the opposite side during this window, it is held
    # stopped in the inspection zone until the hold expires.
    segregation_hold_until = 0.0
    segregation_exit_hold_started = False
    frozen_segregation_grade = "NO LEATHER"
    last_hold_report_second = None

    color_accepted = False
    last_marker_diagnostic = 0.0
    last_marker_diagnostic_state = None
    frame_count = 0
    last_detections = []
    last_defect_area_mask = np.zeros(
        (FRAME_HEIGHT, FRAME_WIDTH),
        dtype=np.uint8,
    )
    current_defect_px = 0

    current_grade = "NO LEATHER"
    current_ratio = 0.0
    current_reason = "empty belt"
    last_inference_ms = 0.0
    last_save_attempt = 0.0

    while True:
        frame = picam2.capture_array()
        frame_count += 1

        # Tracks whether YOLO ran on THIS frame. Projection is only frozen
        # from a fresh detection frame after the conveyor has settled.
        detection_updated_this_frame = False

        # -------------------------------------------------
        # 1. Leather Segmentation
        # -------------------------------------------------
        contour, piece_area = cv_engine.segment_leather(frame)
        leather_in_middle_zone = False

        if contour is not None:
            # This may be the current hide or a following hide. Do NOT cancel
            # segregation_hold_until here; once the previous leather has left
            # the camera, its extra 5-second diverter hold must finish even if
            # another leather becomes visible.
            no_leather_since = None
            hide_exit_reset_done = False

            cv2.drawContours(frame, [contour], -1, (0, 255, 0), 2)
            lx, ly, lw, lh = cv2.boundingRect(contour)

            if current_hide_id is None:
                current_hide_id = time.strftime("HIDE-%m%d-%H%M%S")
                current_inspection_saved = False
                print(f"[SAVE] Hide detected: {current_hide_id}", flush=True)

            if ly <= MIDDLE_Y_MAX and (ly + lh) >= MIDDLE_Y_MIN:
                leather_in_middle_zone = True

        else:
            now = time.time()

            # Start the ordinary hide-exit cleanup timer.
            if no_leather_since is None:
                no_leather_since = now
                hide_exit_reset_done = False

            # Start the diverter safety hold only after THIS leather has already
            # received a real GOOD/BAD decision.
            if (
                segregation_sent_for_current_hide
                and not segregation_exit_hold_started
            ):
                segregation_hold_until = now + LEATHER_EXIT_RESET_DELAY
                segregation_exit_hold_started = True

                print(
                    f"[SEGREGATION] Leather left camera. Locking "
                    f"{servo_state} position for another "
                    f"{LEATHER_EXIT_RESET_DELAY:.1f}s."
                )

            leather_absent_for = now - no_leather_since

            # Clear finished-hide tracking after the usual absence delay.
            # IMPORTANT: this cleanup does NOT move or re-home the diverter.
            if (
                not hide_exit_reset_done
                and leather_absent_for >= LEATHER_EXIT_RESET_DELAY
                and not is_currently_stopped
                and not is_center_paused
            ):
                color_accepted = False
                tracker.reset()
                marked_defect_ids.clear()
                queued_defect_ids.clear()
                marker_memory.clear()
                pending_marks = []
                current_mark = None
                last_detections = []

                projection_active = False
                projection_captured = False
                frozen_projection_detections = []
                current_hide_id = None
                current_inspection_saved = False

                hide_exit_reset_done = True
                clear_projector()

                print(
                    "[SYSTEM] Previous hide tracking cleared."
                )

        # -------------------------------------------------
        # Projection re-arm logic
        # -------------------------------------------------
        # The old version only reset has_paused_for_current_hide when
        # contour became None. If segmentation kept seeing any part of the
        # leather (or belt noise), the projector stayed permanently disarmed.
        #
        # Now we re-arm after the CENTER INSPECTION ZONE itself has been clear
        # for several consecutive frames. This lets the next leather piece
        # trigger projection without restarting app5.py.
        if not leather_in_middle_zone and not is_center_paused:
            projection_zone_clear_frames += 1

            if projection_zone_clear_frames >= PROJECTION_REARM_CLEAR_FRAMES:
                if has_paused_for_current_hide:
                    print("[PROJECTOR] Inspection zone clear. Armed for next hide.")

                has_paused_for_current_hide = False
                projection_zone_clear_frames = PROJECTION_REARM_CLEAR_FRAMES

        else:
            projection_zone_clear_frames = 0

        # -------------------------------------------------
        # 2. Auto-Pause for Projection Inspection
        # -------------------------------------------------
        if (
            leather_in_middle_zone
            and not has_paused_for_current_hide
            and not is_currently_stopped
            and not is_center_paused
        ):
            print("[PI] Object entered inspection area. Checking shape...")
            clear_projector()
            accepted = screen_or_return(
                arduino, picam2, cv_engine, publish_screening_frame,
                resume_return_event,
            )
            if not accepted:
                # Rejected/uncertain object was automatically returned, or a manual fault recovery completed.
                color_accepted = False
                tracker.reset()
                marked_defect_ids.clear()
                queued_defect_ids.clear()
                marker_memory.clear()
                pending_marks = []
                current_mark = None
                last_detections = []
                color_accepted = False
                has_paused_for_current_hide = False
                projection_zone_clear_frames = 0
                projection_active = False
                projection_captured = False
                frozen_projection_detections = []
                segregation_sent_for_current_hide = False
                segregation_exit_hold_started = False
                frozen_segregation_grade = "NO LEATHER"
                no_leather_since = None
                current_grade, current_ratio, current_reason = "NO LEATHER", 0.0, "ready"
                current_hide_id = None
                current_inspection_saved = False
                continue
            color_accepted = True
            # Never reuse the moving / annotated frame from before screening.
            frame = picam2.capture_array()
            contour, piece_area = cv_engine.segment_leather(frame)
            is_center_paused = True
            has_paused_for_current_hide = True
            projection_zone_clear_frames = 0
            pause_start_time = time.time()

            projection_active = False
            projection_captured = False
            frozen_projection_detections = []

            # Arm segregation for this NEW leather piece.
            #
            # Do NOT reset servo_state or segregation_hold_until here.
            # If the previous leather still owns the 5-second safety hold and
            # this new leather needs the opposite bin, this hide remains paused
            # until the previous hold expires.
            segregation_sent_for_current_hide = False
            segregation_exit_hold_started = False
            frozen_segregation_grade = "NO LEATHER"
            last_hold_report_second = None

            clear_projector()

            send_to_arduino("STOP")

        # -------------------------------------------------
        # 3. YOLO Object Detection - LOW LATENCY
        # -------------------------------------------------
        # OLD behavior:
        #   YOLO ran only every second loop, but last_detections was drawn and
        #   used by the marker on the newer frame. The box therefore visibly
        #   trailed the moving leather and the marker sometimes acted on an old
        #   Y coordinate.
        #
        # NEW behavior:
        #   Run YOLO on every frame while the leather is moving. During
        #   projection or physical stamping the leather is stationary, so
        #   reusing the last boxes is safe and saves CPU.
        # Preview detections before color acceptance; hardware actions remain
        # gated separately. Preview boxes are not a GOOD/BAD decision.
        run_yolo_now = (
            not projection_active
            and not is_currently_stopped
        )

        if not color_accepted:
            current_grade = "CHECKING SHAPE" if contour is not None else "NO LEATHER"
            current_ratio = 0.0
            current_reason = "Awaiting shape inspection zone" if contour is not None else "empty belt"

        if run_yolo_now:
            (
                last_detections,
                total_defect_px,
                last_inference_ms,
                last_defect_area_mask,
            ) = detect_defects(frame, contour)

            current_defect_px = total_defect_px
            detection_updated_this_frame = True

            if color_accepted:
                current_grade, current_ratio, current_reason = cv_engine.grade_piece(
                    [(d[0], 0) for d in last_detections],
                    piece_area,
                    manual_defect_px=total_defect_px,
                )

                print(
                    f"[AREA TOTAL] "
                    f"leather={piece_area:.0f}px / {pixels_to_cm2(piece_area):.1f}cm^2 "
                    f"defect={total_defect_px}px / {pixels_to_cm2(total_defect_px):.1f}cm^2 "
                    f"coverage={current_ratio:.2f}%",
                    flush=True,
                )

        # -------------------------------------------------
        # 4. Freeze Projection + Make One Stable Grade
        # -------------------------------------------------
        if is_center_paused and not projection_captured:
            elapsed = time.time() - pause_start_time

            if elapsed >= PROJECTION_SETTLE_DELAY and detection_updated_this_frame:
                projectable = []

                # Keep only detections whose center lies on the segmented hide.
                if contour is not None:
                    for detection in last_detections:
                        cx = detection[7]
                        cy = detection[8]

                        inside_leather = cv2.pointPolygonTest(
                            contour,
                            (float(cx), float(cy)),
                            False,
                        )

                        if inside_leather >= 0:
                            mapped = projector_mapper.transform_point(cx, cy)

                            if mapped is not None:
                                px, py = mapped
                                if (
                                    0 <= px < PROJECTOR_WIDTH
                                    and 0 <= py < PROJECTOR_HEIGHT
                                ):
                                    projectable.append(detection)

                frozen_projection_detections = list(projectable)

                # Freeze the stopped-frame grade. The segregation gate will use
                # this exact decision even if it has to wait for the previous
                # leather's 5-second diverter hold to finish.
                frozen_segregation_grade = current_grade

                if (
                    current_hide_id is not None
                    and not current_inspection_saved
                    and frozen_segregation_grade in ("GOOD", "BAD")
                    and piece_area > 0
                ):
                    last_save_attempt = time.monotonic()
                    print(f"[SAVE] Saving inspection for {current_hide_id}", flush=True)
                    current_inspection_saved = save_inspection_record(
                        current_hide_id,
                        list(last_detections),
                        frozen_segregation_grade,
                        current_ratio,
                        piece_area,
                        "BELT: PAUSED IN CENTER",
                        frame,
                    )

                print(
                    f"[SEGREGATION] Frozen grade = "
                    f"{frozen_segregation_grade}."
                )

                print(
                    f"[PROJECTOR] Frozen "
                    f"{len(frozen_projection_detections)} defect(s)."
                )

                if frozen_projection_detections:
                    if project_detections(frozen_projection_detections):
                        projection_active = True
                        print("[PROJECTOR] Overlay ON.")
                else:
                    clear_projector()
                    print("[PROJECTOR] No projectable defect found.")

                projection_captured = True

        if (
            is_center_paused
            and projection_captured
            and current_hide_id is not None
            and not current_inspection_saved
            and frozen_segregation_grade in ("GOOD", "BAD")
            and piece_area > 0
            and time.monotonic() - last_save_attempt >= 2.0
        ):
            last_save_attempt = time.monotonic()
            current_inspection_saved = save_inspection_record(
                current_hide_id,
                list(last_detections),
                frozen_segregation_grade,
                current_ratio,
                piece_area,
                "BELT: PAUSED IN CENTER",
                frame,
            )

        # -------------------------------------------------
        # 4B. Safe Segregation Command
        # -------------------------------------------------
        # This is deliberately separate from projection capture. If a new hide
        # needs the opposite bin while the previous hide is still inside its
        # 5-second exit hold, the conveyor stays stopped and this block retries
        # automatically until it is safe to switch the diverter.
        if (
            is_center_paused
            and projection_captured
            and not segregation_sent_for_current_hide
        ):
            desired_grade = frozen_segregation_grade

            if desired_grade in ("GOOD", "BAD"):
                now = time.time()

                # If the diverter is already on the required side, no movement
                # is needed and the previous leather remains protected.
                if desired_grade == servo_state:
                    segregation_sent_for_current_hide = True
                    print(
                        f"[SEGREGATION] {desired_grade} requested; "
                        f"diverter already {servo_state}. No movement."
                    )

                # Opposite side requested: protect the previous leather until
                # its 5-second exit hold has fully expired.
                elif now < segregation_hold_until:
                    remaining = segregation_hold_until - now
                    report_second = int(remaining + 0.999)

                    if report_second != last_hold_report_second:
                        last_hold_report_second = report_second
                        print(
                            f"[SEGREGATION] Waiting {remaining:.1f}s before "
                            f"switching {servo_state} -> {desired_grade}. "
                            f"Conveyor remains paused."
                        )

                else:
                    send_to_arduino(f"SEG:{desired_grade}")
                    segregation_sent_for_current_hide = True
                    servo_state = desired_grade
                    last_hold_report_second = None

                    print(
                        f"[SEGREGATION] Safe to switch -> {desired_grade}. "
                        f"Arduino will rotate the 360 servo for 1.5s and stop."
                    )

            else:
                print(
                    "[SEGREGATION] Frozen grade is not GOOD/BAD; "
                    f"diverter remains {servo_state}."
                )

        # -------------------------------------------------
        # 5. End Projection Pause / Resume Conveyor
        # -------------------------------------------------
        if is_center_paused and (time.time() - pause_start_time >= PAUSE_DURATION):

            valid_frozen_grade = frozen_segregation_grade in ("GOOD", "BAD")

            # If an opposite-bin change is still waiting for the previous
            # leather's 5-second hold, DO NOT resume the conveyor yet.
            if valid_frozen_grade and not segregation_sent_for_current_hide:
                pass

            else:
                print("[PI] Projection inspection finished. Resuming conveyor...")

                clear_projector()
                projection_active = False
                projection_captured = False
                is_center_paused = False

                send_to_arduino("START")

        # -------------------------------------------------
        # 6. Defect Tracking for Mechanical Marker
        # -------------------------------------------------
        # Only feed the tracker genuinely NEW YOLO results.
        if not color_accepted:
            tracked_defects = {}
        elif detection_updated_this_frame:
            tracked_defects = tracker.update(last_detections)
        else:
            tracked_defects = tracker.current_positions()

        # -------------------------------------------------
        # 7. Camera Visual Annotations
        # -------------------------------------------------
        for name, cls_id, x1, y1, x2, y2, conf, cx, cy in last_detections:
            color = get_class_color(cls_id)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

            label_text = f"{name} {conf:.2f}"
            (text_w, text_h), baseline = cv2.getTextSize(
                label_text,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                2,
            )
            label_y = max(y1 - 8, text_h + 10)

            cv2.rectangle(
                frame,
                (x1, label_y - text_h - 4),
                (x1 + text_w + 4, label_y + baseline),
                color,
                cv2.FILLED,
            )

            cv2.putText(
                frame,
                label_text,
                (x1 + 2, label_y - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                2,
            )

        # Draw the ACTUAL pixels being used for the coverage numerator.
        # White contours are the measured defect-area mask; the coloured YOLO
        # rectangles remain visible only as localization boxes.
        if DEFECT_MASK_DRAW and last_defect_area_mask is not None:
            area_contours, _ = cv2.findContours(
                last_defect_area_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            if area_contours:
                cv2.drawContours(
                    frame,
                    area_contours,
                    -1,
                    (255, 255, 255),
                    2,
                )

        # -------------------------------------------------
        # 8. Predictive Mechanical Marker Trigger
        # -------------------------------------------------
        # The physical marker remains CENTER_Y_MIN..CENTER_Y_MAX (100..220).
        # We arm earlier because the latest real run showed YOLO centres moving
        # 417 -> 333 -> 252 and then disappearing before reaching that band.
        #
        # Unlike the old logic, losing the box near the top does NOT erase the
        # target.  We retain its X position and recent conveyor speed, predict
        # when it reaches the EARLY STOP calibration point MARK_TARGET_Y, then
        # STOP + MARK using the remembered X.  The physical yellow marker band
        # itself remains CENTER_Y_MIN..CENTER_Y_MAX (100..220).
        marker_now = time.monotonic()

        if color_accepted and detection_updated_this_frame:
            for tid, (cx, cy) in tracked_defects.items():
                if tid in marked_defect_ids or tid in queued_defect_ids:
                    continue

                if not (CENTER_X_MIN <= cx <= CENTER_X_MAX):
                    continue

                # There is no reason to remember defects that are still far
                # below the marker.  They will be added once they approach.
                if cy > MARK_MEMORY_Y_MAX:
                    continue

                previous = marker_memory.get(tid)
                speed_px_s = None

                if previous is not None:
                    dt = marker_now - previous["seen_time"]
                    upward_pixels = previous["y"] - cy

                    # Positive speed means the defect is moving upward in the
                    # camera image (toward smaller Y / toward the marker).
                    if dt > 0.05 and upward_pixels > 0:
                        instant_speed = upward_pixels / dt
                        old_speed = previous.get("speed_px_s")

                        if old_speed is None:
                            speed_px_s = instant_speed
                        else:
                            # Light smoothing makes one noisy YOLO centre less
                            # able to shift the predicted arrival time.
                            speed_px_s = (
                                0.65 * old_speed
                                + 0.35 * instant_speed
                            )
                    else:
                        speed_px_s = previous.get("speed_px_s")

                marker_memory[tid] = {
                    "x": cx,
                    "y": cy,
                    "seen_time": marker_now,
                    "speed_px_s": speed_px_s,
                }

                speed_text = (
                    f"{speed_px_s:.1f}px/s"
                    if speed_px_s is not None
                    else "learning speed"
                )

                if cy <= MARK_ARM_Y:
                    print(
                        f"[MARKER ARM] ID {tid} x={cx} y={cy} "
                        f"speed={speed_text}",
                        flush=True,
                    )

        # Keep remembered targets through short YOLO dropouts, but never keep a
        # stale target indefinitely or carry it into the next leather piece.
        for tid in list(marker_memory.keys()):
            if tid in marked_defect_ids:
                marker_memory.pop(tid, None)
                continue

            age = marker_now - marker_memory[tid]["seen_time"]
            if age > MARK_MEMORY_TIMEOUT_SEC and tid not in queued_defect_ids:
                print(
                    f"[MARKER] Dropping stale remembered ID {tid} "
                    f"after {age:.1f}s.",
                    flush=True,
                )
                marker_memory.pop(tid, None)

        # Build candidates from MEMORY, not only from this exact YOLO frame.
        # This is the key fix for boxes that disappear around Y=252.
        marker_candidates = []

        if color_accepted:
            for tid, remembered in marker_memory.items():
                if tid in marked_defect_ids or tid in queued_defect_ids:
                    continue

                cx = remembered["x"]
                cy = remembered["y"]

                if cy > MARK_ARM_Y:
                    continue

                speed_px_s = remembered.get("speed_px_s")

                if speed_px_s is None or speed_px_s < MARK_MIN_SPEED_PX_S:
                    speed_px_s = MARK_FALLBACK_SPEED_PX_S

                # If the last box is already at/past the target, trigger now.
                eta_sec = max(
                    0.0,
                    (cy - MARK_TARGET_Y) / speed_px_s,
                )

                if eta_sec <= MARK_MAX_WAIT_SEC:
                    marker_candidates.append(
                        (tid, cx, cy, speed_px_s, eta_sec)
                    )

        diagnostic_state = (
            color_accepted,
            contour is not None,
            len(last_detections),
            bool(marker_candidates),
            is_center_paused,
            is_currently_stopped,
            len(marker_memory),
        )
        diagnostic_now = time.monotonic()

        if (color_accepted or contour is not None) and (
            diagnostic_now - last_marker_diagnostic >= 1.0
            or diagnostic_state != last_marker_diagnostic_state
        ):
            positions = ", ".join(
                f"{tid}:({cx},{cy})"
                for tid, (cx, cy) in tracked_defects.items()
            ) or "none"

            memory_positions = ", ".join(
                f"{tid}:({m['x']},{m['y']})"
                for tid, m in marker_memory.items()
            ) or "none"

            print(
                f"[MARKER CHECK] accepted={color_accepted} "
                f"leather_visible={contour is not None} area={piece_area:.0f} "
                f"fresh={detection_updated_this_frame} boxes={len(last_detections)} "
                f"positions=[{positions}] memory=[{memory_positions}] "
                f"physical_y={CENTER_Y_MIN}..{CENTER_Y_MAX} "
                f"arm_y<={MARK_ARM_Y} early_stop_y={MARK_TARGET_Y} "
                f"ready={len(marker_candidates)} "
                f"projection_pause={is_center_paused} "
                f"marking={is_currently_stopped} "
                f"marked={len(marked_defect_ids)} "
                f"queued={len(queued_defect_ids)} "
                f"inference_ms={last_inference_ms:.0f}",
                flush=True,
            )

            last_marker_diagnostic = diagnostic_now
            last_marker_diagnostic_state = diagnostic_state

        if (
            color_accepted
            and marker_candidates
            and not is_currently_stopped
            and not is_center_paused
        ):
            # Smallest Y is physically the most advanced defect because the belt
            # moves upward in the image.
            primary = min(
                marker_candidates,
                key=lambda item: item[2],
            )

            primary_id, _, primary_y, primary_speed, primary_eta = primary

            # Mark only defects on approximately the same Y row during this
            # conveyor stop.  Their remembered X coordinates remain independent.
            same_row_hits = []

            for tid, remembered in marker_memory.items():
                if tid in marked_defect_ids or tid in queued_defect_ids:
                    continue

                if abs(remembered["y"] - primary_y) <= SAME_ROW_TOLERANCE:
                    same_row_hits.append(
                        (tid, remembered["x"], remembered["y"])
                    )

            same_row_hits.sort(key=lambda item: item[1])

            if same_row_hits:
                pending_marks = list(same_row_hits)

                for tid, _, _ in pending_marks:
                    queued_defect_ids.add(tid)

                # Stop slightly before the calculated target to compensate for
                # serial + motor stopping latency.  While waiting here we skip a
                # whole extra YOLO inference, which is exactly what previously
                # caused the defect to vanish before the marker decision.
                wait_before_stop = max(
                    0.0,
                    primary_eta - MARK_EARLY_STOP_LEAD_SEC,
                )

                print(
                    f"\n[MARKER] ID {primary_id} early-stop prediction armed. "
                    f"last_y={primary_y}, speed={primary_speed:.1f}px/s, "
                    f"stop_target_y={MARK_TARGET_Y}, ETA={primary_eta:.2f}s, "
                    f"stop_in={wait_before_stop:.2f}s.",
                    flush=True,
                )

                if wait_before_stop > 0:
                    time.sleep(wait_before_stop)

                # From this point the system owns the belt for physical marking.
                is_currently_stopped = True
                send_to_arduino("STOP")

                if MARK_BELT_SETTLE_DELAY > 0:
                    time.sleep(MARK_BELT_SETTLE_DELAY)

                print(
                    f"[MARKER] Early stop point reached (Y={MARK_TARGET_Y}). "
                    f"Stopping for {len(pending_marks)} defect(s).",
                    flush=True,
                )

                current_mark = pending_marks.pop(0)
                tid, mark_x, mark_y = current_mark

                print(
                    f"[MARKER] Marking ID {tid} using remembered "
                    f"X={mark_x} (last seen Y={mark_y}).",
                    flush=True,
                )

                send_to_arduino(
                    f"MARK:{calculate_steps(mark_x)}"
                )

        # -------------------------------------------------
        # 9. Reliable Mechanical Marker Queue
        # -------------------------------------------------
        #
        # Do not declare a defect marked until the hardware reports DONE.
        if (
            is_currently_stopped
            and arduino is not None
            and arduino.in_waiting > 0
        ):
            try:
                response = arduino.readline().decode(
                    "utf-8"
                ).strip()

                if response == "DONE":
                    if current_mark is not None:
                        finished_id = current_mark[0]

                        marked_defect_ids.add(
                            finished_id
                        )
                        queued_defect_ids.discard(
                            finished_id
                        )
                        marker_memory.pop(
                            finished_id,
                            None,
                        )

                        print(
                            f"[MARKER] DONE ID {finished_id}."
                        )

                        current_mark = None

                    if pending_marks:
                        current_mark = pending_marks.pop(0)

                        tid, mark_x, mark_y = current_mark

                        print(
                            f"[MARKER] Next ID {tid} "
                            f"at camera ({mark_x}, {mark_y})."
                        )

                        send_to_arduino(
                            f"MARK:{calculate_steps(mark_x)}"
                        )

                    else:
                        print(
                            "[PI] Current Y-row marked. "
                            "Resuming conveyor..."
                        )

                        send_to_arduino("START")
                        is_currently_stopped = False

            except Exception as exc:
                print(
                    f"[SERIAL] Marker queue read error: {exc}"
                )

        # -------------------------------------------------
        # 10. Metrics / Web Display
        # -------------------------------------------------
        if is_currently_stopped:
            box_color = (0, 0, 255)
            status_text = (
                f"BELT: STOPPED (MARKING {len(pending_marks) + 1} DEFECTS...)"
            )

        elif is_center_paused:
            box_color = (255, 0, 255)
            time_left = max(
                0.0,
                PAUSE_DURATION - (time.time() - pause_start_time),
            )

            if projection_active:
                status_text = (
                    f"BELT: PAUSED - PROJECTING "
                    f"{len(frozen_projection_detections)} DEFECT(S) "
                    f"({time_left:.1f}s)"
                )
            else:
                status_text = (
                    f"BELT: PAUSED IN CENTER "
                    f"({time_left:.1f}s INSPECTION)"
                )

        else:
            box_color = (0, 255, 255)
            status_text = "BELT: RUNNING"

        grade_color = (
            (0, 255, 0)
            if current_grade == "GOOD"
            else (0, 0, 255)
            if current_grade == "BAD"
            else (180, 180, 180)
        )

        if projection_active:
            projector_status = "PROJECTING"
        elif projector_mapper.is_calibrated():
            projector_status = "READY"
        else:
            projector_status = "NOT CALIBRATED"

        latest_stats = {
            "grade": current_grade,
            "ratio": round(current_ratio, 1),
            "reason": current_reason,

            # Raw/calculation values retained for diagnostics.
            "piece_area": int(piece_area),
            "defect_pixels": int(current_defect_px),

            # Physical area values shown on the dashboard.
            "piece_area_cm2": round(pixels_to_cm2(piece_area), 1),
            "defect_area_cm2": round(pixels_to_cm2(current_defect_px), 1),
            "pixels_per_cm2": round(PIXELS_PER_CM2, 3),

            "status": status_text,
            "projector_status": projector_status,
            "projected_defects": len(frozen_projection_detections),
            "servo_state": servo_state,
            "inference_ms": round(last_inference_ms, 1),
            "defect_count": len(last_detections),
            "hide_id": current_hide_id,
            "inspection_saved": current_inspection_saved,
            "camera_connected": True,
            "updated_at": time.time(),
            "performance": performance_snapshot(last_inference_ms),
            "segmentation_raw_area": int(getattr(cv_engine, "last_raw_area", 0)),
            "segmentation_refined_area": int(getattr(cv_engine, "last_piece_area", piece_area)),
        }

        # Calibrated projector footprint in the camera view (cyan).
        # This makes it easy to visually confirm where the physical projector
        # can place overlays.
        if PROJECTOR_CAMERA_POLYGON is not None:
            cv2.polylines(
                frame,
                [PROJECTOR_CAMERA_POLYGON],
                True,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )

        # Violet stop/trigger band. Its lower edge automatically matches the
        # lowest edge of the calibrated projector footprint.
        cv2.rectangle(
            frame,
            (0, MIDDLE_Y_MIN),
            (FRAME_WIDTH, MIDDLE_Y_MAX),
            (255, 0, 255),
            2,
        )

        cv2.rectangle(
            frame,
            (CENTER_X_MIN, CENTER_Y_MIN),
            (CENTER_X_MAX, CENTER_Y_MAX),
            box_color,
            3,
        )

        # Orange software-only arm line.  The physical marker band above is
        # unchanged; this line simply shows where arrival prediction begins.
        cv2.line(
            frame,
            (CENTER_X_MIN, MARK_ARM_Y),
            (CENTER_X_MAX, MARK_ARM_Y),
            (0, 165, 255),
            2,
        )
        cv2.putText(
            frame,
            "MARKER PRE-TRIGGER",
            (CENTER_X_MIN + 10, MARK_ARM_Y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2,
        )

        # Blue calibration line: this is where Python now sends STOP.  The
        # physical marker is still the yellow 100..220 band above it.
        cv2.line(
            frame,
            (CENTER_X_MIN, MARK_TARGET_Y),
            (CENTER_X_MAX, MARK_TARGET_Y),
            (255, 0, 0),
            2,
        )
        cv2.putText(
            frame,
            "EARLY STOP",
            (CENTER_X_MIN + 10, MARK_TARGET_Y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            2,
        )

        cv2.putText(
            frame,
            status_text,
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            box_color,
            2,
        )

        cv2.putText(
            frame,
            f"GRADE: {current_grade} | DEFECT: {current_ratio:.1f}%",
            (30, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            grade_color,
            2,
        )

        cv2.putText(
            frame,
            f"YOLO: {last_inference_ms:.0f} ms",
            (30, 130),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        if projection_active:
            cv2.putText(
                frame,
                f"PROJECTOR: ON ({len(frozen_projection_detections)} defect(s))",
                (30, 165),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

        cv2.putText(
            frame,
            f"SEGREGATION: {servo_state} (360 SERVO)",
            (30, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        # Thread-safe JPEG stream for Flask.
        display_frame = cv2.resize(frame, (720, 822))
        ok, buffer = cv2.imencode(
            ".jpg",
            display_frame,
            [cv2.IMWRITE_JPEG_QUALITY, 70],
        )

        if ok:
            with frame_lock:
                output_frame_bytes = buffer.tobytes()


# =====================================================
# Serial Send Helper
# =====================================================

def send_to_arduino(command):
    global arduino

    if arduino is None:
        return

    try:
        arduino.write(f"{command}\n".encode("utf-8"))
        print(f"[SERIAL OUT] -> {command}")

    except (serial.SerialException, OSError):
        print("[SERIAL] Write failed - re-connecting...")
        arduino = connect_arduino()

        if arduino is not None:
            try:
                arduino.write(f"{command}\n".encode("utf-8"))
            except (serial.SerialException, OSError):
                pass


# =====================================================
# Start Vision Worker
# =====================================================

worker = threading.Thread(target=inspection_worker, daemon=True)
worker.start()


# =====================================================
# Flask Video Stream / Routes
# =====================================================

def generate_frames():
    """Generate JPEG stream without blocking the inspection worker."""
    global output_frame_bytes

    while True:
        with frame_lock:
            if output_frame_bytes is None:
                frame_data = None
            else:
                frame_data = output_frame_bytes

        if frame_data is None:
            time.sleep(0.01)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame_data
            + b"\r\n"
        )

        time.sleep(0.03)


@app.route("/")
def index():
    return jsonify({
        "service": "HideSpec camera stream",
        "status": "running",
        "stats": latest_stats,
        "endpoints": ["/stats", "/api/stream/status", "/video_feed"],
    })


@app.route("/stats")
def stats():
    return jsonify(latest_stats)


@app.route("/api/stream/status")
def stream_status():
    with frame_lock:
        streaming = output_frame_bytes is not None
    return jsonify({
        "status": "running",
        "streaming": streaming,
        "camera_connected": True,
        "source": "app5.py",
        "port": 5000,
        "video_feed": "/video_feed",
        "stats": latest_stats,
    })


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# =====================================================
# Projector Display Loop
# =====================================================

def projector_display_loop():
    """
    Continuously displays projector_frame on HDMI-A-2 in TRUE FULLSCREEN.

    The window is first created, moved to the second display, and only then
    switched to fullscreen. This prevents it from fullscreening on the monitor.
    """
    clear_projector()

    cv2.namedWindow(
        PROJECTOR_WINDOW,
        cv2.WINDOW_NORMAL
    )

    # Create the window first.
    with projector_lock:
        first_display = projector_frame.copy()

    cv2.imshow(
        PROJECTOR_WINDOW,
        first_display
    )
    cv2.waitKey(250)

    # Move the window to HDMI-A-2 before entering fullscreen.
    cv2.moveWindow(
        PROJECTOR_WINDOW,
        PROJECTOR_X,
        PROJECTOR_Y
    )
    cv2.waitKey(250)

    # Fullscreen on the projector.
    cv2.setWindowProperty(
        PROJECTOR_WINDOW,
        cv2.WND_PROP_FULLSCREEN,
        cv2.WINDOW_FULLSCREEN
    )
    cv2.waitKey(250)

    print(
        f"[PROJECTOR] Fullscreen output active on HDMI-A-2 "
        f"({PROJECTOR_WIDTH}x{PROJECTOR_HEIGHT})."
    )

    while True:
        with projector_lock:
            display = projector_frame.copy()

        cv2.imshow(
            PROJECTOR_WINDOW,
            display
        )

        key = cv2.waitKey(16) & 0xFF

        if key in (ord("r"), ord("R")):
            resume_return_event.set()
        if key == 27:
            break

    clear_projector()
    cv2.destroyWindow(PROJECTOR_WINDOW)


# =====================================================
# Main Entry Point
# =====================================================

if __name__ == "__main__":

    def run_flask():
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    try:
        # Keep OpenCV's GUI on the main thread for better Raspberry Pi/Linux
        # window-manager compatibility.
        projector_display_loop()

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown requested.")

    finally:
        # Best-effort stop on normal exit. Reverse also has an Arduino timeout.
        send_to_arduino("STOP")
        clear_projector()

        try:
            picam2.stop()
        except Exception:
            pass

        cv2.destroyAllWindows()

        if arduino is not None and arduino.is_open:
            arduino.close()

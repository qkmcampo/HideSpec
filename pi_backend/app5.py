"""
Main System Host (app5.py)
Threaded execution engine separating real-time vision/hardware control
from Web HTTP streaming, while also driving the calibrated projector overlay.
"""

from flask import Flask, Response, jsonify, render_template
from ultralytics import YOLO
from picamera2 import Picamera2
from leather_cv import LeatherCV
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


app = Flask(__name__)


# =====================================================
# Camera / Detection Configuration
# =====================================================

# Lower inference size substantially reduces Raspberry Pi latency while
# Ultralytics still returns boxes in the original 1400x1600 frame coordinates.
# If very small-defect recall drops, try 736 instead of returning to 960.
IMG_SIZE = 640
FRAME_WIDTH = 1400
FRAME_HEIGHT = 1600

CONF_THRESHOLD = 0.60
MIN_DEFECT_WIDTH = 15
MIN_DEFECT_HEIGHT = 15


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

cv_engine = LeatherCV(
    frame_width=FRAME_WIDTH,
    frame_height=FRAME_HEIGHT,
    defect_ratio_thresh=20.0,
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
CENTER_Y_MIN = 250
CENTER_Y_MAX = 370

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
# Arduino starts the servo in GOOD position (125 degrees).
# The Pi sends exactly one segregation decision for each leather after the
# leather has stopped in the middle and a fresh stable grade is available.
# The servo state is NEVER reset when the leather leaves; it remains at the
# last GOOD/BAD position until the next stopped leather is classified.
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
    "status": "BELT: RUNNING",
    "projector_status": (
        "READY" if projector_mapper.is_calibrated() else "NOT CALIBRATED"
    ),
    "projected_defects": 0,
    "servo_state": "GOOD",
}

API_SERVER_URL = "http://127.0.0.1:5001"
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)


def save_inspection_record(hide_id, detections, grade, ratio, piece_area, status_text, frame):
    capture_filename = f"{hide_id}.jpg"
    capture_path = os.path.join(CAPTURES_DIR, capture_filename)
    if not cv2.imwrite(capture_path, frame):
        print(f"[CAPTURE] Failed to save {capture_path}")
        return False

    payload = {
        "hide_id": hide_id,
        "defects": [
            {
                "type": name,
                "confidence": round(float(conf), 4),
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1),
            }
            for name, _class_id, x1, y1, x2, y2, conf, _cx, _cy in detections
        ],
        "defect_area_percent": round(float(ratio or 0), 1),
        "leather_area": int(piece_area or 0),
        "defect_area": int((piece_area or 0) * float(ratio or 0) / 100.0),
        "snapshot_path": f"/captures/{capture_filename}",
        "machine_status": status_text,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
    }

    request_data = json.dumps(payload).encode("utf-8")
    request_object = urlrequest.Request(
        f"{API_SERVER_URL}/api/inspections",
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(request_object, timeout=5) as response:
            response.read()
        print(f"[DB] Inspection saved for {hide_id}")
        return True
    except HTTPError as error:
        print(f"[DB] Save failed for {hide_id}: HTTP {error.code}")
    except URLError as error:
        print(f"[DB] Save failed for {hide_id}: {error.reason}")
    except Exception as error:
        print(f"[DB] Save failed for {hide_id}: {error}")
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



def detect_defects(frame):
    """
    Run YOLO once on the supplied camera frame.

    Even though IMG_SIZE is smaller, Ultralytics rescales box coordinates back
    to the original camera-frame coordinate system. That means the existing
    projector homography and marker X calibration remain valid.
    """
    t0 = time.perf_counter()

    results = model(
        frame,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        verbose=False,
    )

    detections = []
    defect_mask = np.zeros(
        (FRAME_HEIGHT, FRAME_WIDTH),
        dtype=np.uint8,
    )

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            box_w = x2 - x1
            box_h = y2 - y1

            if box_w < MIN_DEFECT_WIDTH or box_h < MIN_DEFECT_HEIGHT:
                continue

            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            name = CLASS_NAMES[cls_id]

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

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

            cv2.rectangle(
                defect_mask,
                (x1, y1),
                (x2, y2),
                255,
                -1,
            )

    inference_ms = (
        time.perf_counter() - t0
    ) * 1000.0

    return (
        detections,
        cv2.countNonZero(defect_mask),
        inference_ms,
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
time.sleep(2)

# Background Belt Calibration
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

    # Time-based hide-exit reset. A frame counter is unreliable because the
    # effective FPS changes with YOLO inference load.
    no_leather_since = None
    hide_exit_reset_done = False

    frame_count = 0
    last_detections = []

    current_grade = "NO LEATHER"
    current_ratio = 0.0
    current_reason = "empty belt"
    last_inference_ms = 0.0
    total_defect_px = 0

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
            # Leather is visible again, so cancel any pending exit timer.
            no_leather_since = None
            hide_exit_reset_done = False

            cv2.drawContours(frame, [contour], -1, (0, 255, 0), 2)
            lx, ly, lw, lh = cv2.boundingRect(contour)

            if ly <= MIDDLE_Y_MAX and (ly + lh) >= MIDDLE_Y_MIN:
                leather_in_middle_zone = True

        else:
            # Start the timer only once when the leather first disappears
            # from the camera. This preserves the last GOOD/BAD segregation
            # decision while that same hide travels toward the diverter.
            if no_leather_since is None:
                no_leather_since = time.time()
                hide_exit_reset_done = False
                print(
                    f"[SEGREGATION] Leather left camera. Holding "
                    f"{servo_state} position for {LEATHER_EXIT_RESET_DELAY:.1f}s."
                )

            leather_absent_for = time.time() - no_leather_since

            # Reset the finished hide only after the full 5-second travel
            # allowance has elapsed and no mechanical action is running.
            if (
                not hide_exit_reset_done
                and leather_absent_for >= LEATHER_EXIT_RESET_DELAY
                and not is_currently_stopped
                and not is_center_paused
            ):
                tracker.reset()
                marked_defect_ids.clear()
                queued_defect_ids.clear()
                pending_marks = []
                current_mark = None
                last_detections = []

                projection_active = False
                projection_captured = False
                frozen_projection_detections = []

                # Re-arm only after the travel delay. IMPORTANT: this does
                # NOT move the servo; the physical diverter remains in the
                # previous GOOD/BAD position until a later hide is classified.
                segregation_sent_for_current_hide = False
                current_hide_id = None
                current_inspection_saved = False
                hide_exit_reset_done = True

                clear_projector()

                print(
                    "[SEGREGATION] 5-second exit hold complete. "
                    "System armed for the next hide."
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
            print("[PI] Hide entered inspection area. Stopping for projection...")

            # Each center-inspection event represents one leather hide.
            # Create the database ID here, not when segmentation first sees
            # the hide, so touching/overlapping hides cannot reuse a record.
            current_hide_id = (
                time.strftime("HIDE-%m%d-%H%M%S")
                + f"-{int(time.time() * 1000) % 1000:03d}"
            )
            current_inspection_saved = False
            print(f"[SAVE] Inspection started: {current_hide_id}")

            is_center_paused = True
            has_paused_for_current_hide = True
            projection_zone_clear_frames = 0
            pause_start_time = time.time()

            projection_active = False
            projection_captured = False
            frozen_projection_detections = []

            # Arm segregation for this NEW leather piece.
            #
            # IMPORTANT:
            # Do NOT reset servo_state here. The physical servo stays at the
            # previous leather's GOOD/BAD angle while this new leather is
            # stopping and being inspected. It changes only after the fresh
            # stopped-frame grade below is accepted.
            segregation_sent_for_current_hide = False

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
        run_yolo_now = (
            not projection_active
            and not is_currently_stopped
        )

        if run_yolo_now:
            (
                last_detections,
                total_defect_px,
                last_inference_ms,
            ) = detect_defects(frame)

            detection_updated_this_frame = True

            current_grade, current_ratio, current_reason = cv_engine.grade_piece(
                [(d[0], (d[4] - d[2]) * (d[5] - d[3])) for d in last_detections],
                piece_area,
            )

        # -------------------------------------------------
        # 4. Freeze and Project a Fresh Stable Detection
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

                            # Only freeze defects that the calibrated projector
                            # can actually display.
                            if mapped is not None:
                                px, py = mapped
                                if (
                                    0 <= px < PROJECTOR_WIDTH
                                    and 0 <= py < PROJECTOR_HEIGHT
                                ):
                                    projectable.append(detection)

                frozen_projection_detections = list(projectable)

                # -------------------------------------------------
                # SEGREGATION DECISION
                # -------------------------------------------------
                # This executes only after:
                #   1) the leather has stopped,
                #   2) the settle delay has elapsed, and
                #   3) YOLO has produced a fresh frame.
                #
                # Therefore the servo receives ONE stable decision for
                # the current leather instead of changing on every frame.
                if not segregation_sent_for_current_hide:
                    if current_grade == "GOOD":
                        # Send exactly once for this leather. The Arduino moves
                        # to 125 degrees and remains there until a later leather
                        # is classified BAD.
                        send_to_arduino("SEG:GOOD")
                        segregation_sent_for_current_hide = True
                        servo_state = "GOOD"
                        print(
                            "[SEGREGATION] Stable grade GOOD -> "
                            "servo = 125 degrees."
                        )

                    elif current_grade == "BAD":
                        # Send exactly once for this leather. The Arduino moves
                        # to 180 degrees and remains there until a later leather
                        # is classified GOOD.
                        send_to_arduino("SEG:BAD")
                        segregation_sent_for_current_hide = True
                        servo_state = "BAD"
                        print(
                            "[SEGREGATION] Stable grade BAD -> "
                            "servo = 180 degrees."
                        )

                    else:
                        # Keep the previous servo position. Never move the
                        # diverter because of an invalid/temporary grade.
                        print(
                            "[SEGREGATION] No valid GOOD/BAD grade yet; "
                            f"servo remains {servo_state}."
                        )

                if (
                    current_hide_id is not None
                    and not current_inspection_saved
                    and current_grade in ("GOOD", "BAD")
                    and piece_area > 0
                ):
                    print(f"[SAVE] Saving inspection for {current_hide_id}")
                    current_inspection_saved = save_inspection_record(
                        current_hide_id,
                        list(last_detections),
                        current_grade,
                        current_ratio,
                        piece_area,
                        "BELT: PAUSED IN CENTER",
                        frame,
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

        # Retry the database write while this hide is still paused. This
        # prevents a temporary API/network failure from losing the record.
        if (
            is_center_paused
            and projection_captured
            and current_hide_id is not None
            and not current_inspection_saved
            and current_grade in ("GOOD", "BAD")
            and piece_area > 0
        ):
            print(f"[SAVE] Retrying inspection save for {current_hide_id}")
            current_inspection_saved = save_inspection_record(
                current_hide_id,
                list(last_detections),
                current_grade,
                current_ratio,
                piece_area,
                "BELT: PAUSED IN CENTER",
                frame,
            )

        # -------------------------------------------------
        # 5. End Projection Pause / Resume Conveyor
        # -------------------------------------------------
        if is_center_paused and (time.time() - pause_start_time >= PAUSE_DURATION):
            print("[PI] Projection inspection finished. Resuming conveyor...")

            # Always remove the overlay before the hide starts moving again.
            clear_projector()
            projection_active = False
            projection_captured = False
            is_center_paused = False

            send_to_arduino("START")

        # -------------------------------------------------
        # 6. Defect Tracking for Mechanical Marker
        # -------------------------------------------------
        # Only feed the tracker genuinely NEW YOLO results.
        if detection_updated_this_frame:
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

        # -------------------------------------------------
        # 8. Reliable Wide-Band Mechanical Marker Trigger
        # -------------------------------------------------
        #
        # Keep the original wide band so a fast-moving defect is not easy to
        # skip. The important change is that we no longer stamp EVERY defect
        # anywhere in this 120-pixel-high region during one stop.
        #
        # The defect closest to the lower/entry side of the band defines the
        # active Y row. Only defects near that same Y are stamped together.
        # Other rows remain unmarked and receive another stop after START.
        center_hits_in_zone = []

        if detection_updated_this_frame:
            for tid, (cx, cy) in tracked_defects.items():
                if not (
                    CENTER_X_MIN <= cx <= CENTER_X_MAX
                    and CENTER_Y_MIN <= cy <= CENTER_Y_MAX
                ):
                    continue

                if tid in marked_defect_ids or tid in queued_defect_ids:
                    continue

                center_hits_in_zone.append(
                    (tid, cx, cy)
                )

        if (
            center_hits_in_zone
            and not is_currently_stopped
            and not is_center_paused
        ):
            # Conveyor moves upward in the image (Y decreases), so the row
            # with the largest Y is the row that has just entered the band.
            primary = max(
                center_hits_in_zone,
                key=lambda item: item[2],
            )
            primary_y = primary[2]

            same_row_hits = [
                item
                for item in center_hits_in_zone
                if abs(item[2] - primary_y) <= SAME_ROW_TOLERANCE
            ]

            same_row_hits.sort(
                key=lambda item: item[1]
            )

            pending_marks = list(same_row_hits)

            for tid, _, _ in pending_marks:
                queued_defect_ids.add(tid)

            is_currently_stopped = True

            # MARK already forces the Arduino conveyor state false, but an
            # explicit STOP makes the intended order obvious and immediate.
            send_to_arduino("STOP")

            print(
                f"\n[MARKER] {len(pending_marks)} defect(s) "
                f"on one Y-row ready to mark."
            )

            current_mark = pending_marks.pop(0)
            tid, mark_x, mark_y = current_mark

            print(
                f"[MARKER] Marking ID {tid} "
                f"at camera ({mark_x}, {mark_y})."
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
            "piece_area": int(piece_area),
            "leather_detected": contour is not None,
            "hide_id": current_hide_id,
            "inspection_saved": current_inspection_saved,
            "defect_count": len(last_detections),
            "defects": [
                {
                    "type": detection[0],
                    "confidence": round(float(detection[6]), 3),
                    "x": detection[2],
                    "y": detection[3],
                    "w": detection[4] - detection[2],
                    "h": detection[5] - detection[3],
                }
                for detection in last_detections
            ],
            "status": status_text,
            "projector_status": projector_status,
            "projected_defects": len(frozen_projection_detections),
            "servo_state": servo_state,
            "inference_ms": round(last_inference_ms, 1),
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

        servo_angle_text = (
            "125 deg" if servo_state == "GOOD"
            else "180 deg" if servo_state == "BAD"
            else "UNKNOWN"
        )

        cv2.putText(
            frame,
            f"SEGREGATION: {servo_state} ({servo_angle_text})",
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
    return render_template("index.html")


@app.route("/stats")
def stats():
    return jsonify(latest_stats)


@app.route("/api/stream/status")
def stream_status():
    return jsonify({
        "status": "running",
        "streaming": output_frame_bytes is not None,
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
        clear_projector()

        try:
            picam2.stop()
        except Exception:
            pass

        cv2.destroyAllWindows()

        if arduino is not None and arduino.is_open:
            arduino.close()

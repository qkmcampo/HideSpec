"""Stopped-frame SHAPE screening with automatic non-leather removal detection.

Behavior:
- Stop the conveyor when an object reaches the inspection area.
- Classify the segmented outline as LEATHER / NOT LEATHER / UNCERTAIN.
- LEATHER stays stopped and continues into the normal inspection workflow.
- NOT LEATHER or UNCERTAIN stays stopped until the camera confirms that the
  operator has removed the object; the conveyor then resumes automatically.
- No reverse command is sent anywhere in this module.

Only the inspection worker calls this module; Flask never writes serial.
"""

import time
import cv2
import numpy as np


# =====================================================
# Screening Configuration
# =====================================================

STABLE_FRAMES = 3
SCREEN_SECONDS = 4.0

# Automatic rejected-object removal detection.
#
# The conveyor will restart only after the camera sees NO segmented object for
# several consecutive frames. This prevents one temporary segmentation dropout
# from restarting the belt while the rejected object is still present.
REMOVAL_CLEAR_FRAMES = 10
REMOVAL_CHECK_DELAY = 0.05


# =====================================================
# Shape-Screening Configuration
# =====================================================

# Ignore tiny segmented blobs.
MIN_OBJECT_AREA_PX = 30000

# square_ratio = short side / long side from cv2.minAreaRect().
ACCEPT_SQUARE_RATIO = 0.55
HARD_REJECT_SQUARE_RATIO = 0.38

# rectangularity = contour area / minimum rotated rectangle area.
ACCEPT_RECTANGULARITY = 0.70
HARD_REJECT_RECTANGULARITY = 0.48

# Solidity helps reject strongly concave / fragmented outlines.
ACCEPT_SOLIDITY = 0.82
HARD_REJECT_SOLIDITY = 0.62

# Approximate polygon corner count.
GOOD_MIN_CORNERS = 4
GOOD_MAX_CORNERS = 7
HARD_REJECT_MAX_CORNERS = 11

# Final weighted score thresholds.
ACCEPT_SHAPE_SCORE = 0.70
REJECT_SHAPE_SCORE = 0.50


# =====================================================
# Serial Helper
# =====================================================

def exchange(arduino, command, expected, timeout=2.0):
    """Send one command and wait for the expected Arduino acknowledgement."""
    if arduino is None:
        return False

    try:
        arduino.write((command + "\n").encode())
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if arduino.in_waiting:
                response = (
                    arduino.readline()
                    .decode(errors="replace")
                    .strip()
                )

                if response:
                    print("[SCREEN]", response)

                if response == expected:
                    return True

                if response.startswith("ERROR"):
                    return False

            time.sleep(0.005)

    except Exception as exc:
        print("[SCREEN] Serial failure:", exc)

    return False


# =====================================================
# Shape Classifier
# =====================================================

def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def classify_shape(contour):
    """Return LEATHER / NOT LEATHER / UNCERTAIN from the segmented outline.

    Returns:
        result: "LEATHER", "NOT LEATHER", or "UNCERTAIN"
        score:  0.0..1.0 geometric match score
        reason: human-readable diagnostics

    IMPORTANT:
        This is shape recognition, not material recognition. A non-leather
        object with the same roughly rectangular geometry can still pass.
    """

    if contour is None:
        return "UNCERTAIN", 0.0, "No reliable object outline"

    contour_area = float(cv2.contourArea(contour))

    if contour_area < MIN_OBJECT_AREA_PX:
        return (
            "UNCERTAIN",
            0.0,
            f"Object outline too small ({contour_area:.0f}px²)",
        )

    # Rotated rectangle makes the test tolerant to a leather piece that is not
    # perfectly aligned with the camera axes.
    (_, _), (rect_w, rect_h), _ = cv2.minAreaRect(contour)
    rect_w = float(rect_w)
    rect_h = float(rect_h)

    if rect_w < 1.0 or rect_h < 1.0:
        return "UNCERTAIN", 0.0, "Invalid minimum rectangle"

    short_side = min(rect_w, rect_h)
    long_side = max(rect_w, rect_h)
    square_ratio = short_side / long_side

    rect_area = rect_w * rect_h
    rectangularity = contour_area / rect_area if rect_area > 0 else 0.0
    rectangularity = _clamp01(rectangularity)

    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    solidity = contour_area / hull_area if hull_area > 0 else 0.0
    solidity = _clamp01(solidity)

    perimeter = float(cv2.arcLength(contour, True))
    if perimeter > 0:
        approx = cv2.approxPolyDP(contour, 0.035 * perimeter, True)
        corners = len(approx)
    else:
        corners = 0

    # -------------------------------------------------
    # Convert individual measurements to 0..1 scores.
    # -------------------------------------------------

    # 0.38 -> 0, 0.70+ -> 1.  A true square approaches 1.
    square_score = _clamp01(
        (square_ratio - HARD_REJECT_SQUARE_RATIO)
        / (0.70 - HARD_REJECT_SQUARE_RATIO)
    )

    # 0.48 -> 0, 0.85+ -> 1.
    rectangularity_score = _clamp01(
        (rectangularity - HARD_REJECT_RECTANGULARITY)
        / (0.85 - HARD_REJECT_RECTANGULARITY)
    )

    # 0.62 -> 0, 0.95+ -> 1.
    solidity_score = _clamp01(
        (solidity - HARD_REJECT_SOLIDITY)
        / (0.95 - HARD_REJECT_SOLIDITY)
    )

    if GOOD_MIN_CORNERS <= corners <= GOOD_MAX_CORNERS:
        corner_score = 1.0
    elif corners == 3 or corners == 8:
        corner_score = 0.55
    elif corners in (9, 10, 11):
        corner_score = 0.25
    else:
        corner_score = 0.0

    # Shape score emphasizes "square-ish" and "rectangle-like" because those
    # are the two characteristics requested for this project's leather samples.
    shape_score = (
        0.38 * square_score
        + 0.37 * rectangularity_score
        + 0.15 * solidity_score
        + 0.10 * corner_score
    )
    shape_score = _clamp01(shape_score)

    # -------------------------------------------------
    # Decision
    # -------------------------------------------------

    hard_reject = (
        square_ratio < HARD_REJECT_SQUARE_RATIO
        or rectangularity < HARD_REJECT_RECTANGULARITY
        or solidity < HARD_REJECT_SOLIDITY
        or corners < 3
        or corners > HARD_REJECT_MAX_CORNERS
    )

    good_geometry = (
        square_ratio >= ACCEPT_SQUARE_RATIO
        and rectangularity >= ACCEPT_RECTANGULARITY
        and solidity >= ACCEPT_SOLIDITY
        and GOOD_MIN_CORNERS <= corners <= GOOD_MAX_CORNERS
    )

    if hard_reject or shape_score <= REJECT_SHAPE_SCORE:
        result = "NOT LEATHER"
    elif good_geometry and shape_score >= ACCEPT_SHAPE_SCORE:
        result = "LEATHER"
    else:
        result = "UNCERTAIN"

    aspect_ratio = long_side / short_side

    reason = (
        f"Shape={shape_score:.0%} | "
        f"aspect={aspect_ratio:.2f}:1 | "
        f"rect={rectangularity:.0%} | "
        f"solidity={solidity:.0%} | "
        f"corners={corners}"
    )

    print(f"[SHAPE] {result} - {reason}")

    return result, shape_score, reason

# =====================================================
# Stopped-Frame Screening / Manual Removal
# =====================================================

def screen_or_return(arduino, camera, cv_engine, publish, resume_event):
    """
    True:
        Object was accepted as leather and remains stopped for inspection.

    False:
        Object was rejected, removed from the inspection area, and the conveyor
        restarted automatically.

    No reverse command is used.

    publish(frame, contour, area, grade, reason, status, fraction)
    must only draw on the supplied frame after classification.

    The last parameter remains named ``fraction`` for compatibility with
    app5.py, but it carries SHAPE MATCH SCORE rather than color percentage.
    """

    resume_event.clear()

    # Stop before evaluating the object.
    stopped = exchange(
        arduino,
        "STOP",
        "STOPPED",
        timeout=2.0,
    )

    result = "NOT LEATHER"
    shape_score = 0.0
    reason = "Arduino STOP not acknowledged"

    # Do not allow a stationary rejected object to become part of the learned
    # empty-belt reference while the operator is removing it.
    previous_adapt = cv_engine.adapt_rate
    cv_engine.adapt_rate = 0.0

    try:
        if stopped:
            time.sleep(0.35)

            deadline = time.monotonic() + SCREEN_SECONDS
            previous = None
            consecutive = 0
            stable = False

            while time.monotonic() < deadline:
                frame = camera.capture_array()
                contour, area = cv_engine.segment_leather(frame)

                raw_result, shape_score, reason = classify_shape(contour)

                # Fail-safe requested by the operator:
                # only a confident LEATHER result is accepted.
                # UNCERTAIN is treated as NOT LEATHER.
                result = (
                    "LEATHER"
                    if raw_result == "LEATHER"
                    else "NOT LEATHER"
                )

                if raw_result == "UNCERTAIN":
                    reason = (
                        "UNCERTAIN treated as NOT LEATHER | "
                        + reason
                    )

                if result == previous:
                    consecutive += 1
                else:
                    consecutive = 1

                previous = result

                publish(
                    frame,
                    contour,
                    area,
                    "CHECKING SHAPE",
                    reason,
                    "BELT: STOPPED - SHAPE CHECK",
                    shape_score,
                )

                if consecutive >= STABLE_FRAMES:
                    stable = True
                    break

            if not stable:
                result = "NOT LEATHER"
                reason = (
                    "No stable LEATHER decision; "
                    "automatic removal detection active"
                )

            # Accepted leather remains stopped.
            # app5.py continues with defect inspection / projection.
            if result == "LEATHER":
                print(
                    f"[SHAPE] ACCEPTED as leather geometry "
                    f"({shape_score:.0%} match)."
                )
                return True

        # -------------------------------------------------
        # Automatic rejected-object removal handling
        # -------------------------------------------------

        if result == "NOT LEATHER":
            print(
                f"[SHAPE] NOT LEATHER ({shape_score:.0%} match). "
                "Conveyor remains stopped. "
                "Remove the object; the system will resume automatically."
            )

        # R is no longer required. Clear any old key event and ignore it.
        resume_event.clear()

        clear_frames = 0

        while True:
            frame = camera.capture_array()
            contour, area = cv_engine.segment_leather(frame)

            # A rejected object is considered physically removed only when the
            # segmentation sees no valid foreground contour for several
            # consecutive frames.
            object_present = (
                contour is not None
                and area is not None
                and area >= MIN_OBJECT_AREA_PX
            )

            if object_present:
                clear_frames = 0
            else:
                clear_frames += 1

            warning_reason = (
                "NOT LEATHER - Please remove the object. "
                "System will resume automatically when the inspection area is clear."
            )

            if reason:
                warning_reason += " | " + reason

            if clear_frames > 0:
                status = (
                    "BELT: STOPPED - NOT LEATHER - "
                    f"WAITING FOR CLEAR AREA {clear_frames}/{REMOVAL_CLEAR_FRAMES}"
                )
            else:
                status = (
                    "BELT: STOPPED - NOT LEATHER - "
                    "PLEASE REMOVE OBJECT"
                )

            publish(
                frame,
                contour,
                area,
                "NOT LEATHER",
                warning_reason,
                status,
                shape_score,
            )

            if clear_frames >= REMOVAL_CLEAR_FRAMES:
                print(
                    "[SHAPE] Rejected object removed. "
                    "Inspection area is clear."
                )

                # Confirm STOP one final time, then resume normal forward motion.
                stopped = exchange(
                    arduino,
                    "STOP",
                    "STOPPED",
                    timeout=2.0,
                )

                if stopped and exchange(
                    arduino,
                    "START",
                    "STARTED",
                    timeout=2.0,
                ):
                    print(
                        "[SHAPE] Conveyor automatically resumed. "
                        "Ready for the next object."
                    )
                    return False

                # A hardware/serial failure is the only reason to remain stopped.
                reason = (
                    "Automatic restart failed; conveyor remains stopped. "
                    "Check Arduino/serial connection."
                )
                clear_frames = 0

            time.sleep(REMOVAL_CHECK_DELAY)

    except Exception:
        exchange(
            arduino,
            "STOP",
            "STOPPED",
            timeout=2.0,
        )
        raise

    finally:
        cv_engine.adapt_rate = previous_adapt

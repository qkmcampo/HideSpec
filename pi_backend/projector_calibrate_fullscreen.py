"""
projector_calibrate_fullscreen.py

Sequential camera-projector calibration for the FULLSCREEN projector mode.

IMPORTANT:
Run this once after switching the main system to fullscreen projection.
It overwrites projector_homography.npy with calibration matching the new
fullscreen geometry.
"""

import cv2
import numpy as np
from picamera2 import Picamera2


CAMERA_WIDTH = 1400
CAMERA_HEIGHT = 1600

PREVIEW_WIDTH = 700
PREVIEW_HEIGHT = 800

PROJECTOR_WIDTH = 1024
PROJECTOR_HEIGHT = 768

PROJECTOR_X = 1920
PROJECTOR_Y = 0

PROJECTOR_WINDOW = "PROJECTOR_CALIBRATION"

# Keep points slightly inside the true projector edge.
MARGIN_X = 80
MARGIN_Y = 60


projector_points = np.float32([
    [MARGIN_X, MARGIN_Y],
    [PROJECTOR_WIDTH - MARGIN_X, MARGIN_Y],
    [PROJECTOR_WIDTH - MARGIN_X, PROJECTOR_HEIGHT - MARGIN_Y],
    [MARGIN_X, PROJECTOR_HEIGHT - MARGIN_Y],
])


picam2 = Picamera2()
picam2.configure(
    picam2.create_preview_configuration(
        main={
            "format": "RGB888",
            "size": (CAMERA_WIDTH, CAMERA_HEIGHT),
        }
    )
)
picam2.start()


cv2.namedWindow(PROJECTOR_WINDOW, cv2.WINDOW_NORMAL)

blank = np.zeros(
    (PROJECTOR_HEIGHT, PROJECTOR_WIDTH, 3),
    dtype=np.uint8
)

# Create -> move -> fullscreen, same geometry as app5.py.
cv2.imshow(PROJECTOR_WINDOW, blank)
cv2.waitKey(250)

cv2.moveWindow(
    PROJECTOR_WINDOW,
    PROJECTOR_X,
    PROJECTOR_Y
)
cv2.waitKey(250)

cv2.setWindowProperty(
    PROJECTOR_WINDOW,
    cv2.WND_PROP_FULLSCREEN,
    cv2.WINDOW_FULLSCREEN
)
cv2.waitKey(250)


cv2.namedWindow("CAMERA", cv2.WINDOW_NORMAL)
cv2.resizeWindow("CAMERA", PREVIEW_WIDTH, PREVIEW_HEIGHT)


camera_points = []
current_point = 0

scale_x = CAMERA_WIDTH / PREVIEW_WIDTH
scale_y = CAMERA_HEIGHT / PREVIEW_HEIGHT


def create_projector_image():
    canvas = np.zeros(
        (PROJECTOR_HEIGHT, PROJECTOR_WIDTH, 3),
        dtype=np.uint8
    )

    if current_point >= 4:
        return canvas

    x = int(projector_points[current_point][0])
    y = int(projector_points[current_point][1])

    # Bright green ring + white center for visibility.
    cv2.circle(
        canvas,
        (x, y),
        28,
        (0, 255, 0),
        7,
        cv2.LINE_AA,
    )

    cv2.circle(
        canvas,
        (x, y),
        7,
        (255, 255, 255),
        -1,
        cv2.LINE_AA,
    )

    cv2.drawMarker(
        canvas,
        (x, y),
        (0, 255, 255),
        cv2.MARKER_CROSS,
        70,
        4,
    )

    return canvas


def mouse_callback(event, x, y, flags, param):
    global current_point

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    if current_point >= 4:
        return

    camera_x = x * scale_x
    camera_y = y * scale_y

    camera_points.append([camera_x, camera_y])

    print(
        f"[CALIBRATION] Point {current_point + 1}: "
        f"camera=({camera_x:.1f}, {camera_y:.1f}) "
        f"projector=({projector_points[current_point][0]:.1f}, "
        f"{projector_points[current_point][1]:.1f})"
    )

    current_point += 1


cv2.setMouseCallback("CAMERA", mouse_callback)


print()
print("FULLSCREEN PROJECTOR CALIBRATION")
print("--------------------------------")
print("Only ONE projected marker appears at a time.")
print("Click the center of that marker in the CAMERA window.")
print("Do this four times. The calibration saves automatically.")
print("Press R to restart or ESC to cancel.")
print()


saved = False

while True:
    frame = picam2.capture_array()

    preview = cv2.resize(
        frame,
        (PREVIEW_WIDTH, PREVIEW_HEIGHT)
    )

    for i, point in enumerate(camera_points):
        px = int(point[0] / scale_x)
        py = int(point[1] / scale_y)

        cv2.circle(
            preview,
            (px, py),
            7,
            (0, 0, 255),
            -1,
        )

        cv2.putText(
            preview,
            str(i + 1),
            (px + 10, py - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

    projector_frame = create_projector_image()

    cv2.imshow("CAMERA", preview)
    cv2.imshow(PROJECTOR_WINDOW, projector_frame)

    if current_point == 4 and not saved:
        camera_array = np.float32(camera_points)

        H = cv2.getPerspectiveTransform(
            camera_array,
            projector_points
        )

        np.save(
            "projector_homography.npy",
            H
        )

        print()
        print("[SUCCESS] Fullscreen calibration saved:")
        print("projector_homography.npy")
        print()

        saved = True
        break

    key = cv2.waitKey(1) & 0xFF

    if key == ord("r"):
        camera_points.clear()
        current_point = 0
        saved = False
        print("[CALIBRATION] Restarted.")

    elif key == 27:
        break


picam2.stop()
cv2.destroyAllWindows()

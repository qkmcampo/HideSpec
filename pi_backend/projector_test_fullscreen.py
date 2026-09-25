"""
projector_test_fullscreen.py

Click a location in the camera preview.
The fullscreen projector should place a dot on that same physical location.
"""

import cv2
import numpy as np
from picamera2 import Picamera2
from projector import ProjectorMapper


CAMERA_WIDTH = 1400
CAMERA_HEIGHT = 1600

PREVIEW_WIDTH = 700
PREVIEW_HEIGHT = 800

PROJECTOR_WIDTH = 1024
PROJECTOR_HEIGHT = 768

PROJECTOR_X = 1920
PROJECTOR_Y = 0

PROJECTOR_WINDOW = "PROJECTOR"


projector = ProjectorMapper(
    width=PROJECTOR_WIDTH,
    height=PROJECTOR_HEIGHT,
    calibration_file="projector_homography.npy",
)

if not projector.is_calibrated():
    print("[ERROR] No projector calibration found.")
    raise SystemExit


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


projection = np.zeros(
    (PROJECTOR_HEIGHT, PROJECTOR_WIDTH, 3),
    dtype=np.uint8
)


cv2.namedWindow(PROJECTOR_WINDOW, cv2.WINDOW_NORMAL)

cv2.imshow(PROJECTOR_WINDOW, projection)
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


scale_x = CAMERA_WIDTH / PREVIEW_WIDTH
scale_y = CAMERA_HEIGHT / PREVIEW_HEIGHT

last_camera_point = None


def mouse_callback(event, x, y, flags, param):
    global projection
    global last_camera_point

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    camera_x = int(x * scale_x)
    camera_y = int(y * scale_y)

    result = projector.transform_point(
        camera_x,
        camera_y
    )

    if result is None:
        return

    projector_x, projector_y = result

    print(
        f"[TEST] Camera: ({camera_x}, {camera_y}) | "
        f"Projector: ({projector_x}, {projector_y})"
    )

    last_camera_point = (
        camera_x,
        camera_y
    )

    projection[:] = 0

    if (
        0 <= projector_x < PROJECTOR_WIDTH
        and
        0 <= projector_y < PROJECTOR_HEIGHT
    ):
        cv2.circle(
            projection,
            (projector_x, projector_y),
            24,
            (0, 255, 0),
            7,
            cv2.LINE_AA,
        )

        cv2.circle(
            projection,
            (projector_x, projector_y),
            6,
            (0, 255, 255),
            -1,
            cv2.LINE_AA,
        )
    else:
        print("[WARNING] Point is outside projector coverage.")


cv2.setMouseCallback("CAMERA", mouse_callback)


print()
print("FULLSCREEN PROJECTOR TEST")
print("-------------------------")
print("Click inside the calibrated projector field.")
print("R = clear, ESC = exit")
print()


while True:
    frame = picam2.capture_array()

    preview = cv2.resize(
        frame,
        (PREVIEW_WIDTH, PREVIEW_HEIGHT)
    )

    if last_camera_point is not None:
        cx = int(last_camera_point[0] / scale_x)
        cy = int(last_camera_point[1] / scale_y)

        cv2.circle(
            preview,
            (cx, cy),
            8,
            (0, 0, 255),
            -1,
        )

        cv2.putText(
            preview,
            "CLICK",
            (cx + 10, max(20, cy - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

    cv2.imshow("CAMERA", preview)
    cv2.imshow(PROJECTOR_WINDOW, projection)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("r"):
        projection[:] = 0
        last_camera_point = None

    elif key == 27:
        break


picam2.stop()
cv2.destroyAllWindows()

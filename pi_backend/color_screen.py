"""Temporary supported-color screening. This does not identify material."""
import cv2
import numpy as np

# OpenCV HSV: H=0..179, S/V=0..255. Provisional, NOT camera-calibrated.
# Red/coral, ochre/tan/brown and cream/off-white from the supplied samples.
HSV_RANGES = (
    ((0, 45, 35), (38, 255, 255)),
    ((170, 45, 35), (179, 255, 255)),
    ((0, 0, 120), (179, 60, 255)),
)
ACCEPT_FRACTION = 0.65
REJECT_FRACTION = 0.45


def classify_color(frame, contour):
    """Return LEATHER/NOT LEATHER/UNCERTAIN, supported fraction, explanation.

    Analyze unannotated BGR pixels inside an eroded object mask. Minority
    stains may be unsupported. No color is treated as a defect here.
    """
    if contour is None:
        return "UNCERTAIN", 0.0, "No reliable object outline"
    mask = np.zeros(frame.shape[:2], np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
    count = cv2.countNonZero(mask)
    if count < 500:
        return "UNCERTAIN", 0.0, "Too few interior pixels"
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    supported = np.zeros_like(mask)
    for low, high in HSV_RANGES:
        supported |= cv2.inRange(hsv, np.array(low), np.array(high))
    fraction = cv2.countNonZero(supported & mask) / count
    result = ("LEATHER" if fraction >= ACCEPT_FRACTION else
              "NOT LEATHER" if fraction <= REJECT_FRACTION else "UNCERTAIN")
    return result, fraction, f"Supported-color pixels: {fraction:.0%} (not material recognition)"

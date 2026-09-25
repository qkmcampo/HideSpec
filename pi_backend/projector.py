"""
projector.py
Camera-to-projector coordinate mapping and overlay rendering.

The homography file is created by projector_calibrate.py.
No manual X/Y flipping is applied here; the calibration itself handles
camera/projector orientation and perspective.
"""

import os
import cv2
import numpy as np


class ProjectorMapper:
    def __init__(
        self,
        width=1024,
        height=768,
        calibration_file="projector_homography.npy",
    ):
        self.width = width
        self.height = height
        self.calibration_file = calibration_file
        self.H = None

        if os.path.exists(calibration_file):
            try:
                self.H = np.load(calibration_file)
                print("[PROJECTOR] Calibration loaded.")
            except Exception as exc:
                print(f"[PROJECTOR] Calibration load error: {exc}")
        else:
            print("[PROJECTOR] No calibration file found.")

    def is_calibrated(self):
        return self.H is not None

    def load_calibration(self):
        """Reload the saved camera-to-projector homography."""
        if not os.path.exists(self.calibration_file):
            return False

        try:
            self.H = np.load(self.calibration_file)
            print("[PROJECTOR] Calibration reloaded.")
            return True
        except Exception as exc:
            print(f"[PROJECTOR] Calibration load error: {exc}")
            return False

    def transform_point(self, x, y):
        """Convert one camera coordinate into projector coordinates."""
        if self.H is None:
            return None

        camera_point = np.array(
            [[[float(x), float(y)]]],
            dtype=np.float32,
        )

        projected = cv2.perspectiveTransform(
            camera_point,
            self.H
        )

        px, py = projected[0][0]

        return (
            int(round(px)),
            int(round(py))
        )

    def transform_box(
        self,
        x1,
        y1,
        x2,
        y2
    ):
        """Transform all four corners of a YOLO bounding box."""
        if self.H is None:
            return None

        camera_points = np.array(
            [[
                [float(x1), float(y1)],
                [float(x2), float(y1)],
                [float(x2), float(y2)],
                [float(x1), float(y2)],
            ]],
            dtype=np.float32,
        )

        projected = cv2.perspectiveTransform(
            camera_points,
            self.H
        )

        return np.round(
            projected[0]
        ).astype(np.int32)

    def create_blank(self):
        """Return a completely black projector frame."""
        return np.zeros(
            (
                self.height,
                self.width,
                3
            ),
            dtype=np.uint8,
        )

    def create_overlay(self, detections):
        """
        Create a black projector frame containing
        the frozen YOLO defects.

        Each detection must have this format:

        (
            name,
            cls_id,
            x1,
            y1,
            x2,
            y2,
            conf,
            cx,
            cy
        )
        """

        canvas = self.create_blank()

        if self.H is None:
            return canvas

        # -----------------------------------------
        # PROJECTOR COLORS
        # OpenCV uses BGR order
        # -----------------------------------------

        NEON_GREEN = (0, 255, 0)
        YELLOW = (0, 255, 255)

        for detection in detections:

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
            ) = detection

            # -----------------------------------------
            # Transform defect center
            # -----------------------------------------

            projected_center = self.transform_point(
                cx,
                cy
            )

            if projected_center is None:
                continue

            px, py = projected_center

            # Ignore detections outside projector area
            if not (
                0 <= px < self.width
                and
                0 <= py < self.height
            ):
                continue

            # -----------------------------------------
            # Transform full YOLO bounding box
            # -----------------------------------------

            projected_box = self.transform_box(
                x1,
                y1,
                x2,
                y2
            )

            if projected_box is None:
                continue

            # =========================================
            # NEON GREEN DEFECT BOUNDING BOX
            # =========================================

            cv2.polylines(
                canvas,
                [projected_box],
                True,
                NEON_GREEN,
                8,
                cv2.LINE_AA,
            )

            # =========================================
            # NEON GREEN CENTER RING
            # =========================================

            cv2.circle(
                canvas,
                (px, py),
                18,
                NEON_GREEN,
                6,
                cv2.LINE_AA,
            )

            # =========================================
            # YELLOW EXACT CENTER POINT
            # =========================================

            cv2.circle(
                canvas,
                (px, py),
                6,
                YELLOW,
                -1,
                cv2.LINE_AA,
            )

            # =========================================
            # NEON GREEN DEFECT CLASS LABEL
            # =========================================

            cv2.putText(
                canvas,
                name.upper(),
                (
                    px + 22,
                    max(
                        30,
                        py - 22
                    )
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                NEON_GREEN,
                3,
                cv2.LINE_AA,
            )

        return canvas

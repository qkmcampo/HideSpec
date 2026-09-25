"""
projector.py
Camera-to-projector coordinate mapping and overlay rendering.
"""

import cv2
import numpy as np
import os


class ProjectorMapper:

    def __init__(
        self,
        width=1024,
        height=768,
        calibration_file="projector_homography.npy"
    ):
        self.width = width
        self.height = height
        self.calibration_file = calibration_file

        self.H = None

        if os.path.exists(calibration_file):
            try:
                self.H = np.load(calibration_file)

                print(
                    "[PROJECTOR] Calibration loaded."
                )

            except Exception as exc:
                print(
                    f"[PROJECTOR] Calibration load error: {exc}"
                )

        else:
            print(
                "[PROJECTOR] No calibration file found."
            )


    def is_calibrated(self):
        return self.H is not None


    def load_calibration(self):

        if not os.path.exists(
            self.calibration_file
        ):
            return False

        try:

            self.H = np.load(
                self.calibration_file
            )

            print(
                "[PROJECTOR] Calibration reloaded."
            )

            return True

        except Exception as exc:

            print(
                f"[PROJECTOR] Calibration load error: {exc}"
            )

            return False


    def transform_point(self, x, y):
        """
        Convert a camera coordinate
        directly into projector coordinates.

        No manual flipping is needed.
        The homography handles orientation.
        """

        if self.H is None:
            return None

        camera_point = np.array(
            [[[float(x), float(y)]]],
            dtype=np.float32
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
        """
        Transform all four corners
        of a YOLO bounding box.
        """

        if self.H is None:
            return None

        camera_points = np.array(
            [[
                [float(x1), float(y1)],
                [float(x2), float(y1)],
                [float(x2), float(y2)],
                [float(x1), float(y2)]
            ]],
            dtype=np.float32
        )

        projected = cv2.perspectiveTransform(
            camera_points,
            self.H
        )

        return np.round(
            projected[0]
        ).astype(np.int32)


    def create_blank(self):

        return np.zeros(
            (
                self.height,
                self.width,
                3
            ),
            dtype=np.uint8
        )


    def create_overlay(
        self,
        detections
    ):

        canvas = self.create_blank()

        if self.H is None:
            return canvas

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
                cy
            ) = detection


            projected_box = (
                self.transform_box(
                    x1,
                    y1,
                    x2,
                    y2
                )
            )


            projected_center = (
                self.transform_point(
                    cx,
                    cy
                )
            )


            if projected_box is None:
                continue


            # Project defect outline
            cv2.polylines(
                canvas,
                [projected_box],
                True,
                (255, 255, 255),
                5,
                cv2.LINE_AA
            )


            if projected_center is None:
                continue


            px, py = projected_center


            if (
                0 <= px < self.width
                and
                0 <= py < self.height
            ):

                # Outer white center marker
                cv2.circle(
                    canvas,
                    (px, py),
                    15,
                    (255, 255, 255),
                    -1,
                    cv2.LINE_AA
                )


                # Red center
                cv2.circle(
                    canvas,
                    (px, py),
                    6,
                    (0, 0, 255),
                    -1,
                    cv2.LINE_AA
                )


                cv2.putText(
                    canvas,
                    name.upper(),
                    (
                        px + 18,
                        max(25, py - 18)
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )


        return canvas

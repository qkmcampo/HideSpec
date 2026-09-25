"""
Leather Computer Vision Engine (leather_cv.py)

Segmentation
------------
The old version thresholded saturation (Otsu) and brightness (+/-45 around one
belt brightness number). That fails for:
  * bright/white/cream leather  - low saturation, and brightness can sit inside
                                  the +/-45 band on a lit belt
  * dark/black/brown leather    - low saturation AND close to belt brightness
  * uneven lighting             - one belt number cannot describe a belt that
                                  is brighter under the light bar than at the
                                  edges

This version stores a full per-pixel picture of the EMPTY belt (in LAB colour
space) at startup, and marks as leather any pixel that differs from that
picture by more than a colour-distance threshold. Brightness, colour and
saturation all count, so a piece is found whether it is brighter, darker, or
just a different hue than the belt. Uneven lighting is handled automatically
because every pixel is compared with the same pixel of the empty belt.

The reference slowly adapts to lighting drift using only belt pixels, so the
system does not need re-calibrating every time the room light changes.

Grading
-------
A piece is BAD if ANY of these is true:
  1. defect area >= defect_ratio_thresh % of the piece       (ISO 17551:2018,
     20 % = boundary between Grade II and Grade III)
  2. number of defects > max_defect_count                    (packer raw-hide
     grading: No. 2 allows up to 4 holes/cuts, 5+ is No. 3)
  3. a defect of a class listed in critical_classes is found (optional,
     empty by default)
"""

import cv2
import numpy as np


class LeatherCV:

    def __init__(
        self,
        frame_width=1400,
        frame_height=1600,
        min_area_ratio=0.05,
        max_area_ratio=0.85,
        defect_ratio_thresh=20.0,
        max_defect_count=4,
        critical_classes=(),
        diff_thresh=18.0,
        downscale=4,
    ):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_area = frame_width * frame_height

        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio

        self.defect_ratio_thresh = defect_ratio_thresh
        self.max_defect_count = max_defect_count
        self.critical_classes = set(critical_classes)

        # Minimum LAB colour distance for a pixel to count as "not belt".
        # Raise it if belt texture/shadows get picked up as leather.
        # Lower it if very belt-like leather is missed.
        self.diff_thresh = diff_thresh

        # Segmentation runs on a reduced image for speed on the Raspberry Pi;
        # the contour is scaled back to full camera coordinates.
        self.downscale = downscale
        self.small_w = frame_width // downscale
        self.small_h = frame_height // downscale

        self.reference_lab = None          # per-pixel empty-belt picture
        self.baseline_belt_val = 125.0     # kept for backward compatibility

        # How fast the reference follows lighting drift (0 = never).
        self.adapt_rate = 0.03

    # -------------------------------------------------------------
    # Calibration
    # -------------------------------------------------------------

    def _prep(self, frame):
        small = cv2.resize(
            frame, (self.small_w, self.small_h), interpolation=cv2.INTER_AREA
        )
        small = cv2.GaussianBlur(small, (7, 7), 0)
        return cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)

    def calibrate_belt(self, empty_frame):
        """
        Store the empty belt. MUST be called with nothing on the belt, under
        the same lighting used for inspection.
        """
        self.reference_lab = self._prep(empty_frame)

        hsv = cv2.cvtColor(empty_frame, cv2.COLOR_BGR2HSV)
        self.baseline_belt_val = float(np.mean(hsv[:, :, 2]))

        print(
            f"[CV] Belt calibrated: mean brightness {self.baseline_belt_val:.1f}"
        )
        return self.baseline_belt_val

    # -------------------------------------------------------------
    # Segmentation
    # -------------------------------------------------------------

    def _exposure_compensate(self, lab):
        """
        Safety net for camera exposure drift. Uses the left/right edge strips
        (belt, almost never covered) to estimate how much brighter or darker
        this frame is than the calibration frame, and removes that difference.
        The real fix is locking exposure in app5.py; this catches the rest.
        """
        ref = self.reference_lab
        w = max(4, self.small_w // 20)
        top = self.small_h // 5          # skip the light-bar region
        edge_now = np.concatenate([lab[top:, :w, 0], lab[top:, -w:, 0]], axis=1)
        edge_ref = np.concatenate([ref[top:, :w, 0], ref[top:, -w:, 0]], axis=1)
        gain = np.median(edge_now) / max(np.median(edge_ref), 1.0)
        gain = float(np.clip(gain, 0.5, 2.0))
        out = lab.copy()
        out[:, :, 0] = out[:, :, 0] / gain
        return out

    def _difference_mask(self, lab):
        ref = self.reference_lab
        lab = self._exposure_compensate(lab)

        d_l = lab[:, :, 0] - ref[:, :, 0]
        d_a = lab[:, :, 1] - ref[:, :, 1]
        d_b = lab[:, :, 2] - ref[:, :, 2]

        chroma_diff = np.sqrt(d_a * d_a + d_b * d_b)
        dist = np.sqrt(d_l * d_l + chroma_diff * chroma_diff)

        # Otsu on the distance map gives a good split when a piece is present;
        # the floor stops it from latching onto belt noise when the belt is
        # empty.
        dist_u8 = np.clip(dist * 2.0, 0, 255).astype(np.uint8)
        otsu_t, _ = cv2.threshold(
            dist_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        strong_t = max(self.diff_thresh, otsu_t / 2.0)
        weak_t = self.diff_thresh * 0.75

        # Shadow suppression: a cast shadow is the SAME colour as the belt,
        # only moderately darker. Black leather is far darker than a shadow,
        # so it survives this rule.
        ref_l = np.maximum(ref[:, :, 0], 1.0)
        l_ratio = lab[:, :, 0] / ref_l
        shadow = (l_ratio > 0.55) & (l_ratio < 0.93) & (chroma_diff < 7.0)

        strong = (dist > strong_t) & ~shadow
        weak = (dist > weak_t) & ~shadow

        # Hysteresis: weak pixels are kept only if they connect to a strong
        # region. This recovers shaded folds/creases of the piece (colour
        # close to the belt) without admitting isolated belt noise.
        weak_u8 = weak.astype(np.uint8)
        n, labels = cv2.connectedComponents(weak_u8, connectivity=8)
        if n <= 1:
            return strong.astype(np.uint8) * 255
        keep = np.zeros(n, bool)
        keep[np.unique(labels[strong])] = True
        keep[0] = False
        return keep[labels].astype(np.uint8) * 255

    def segment_leather(self, frame):
        """Returns (contour_in_full_frame_coords, area_px) or (None, 0)."""
        if self.reference_lab is None:
            self.calibrate_belt(frame)
            return None, 0

        lab = self._prep(frame)
        mask = self._difference_mask(lab)

        # Remove speckle, then close small gaps (creases, holes, stains).
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        )
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)),
        )

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        contour = None
        area = 0.0
        if contours:
            largest = max(contours, key=cv2.contourArea)
            area_small = cv2.contourArea(largest)
            area = area_small * self.downscale * self.downscale

            too_small = area < self.min_area_ratio * self.frame_area
            too_big = area > self.max_area_ratio * self.frame_area

            if not too_small and not too_big:
                # Light smoothing; keeps real outline (not a convex hull, which
                # added belt area to irregular pieces).
                eps = 0.004 * cv2.arcLength(largest, True)
                smooth = cv2.approxPolyDP(largest, eps, True)
                contour = (smooth.astype(np.float32) * self.downscale).astype(
                    np.int32
                )
            else:
                area = 0.0

        self._adapt_reference(lab, contour)
        return (contour, area) if contour is not None else (None, 0)

    def _adapt_reference(self, lab, contour):
        """Follow slow lighting changes using belt pixels only."""
        if self.adapt_rate <= 0:
            return

        belt = np.ones((self.small_h, self.small_w), np.uint8)
        if contour is not None:
            small_cnt = (contour.astype(np.float32) / self.downscale).astype(
                np.int32
            )
            cv2.drawContours(belt, [small_cnt], -1, 0, -1)
            belt = cv2.erode(belt, np.ones((25, 25), np.uint8))

        sel = belt.astype(bool)
        a = self.adapt_rate
        self.reference_lab[sel] = (1 - a) * self.reference_lab[sel] + a * lab[sel]

    def piece_mask(self, contour):
        """Full-resolution filled mask of the piece (for defect ratios)."""
        mask = np.zeros((self.frame_height, self.frame_width), np.uint8)
        if contour is not None:
            cv2.drawContours(mask, [contour], -1, 255, -1)
        return mask

    def get_centroid(self, contour):
        if contour is None:
            return None
        M = cv2.moments(contour)
        if M["m00"] == 0:
            return None
        return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

    # -------------------------------------------------------------
    # Grading
    # -------------------------------------------------------------

    @staticmethod
    def iso_grade(ratio):
        """ISO 17551:2018 Section 5 defect-area bands."""
        if ratio <= 10:
            return "I"
        if ratio <= 20:
            return "II"
        if ratio <= 40:
            return "III"
        if ratio <= 70:
            return "IV"
        return "V"

    def grade_piece(self, detections, piece_area, manual_defect_px=None):
        """
        detections: list of (class_name, area) - only defects ON the piece.
        Returns (grade, ratio_percent, reason).
        """
        if piece_area <= 0:
            return "NO LEATHER", 0.0, "empty belt"

        defect_area = (
            manual_defect_px
            if manual_defect_px is not None
            else sum(a for _, a in detections)
        )
        ratio = 100.0 * defect_area / piece_area
        count = len(detections)
        iso = self.iso_grade(ratio)

        reasons = []

        critical = [n for n, _ in detections if n in self.critical_classes]
        if critical:
            reasons.append(f"critical {critical[0]}")

        if count > self.max_defect_count:
            reasons.append(f"{count} defects > {self.max_defect_count}")

        if ratio >= self.defect_ratio_thresh:
            reasons.append(f"area {ratio:.1f}% >= {self.defect_ratio_thresh:.0f}%")

        if reasons:
            return "BAD", ratio, f"ISO {iso} | " + ", ".join(reasons)

        return "GOOD", ratio, f"ISO {iso} | {count} defects, {ratio:.1f}%"

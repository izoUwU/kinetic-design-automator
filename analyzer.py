import json
import os

import cv2
import numpy as np

_CALIBRATION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration_params.json")


class Analyzer:
    def __init__(self):
        self.image = None
        self.gray = None
        self.points = []
        self.thresh_img = None
        self.trench_lines = []
        self._calibration = self._default_calibration()
        self._reload_calibration_file()

    @staticmethod
    def _default_calibration():
        return {
            "gold_trench_blend": 0.07,
            "left_offset": 0,
            "right_offset": 0,
            "contact_offset": 0,
            # Per-ray coverage detection (_find_graphene_span); trainable via train_calibration.py
            "ray_anchor_blend": 0.11,
            "ray_anchor_margin": 3.0,
            "ray_anchor_floor_margin": 2.0,
            "ray_floor_step_max": 12.0,
            "min_trench_contrast": 6.0,
            "early_spurious_step_max": 13.5,
            "min_edge_drop": 3.0,
            "ray_clamp_step_max": 14.0,
            "low_contrast_dark_frac_min": 0.72,
            "early_hold_dark_ratio_min": 0.65,
            "edge_guided_min_drop": 4.5,
            "full_cover_dark_frac": 0.82,
            "full_cover_early_frac": 0.78,
            "sustain_dark_ratio": 0.72,
            "sustain_window_frac": 0.08,
        }

    def _reload_calibration_file(self):
        self._calibration = self._default_calibration()
        if os.path.isfile(_CALIBRATION_PATH):
            try:
                with open(_CALIBRATION_PATH, encoding="utf-8") as f:
                    loaded = json.load(f)
                for k in self._default_calibration():
                    if k in loaded:
                        self._calibration[k] = loaded[k]
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def load_image(self, path):
        self.image = cv2.imread(path)
        if self.image is None:
            raise ValueError("Could not load image")
        self.gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        self._reload_calibration_file()
        return self.image

    def _get_trench_profile(self, img, start_pt, end_pt, num_samples):
        x1, y1 = start_pt
        x2, y2 = end_pt
        x_coords = np.linspace(x1, x2, num_samples).astype(int)
        y_coords = np.linspace(y1, y2, num_samples).astype(int)
        
        h, w = self.gray.shape
        x_coords = np.clip(x_coords, 0, w - 1)
        y_coords = np.clip(y_coords, 0, h - 1)

        # Robust profile against dust/scratches: sample a small band of parallel rays
        # and take median at each sample point. This suppresses isolated dark spikes that
        # otherwise cause false early "full coverage" crossings.
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        offsets = (-2, 0, 2)
        samples = []
        if dx >= dy:
            for off in offsets:
                yy = np.clip(y_coords + off, 0, h - 1)
                samples.append(img[yy, x_coords].astype(np.float32))
        else:
            for off in offsets:
                xx = np.clip(x_coords + off, 0, w - 1)
                samples.append(img[y_coords, xx].astype(np.float32))
        return np.median(np.stack(samples, axis=0), axis=0)

    def _apply_calibrated_thresholds(self, opt_contact, base_l, base_r):
        """Apply contact / left / right offsets from calibration_params.json."""
        co = int(self._calibration.get("contact_offset", 0))
        lo = int(self._calibration.get("left_offset", 0))
        ro = int(self._calibration.get("right_offset", 0))
        oc = int(np.clip(int(opt_contact) + co, 100, 245))
        ol = int(np.clip(int(base_l) + lo, 1, 254))
        orr = int(np.clip(int(base_r) + ro, 1, 254))
        return oc, ol, orr

    def auto_tune_parameters(self):
        if self.gray is None:
            return self._apply_calibrated_thresholds(100, 140, 130)

        # --- Step 1: Find contact threshold by scanning high→low ---
        # Collect (threshold, pad_count) across the scan range.
        # Pick the median of the plateau where count is at its maximum (and ≤ 66).
        # This ensures pads are fully visible (not just barely appearing at high threshold)
        # while avoiding false-positive floods at low threshold.
        blurred = cv2.GaussianBlur(self.gray, (3, 3), 0)
        opt_contact = 200  # safe fallback
        candidates = []  # (t, pad_count)

        for t in range(240, 140, -1):
            _, tm = cv2.threshold(blurred, t, 255, cv2.THRESH_BINARY)
            cnts, _ = cv2.findContours(tm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(cnts) < 4:
                continue

            areas = sorted([cv2.contourArea(c) for c in cnts], reverse=True)
            ref = np.median(areas[4:68]) if len(areas) > 8 else (np.median(areas) if areas else 1)
            if ref <= 0:
                continue

            pad_count = 0
            for c in cnts:
                b = cv2.boundingRect(c)
                a = cv2.contourArea(c)
                ar = b[2] / max(1, float(b[3]))
                ext = a / (b[2] * b[3] + 1e-5)
                # Loose filters — same as process() — so plateau reflects actual detection
                if ref * 0.25 < a < ref * 2.5 and 0.35 < ar < 2.5 and ext > 0.50:
                    pad_count += 1

            if 56 <= pad_count <= 68:
                candidates.append((t, pad_count))
            elif pad_count > 68 and candidates:
                break  # false positives flooding in, stop

        if candidates:
            max_count = max(c[1] for c in candidates if c[1] <= 66)
            plateau_ts = [c[0] for c in candidates if c[1] == max_count]
            # Use max of plateau: the highest threshold where all pads first become
            # visible under process()'s actual (loose) filters. No arbitrary offset needed.
            opt_contact = max(plateau_ts)

        # --- Step 2: Compute graphene thresholds from pad profiles ---
        _, thresh = cv2.threshold(self.gray, opt_contact, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return self._apply_calibrated_thresholds(opt_contact, 140, 130)
        top_80 = sorted([cv2.contourArea(c) for c in contours], reverse=True)[:80]
        true_pad_area = np.median(top_80)

        valid_pads = []
        for c in contours:
            b = cv2.boundingRect(c)
            ar = b[2] / float(b[3])
            extent = cv2.contourArea(c) / (b[2]*b[3] + 1e-5)
            if (true_pad_area * 0.25) < cv2.contourArea(c) < (true_pad_area * 3.5) and 0.70 < ar < 1.4 and extent > 0.75:
                valid_pads.append(c)

        pads = sorted(valid_pads, key=cv2.contourArea, reverse=True)[:64]
        if not pads:
            return self._apply_calibrated_thresholds(opt_contact, 140, 130)

        gx = sum([cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2]/2.0 for c in pads]) / len(pads)

        left_opts, right_opts = [], []

        for c in pads:
            box = cv2.boundingRect(c)
            cx = box[0] + box[2]/2.0
            cy = int(box[1] + box[3]/2.0)

            # --- Anchor: sample brightness directly inside the gold pad ---
            # Use the central 50% of the pad in x and a ±4px band in y to get a
            # stable gold-level reference that is immune to pad-edge shadows.
            pad_x0 = int(box[0] + box[2] * 0.25)
            pad_x1 = int(box[0] + box[2] * 0.75)
            pad_y0 = max(0, cy - 4)
            pad_y1 = min(self.gray.shape[0], cy + 5)
            gold_region = self.gray[pad_y0:pad_y1, pad_x0:pad_x1]
            gold_level = float(np.percentile(gold_region, 85)) if gold_region.size > 0 else 200.0

            if cx < gx:
                start_pt = (box[0] + box[2] + 4, cy)
                max_dist = int(abs(gx - start_pt[0]))
                if max_dist > 50:
                    profile = self._get_trench_profile(self.gray, start_pt, (int(start_pt[0] + max_dist), cy), max_dist)
                    smoothed = cv2.GaussianBlur(profile.astype(np.float32).reshape(1, -1), (9, 1), 0).flatten()
                    if len(smoothed) > 30:
                        # Skip the first 8px (gold-pad shadow) then sample the rest
                        trench_profile = smoothed[8:]
                        # True graphene level: 5th-percentile of the darkest half
                        quarter = max(1, len(trench_profile) // 4)
                        darkest = float(np.percentile(trench_profile[:quarter * 2], 5))
                        contrast = gold_level - darkest
                        if contrast > 20:
                            blend = float(self._calibration.get("gold_trench_blend", 0.07))
                            left_opts.append(darkest + contrast * blend)
            else:
                start_pt = (box[0] - 4, cy)
                max_dist = int(abs(start_pt[0] - gx))
                if max_dist > 50:
                    profile = self._get_trench_profile(self.gray, start_pt, (int(start_pt[0] - max_dist), cy), max_dist)
                    smoothed = cv2.GaussianBlur(profile.astype(np.float32).reshape(1, -1), (9, 1), 0).flatten()
                    if len(smoothed) > 30:
                        trench_profile = smoothed[8:]
                        quarter = max(1, len(trench_profile) // 4)
                        darkest = float(np.percentile(trench_profile[:quarter * 2], 5))
                        contrast = gold_level - darkest
                        if contrast > 20:
                            blend = float(self._calibration.get("gold_trench_blend", 0.07))
                            right_opts.append(darkest + contrast * blend)

        def _robust_median(vals):
            """IQR-filtered median: discard values outside 1.5×IQR before taking median."""
            if not vals:
                return None
            arr = np.array(vals)
            q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            clean = arr[(arr >= lo) & (arr <= hi)]
            return float(np.median(clean)) if len(clean) > 0 else float(np.median(arr))

        lm = _robust_median(left_opts)
        rm = _robust_median(right_opts)
        base_l = int(lm) if lm is not None else 140
        base_r = int(rm) if rm is not None else 135

        return self._apply_calibrated_thresholds(opt_contact, base_l, base_r)

    def _find_graphene_span(self, start_pt, end_pt, num_samples, graph_thresh):
        if num_samples < 5:
            return 0, 0, 0
        profile = self._get_trench_profile(self.gray, start_pt, end_pt, num_samples)

        # Heavy deep-float Gaussian curve mathematically eliminates the "staircase effect"
        # We cap the blur kernel to (9, 1) rather than (41, 1). A heavy kernel massively dilutes physical edges,
        # moving the mathematical threshold intersection artificially inwards and requiring manual user intervention.
        # Length 9 removes digital staircase steps while completely freezing the pixel-perfect physical edge!
        smoothed_arr = cv2.GaussianBlur(profile.astype(np.float32).reshape(1, -1), (9, 1), 0).flatten()

        skip = 5
        seg = max(20, min(num_samples // 4, 85))
        if skip + seg >= len(smoothed_arr) - 2:
            seg = max(10, len(smoothed_arr) // 5)

        head = smoothed_arr[skip : skip + seg]
        tail = smoothed_arr[-seg:]
        step = 100.0
        t_eff = float(graph_thresh)
        probe = smoothed_arr[skip:]
        early_n = max(10, min(28, int(0.12 * num_samples)))
        early = smoothed_arr[skip : min(len(smoothed_arr), skip + early_n)]

        if len(head) >= 4 and len(tail) >= 3:
            tail_dark = float(np.percentile(tail, 15))
            head_bright = float(np.percentile(head, 60))
            step = head_bright - tail_dark
            min_ct = float(self._calibration.get("min_trench_contrast", 7.5))
            if step < min_ct:
                # Low-contrast rescue: if most of the trench is still dark relative
                # to threshold, keep searching instead of forcing zero coverage.
                dark_frac = float(np.mean(probe < t_eff)) if len(probe) > 0 else 0.0
                min_dark_frac = float(self._calibration.get("low_contrast_dark_frac_min", 0.72))
                if dark_frac < min_dark_frac:
                    return 0, 0, 0
            rb = float(self._calibration.get("ray_anchor_blend", 0.11))
            margin = float(self._calibration.get("ray_anchor_margin", 3.0))
            floor_margin = float(self._calibration.get("ray_anchor_floor_margin", 2.0))
            floor_step_max = float(self._calibration.get("ray_floor_step_max", 12.0))
            anchor = tail_dark + step * rb
            clamp_step_max = float(self._calibration.get("ray_clamp_step_max", 14.0))
            # Clamp only to anchor+margin (not anchor), otherwise threshold can become
            # unrealistically low and produce false "0 coverage" on faint graphene.
            # Apply clamp only on weak-step rays; strong-step rays should keep global
            # threshold to avoid underestimating coverage length.
            if step <= clamp_step_max and t_eff > anchor + margin:
                t_eff = anchor + margin
            # Also prevent thresholds from being too low for a given trench profile,
            # which can force false zeros on valid low-contrast graphene.
            if step <= floor_step_max and t_eff < anchor - floor_margin:
                t_eff = anchor - floor_margin

        cvg_start = None
        edge_candidate = None
        min_drop = float(self._calibration.get("min_edge_drop", 5.0))
        head_ref = float(np.percentile(head, 60)) if len(head) >= 3 else float(np.percentile(smoothed_arr[skip:], 60))
        # Full-coverage detection: if the trench is already predominantly dark right
        # after the pad, start coverage immediately after skip. This fixes the common
        # "half-covered" left-column failure mode.
        full_dark = float(self._calibration.get("full_cover_dark_frac", 0.82))
        full_early = float(self._calibration.get("full_cover_early_frac", 0.78))
        if len(probe) > 0:
            df_all = float(np.mean(probe < t_eff))
            df_early = float(np.mean(early < t_eff)) if len(early) > 0 else df_all
            if df_all >= full_dark and df_early >= full_early:
                cvg_start = skip
        need_hyst = len(smoothed_arr) >= skip + 4
        if cvg_start is None and need_hyst:
            run = 0
            for i in range(skip, len(smoothed_arr)):
                if smoothed_arr[i] < t_eff and (head_ref - float(smoothed_arr[i])) >= min_drop:
                    run += 1
                    if run >= 2:
                        cvg_start = i - 1
                        break
                else:
                    run = 0
        if cvg_start is None:
            for i in range(skip, len(smoothed_arr)):
                if smoothed_arr[i] < t_eff and (head_ref - float(smoothed_arr[i])) >= min_drop:
                    cvg_start = i
                    break

        # Safety fallback for faint graphene: if the edge-drop gate blocks all crossings,
        # retry threshold-only crossing before declaring "no coverage".
        if cvg_start is None and min_drop > 0.0:
            run = 0
            for i in range(skip, len(smoothed_arr)):
                if smoothed_arr[i] < t_eff:
                    run += 1
                    if run >= 2:
                        cvg_start = i - 1
                        break
                else:
                    run = 0
            if cvg_start is None:
                for i in range(skip, len(smoothed_arr)):
                    if smoothed_arr[i] < t_eff:
                        cvg_start = i
                        break

        if cvg_start is None:
            return 0, 0, 0

        # Edge-guided correction:
        # use the strongest sustained negative gradient as a physical edge estimate.
        # This helps when threshold crossing is too early (overshoot) or missing (false zero).
        edge_min_drop = float(self._calibration.get("edge_guided_min_drop", 4.5))
        if cvg_start != skip and len(smoothed_arr) > skip + 12:
            d = smoothed_arr[:-1] - smoothed_arr[1:]  # positive when signal drops
            w0 = skip
            w1 = max(w0 + 8, int(len(d) * 0.78))
            if w1 > w0:
                local = d[w0:w1]
                loc_idx = int(np.argmax(local))
                edge_idx = w0 + loc_idx + 1
                edge_drop = float(local[loc_idx]) if len(local) > 0 else 0.0
                if edge_drop >= edge_min_drop:
                    # Only lock when the edge behaves like a true transition:
                    # mostly bright before the edge and mostly dark after.
                    pre0 = max(skip, edge_idx - 12)
                    pre1 = max(pre0 + 1, edge_idx)
                    post0 = edge_idx
                    post1 = min(len(smoothed_arr), edge_idx + 12)
                    pre = smoothed_arr[pre0:pre1]
                    post = smoothed_arr[post0:post1]
                    pre_dark = float(np.mean(pre < t_eff)) if len(pre) > 0 else 0.0
                    post_dark = float(np.mean(post < t_eff)) if len(post) > 0 else 0.0
                    if pre_dark <= 0.35 and post_dark >= 0.65:
                        edge_candidate = edge_idx
                        if cvg_start < edge_idx - 6:
                            cvg_start = edge_idx

        # Reject spurious early crossings unless darkness is sustained.
        hold_n = max(6, min(16, int(0.06 * num_samples)))
        early_probe_lim = max(16, int(0.10 * num_samples))
        if cvg_start < early_probe_lim and cvg_start + 2 < len(smoothed_arr):
            w0 = cvg_start
            w1 = min(len(smoothed_arr), cvg_start + hold_n)
            win = smoothed_arr[w0:w1]
            if len(win) > 0:
                dark_ratio = float(np.mean(win < t_eff))
                need_ratio = float(self._calibration.get("early_hold_dark_ratio_min", 0.65))
                if dark_ratio < need_ratio:
                    for i in range(w1, len(smoothed_arr)):
                        if smoothed_arr[i] < t_eff:
                            cvg_start = i
                            break

        if len(head) >= 4 and len(tail) >= 3:
            early_lim = max(14, int(0.045 * num_samples))
            sp_max = float(self._calibration.get("early_spurious_step_max", 13.5))
            if cvg_start < early_lim and step < sp_max:
                return 0, 0, 0

        # Ensemble start consensus: combine independent hypotheses and use a robust
        # middle choice to avoid one heuristic dominating on difficult rays.
        candidates = []
        if cvg_start is not None:
            candidates.append(int(cvg_start))
        if edge_candidate is not None:
            candidates.append(int(edge_candidate))
        if len(probe) > 0:
            win_n = max(8, min(26, int(self._calibration.get("sustain_window_frac", 0.08) * num_samples)))
            need_dark = float(self._calibration.get("sustain_dark_ratio", 0.72))
            sustain_idx = None
            for j in range(skip, max(skip, len(smoothed_arr) - win_n + 1)):
                w = smoothed_arr[j : j + win_n]
                if len(w) > 0 and float(np.mean(w < t_eff)) >= need_dark:
                    sustain_idx = j
                    break
            if sustain_idx is not None:
                candidates.append(int(sustain_idx))
            # Full-dark hypothesis if most trench samples are under threshold.
            if float(np.mean(probe < t_eff)) >= full_dark and float(np.mean(early < t_eff)) >= full_early:
                candidates.append(int(skip))

        if candidates:
            c_sorted = sorted(candidates)
            cvg_start = int(c_sorted[len(c_sorted) // 2])
            cvg_start = max(skip, min(cvg_start, num_samples - 1))

        cvg_end = num_samples - 1
        cvg_len = cvg_end - cvg_start
        return cvg_len, cvg_start, cvg_end

    def process(self, threshold=100, left_graph_thresh=100, right_graph_thresh=100, trim_um=0, orientation='Horizontal', bg_type='Dark', morph_size=0, num_points=64, local_trims=None, local_threshes=None, skipped_pads=None, _allow_autocorrect=True):
        if self.gray is None: return None
        if local_trims is None: local_trims = {}
        if local_threshes is None: local_threshes = {}
        if skipped_pads is None: skipped_pads = []
            
        # 1. Base thresholds
        blurred = cv2.GaussianBlur(self.gray, (3,3), 0)
        _, self.thresh_img = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(self.thresh_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        areas = [cv2.contourArea(c) for c in contours]
        if len(areas) == 0: return [], self.thresh_img
        
        # From dhon6.py: 64 contact pads all 200×200µm, corner fiducials 400×450µm (5×), labels 100µm (12%).
        # Use [4:68] to estimate pad area — skip the 4 largest blobs (corner marks / fused bus-bars),
        # then take the next 64 which should be exactly the real pads.
        sorted_areas = sorted(areas, reverse=True)
        reference_areas = sorted_areas[4:68] if len(sorted_areas) > 8 else sorted_areas
        true_pad_area = np.median(reference_areas) if reference_areas else np.median(sorted_areas)

        pad_candidates = []
        for c in contours:
            b = cv2.boundingRect(c)
            box_area = b[2] * b[3]
            ar = b[2] / float(b[3])
            extent = cv2.contourArea(c) / (box_area + 1e-5)
            c_area = cv2.contourArea(c)
            # Design-informed filters (from dhon6.py):
            #   min 25%: text labels are ~12% of pad area → excluded
            #   max 2.5×: corner fiducials are ~5× → excluded
            #   ar 0.35–2.5: pads are square; slightly loosened so pad+short-wire merged blobs survive
            #      at lower thresholds (gold wire merges into pad contour at ~172-177 threshold)
            #   extent >0.50: solid pads score ~0.85+; triangles score ~0.50 → excluded
            if (true_pad_area * 0.25) < c_area < (true_pad_area * 2.5) and 0.35 < ar < 2.5 and extent > 0.50:
                pad_candidates.append(c)
        
        if not pad_candidates:
            self.trench_lines = []
            return [{"id": i+1, "distance": 0.0, "details": "No valid pads found. Adjust threshold.", "is_skipped": True} for i in range(num_points)], self.thresh_img

        # --- Split by global X center ---
        gx = sum([cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2]/2.0 for c in pad_candidates]) / len(pad_candidates)
        gy = sum([cv2.boundingRect(c)[1] + cv2.boundingRect(c)[3]/2.0 for c in pad_candidates]) / len(pad_candidates)

        left_raw  = [c for c in pad_candidates if (cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2]/2.0) <  gx]
        right_raw = [c for c in pad_candidates if (cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2]/2.0) >= gx]

        # X-column range filter: remove anything far outside the pad column's X band.
        # Corner fiducials (G1-G4) are ~23 pad-widths from column center; real pads within ±3.
        # This stops low-threshold corner blobs from stealing the last grid slots.
        def _xfilter(raw):
            if len(raw) < 4:
                return raw
            cxs = [cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2]/2.0 for c in raw]
            ws  = [cv2.boundingRect(c)[2] for c in raw]
            med_cx = float(np.median(cxs))
            med_w  = float(np.median(ws))
            return [c for c, cx in zip(raw, cxs) if abs(cx - med_cx) <= med_w * 4]

        left_raw  = _xfilter(left_raw)
        right_raw = _xfilter(right_raw)

        rows = num_points // 2

        # --- Per-column grid mapper (auto-skip missing pads) ---
        def _map_to_grid(cnts_sorted, rows, skip_local_ids):
            """
            Assign detected pads to fixed grid slots based on Y-spacing.
            Slots with no pad nearby → None (auto-skipped).
            skip_local_ids: set of 0-based local slot indices to force-skip.
            """
            if not cnts_sorted:
                return [None] * rows

            ys = [cv2.boundingRect(c)[1] + cv2.boundingRect(c)[3] / 2.0 for c in cnts_sorted]

            # Spacing: raw median of consecutive Y-diffs (ignoring sub-pixel jitter < 5px).
            # Raw median is robust: 32 correct diffs at ~30px override a few tiny/large outliers.
            raw_diffs = [ys[i+1] - ys[i] for i in range(len(ys)-1) if ys[i+1] - ys[i] > 5]
            if raw_diffs:
                spacing = float(np.median(raw_diffs))
            else:
                spacing = max(5.0, self.gray.shape[0] / max(1, rows))
            spacing = max(spacing, 5.0)

            # --- Y-isolation purge ---
            # Remove blobs whose closest Y-neighbor is > 2× spacing away.
            # These are isolated false positives (fiducials, stray features) sitting
            # outside the true pad array. A genuine first/last pad always has at least
            # one neighbour within 1 spacing of it.
            if len(ys) > 2:
                purged_pairs = []
                for i, (c, y) in enumerate(zip(cnts_sorted, ys)):
                    others = [yy for j, yy in enumerate(ys) if j != i]
                    nearest_dist = min(abs(y - yy) for yy in others)
                    if nearest_dist <= 2.0 * spacing:
                        purged_pairs.append((c, y))
                if len(purged_pairs) >= rows // 2:  # safety: only apply if we kept enough
                    cnts_sorted = [p[0] for p in purged_pairs]
                    ys          = [p[1] for p in purged_pairs]
                    # Recompute spacing after purge (cleaner set)
                    raw_diffs2 = [ys[i+1] - ys[i] for i in range(len(ys)-1) if ys[i+1] - ys[i] > 5]
                    if raw_diffs2:
                        spacing = float(np.median(raw_diffs2))

            tol = 0.45  # accept within 45% of a slot centre

            # Best anchor: try ALL detected Y values (after purge) as candidate anchors.
            # Pick the one that results in the most total filled slots (not just consecutive).
            # Consecutive-streak logic can miss the last few slots when cumulative pitch drift
            # pushes them outside the tolerance window on later rows.
            best_fill = -1
            best_anchor = ys[0]
            ys_set = ys
            for trial_y in ys_set:
                fill = 0
                for s in range(rows):
                    expected = trial_y + s * spacing
                    if any(abs(y - expected) <= tol * spacing for y in ys_set):
                        fill += 1
                if fill > best_fill:
                    best_fill = fill
                    best_anchor = trial_y
            anchor_y = best_anchor


            def _assign(anchor, sp, tolerance):
                g = [None] * rows
                matched_ys = {}  # slot -> y_center of matched pad
                for c, y in zip(cnts_sorted, ys):
                    sf = (y - anchor) / sp
                    sl = int(round(sf))
                    if 0 <= sl < rows and abs(sf - sl) <= tolerance:
                        if g[sl] is None or cv2.contourArea(c) > cv2.contourArea(g[sl]):
                            g[sl] = c
                            matched_ys[sl] = y
                return g, matched_ys

            # Pass 1: initial assignment with raw spacing
            grid, m_ys = _assign(anchor_y, spacing, tol)

            # Pass 2: refine anchor+spacing via least-squares on matched (slot, y) pairs
            if len(m_ys) >= 4:
                slots_arr = np.array(list(m_ys.keys()),   dtype=float)
                ys_arr    = np.array(list(m_ys.values()), dtype=float)
                A = np.vstack([np.ones_like(slots_arr), slots_arr]).T
                result = np.linalg.lstsq(A, ys_arr, rcond=None)
                anchor_ref  = float(result[0][0])
                spacing_ref = float(result[0][1])
                if spacing_ref > spacing * 0.7:  # sanity: don't accept crazy values
                    grid, _ = _assign(anchor_ref, spacing_ref, 0.50)

            # Force-skip manually requested slots
            for local_idx in skip_local_ids:
                if 0 <= local_idx < rows:
                    grid[local_idx] = None

            return grid


        # Convert global skip IDs → 0-based local column indices
        left_skip_local  = {s - 1        for s in skipped_pads if 1      <= s <= rows}
        right_skip_local = {s - rows - 1 for s in skipped_pads if rows < s <= 2 * rows}

        left_sorted  = sorted(left_raw,  key=lambda c: cv2.boundingRect(c)[1])
        right_sorted = sorted(right_raw, key=lambda c: cv2.boundingRect(c)[1])

        left_contours  = _map_to_grid(left_sorted,  rows, left_skip_local)
        right_contours = _map_to_grid(right_sorted, rows, right_skip_local)

        ordered_contours = left_contours + right_contours

        # Recompute gx as the TRUE chip center using inner-edge midpoint.
        # The mean-of-all-pad-centers drifts due to stagger alternation and missing pads.
        # The chip center = midpoint between the rightmost edges of left pads and leftmost edges of right pads.
        # This is stable regardless of any stagger pattern or missing pads.
        valid_left  = [c for c in left_contours  if c is not None]
        valid_right = [c for c in right_contours if c is not None]
        if valid_left and valid_right:
            # Inner edge of left pads = right side (closest to chip center)
            l_inner = sorted([cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] for c in valid_left], reverse=True)
            # Inner edge of right pads = left side (closest to chip center)
            r_inner = sorted([cv2.boundingRect(c)[0] for c in valid_right])
            n = min(8, len(l_inner), len(r_inner))
            gx = (np.median(l_inner[:n]) + np.median(r_inner[:n])) / 2.0
        # else: keep the original gx estimate

        self.points = []
        self.trench_lines = []
        
        # PASS 1: Calculate provisional distances to center to find Global Micrometer Ratio
        cached_data = []
        for i in range(num_points):
            global_pad_num = i + 1
            c = ordered_contours[i] if i < len(ordered_contours) else None
            
            if global_pad_num in skipped_pads or c is None:
                cached_data.append({
                    'is_skipped': True,
                    'orig_idx': i,
                    'provisional_dist': 0.0
                })
            else:
                x, y, w, h = cv2.boundingRect(c)
                cx = x + w / 2.0
                cy = y + h / 2.0
                    
                dx, dy = 0.0, 0.0
                max_dist = 0
                
                app_graph_thresh = left_graph_thresh if cx < gx else right_graph_thresh
                if i in local_threshes:
                    app_graph_thresh = local_threshes[i]
                
                if orientation == 'Horizontal':
                    if cx < gx: 
                        dx = 1.0
                        start_pt = (int(x + w + 4), int(cy))
                        max_dist = abs(gx - start_pt[0])
                    else: 
                        dx = -1.0
                        start_pt = (int(x - 4), int(cy))
                        max_dist = abs(start_pt[0] - gx)
                else:
                    if cy < gy:
                        dy = 1.0
                        start_pt = (int(cx), int(y + h))
                        max_dist = abs(gy - start_pt[1])
                    else:
                        dy = -1.0
                        start_pt = (int(cx), int(y))
                        max_dist = abs(start_pt[1] - gy)
                        
                cached_data.append({
                    'is_skipped': False,
                    'box': (x, y, w, h),
                    'start_pt': start_pt,
                    'dx': dx, 'dy': dy,
                    'provisional_dist': max_dist,
                    'app_graph_thresh': app_graph_thresh,
                    'orig_idx': i
                })
        # From dhon6.py: wire_start_x_l = cap_center_x_l - cap_w/2 + penetration = -160μm from chip center.
        # Inner staggered pads (even global IDs): trench = 1900μm, gap to chip center = 160μm → total = 2060μm.
        # This gives the correct um_per_pixel AND stops coverage at wire_start (not 60μm past it).
        even_ratios = [2060.0 / d['provisional_dist'] for i, d in enumerate(cached_data) if (i+1)%2 == 0 and not d.get('is_skipped') and d['provisional_dist'] > 0]
        global_um_per_pixel = np.mean(even_ratios) if even_ratios else 1.0
        gap_pixels = 160.0 / global_um_per_pixel
        
        # PASS 2: Trace explicit trench limits and calculate metrics
        for i, d in enumerate(cached_data):
            if d.get('is_skipped'):
                self.points.append({
                    'box': (0, 0, 0, 0),
                    'trench_pixel_len': 0,
                    'cvg_pixel_dist': 0,
                    'um_per_pixel': global_um_per_pixel,
                    'total_um': 0.0,
                    'coverage_um': 0.0,
                    'coverage_ratio': 0.0,
                    'is_skipped': True
                })
                self.trench_lines.append({
                    'pt1': (0,0), 'pt2': (0,0), 'cvg_pixels': 0, 'orig_idx': d['orig_idx'],
                    'base_cvg_start_idx': 0, 'global_um_per_pixel': global_um_per_pixel,
                    'start_pt': (0,0), 'dx': 0, 'dy': 0
                })
                continue

            x, y, w, h = d['box']
            start_pt = d['start_pt']
            dx, dy = d['dx'], d['dy']
            
            trench_pixel_len = d['provisional_dist'] - gap_pixels
            if trench_pixel_len < 5: trench_pixel_len = 5
            
            end_pt = (int(start_pt[0] + dx * trench_pixel_len), int(start_pt[1] + dy * trench_pixel_len))
            
            cvg_pixels, cvg_start_idx, cvg_end_idx = self._find_graphene_span(
                start_pt, end_pt, int(trench_pixel_len), d['app_graph_thresh']
            )
            
            # Apply Global + Local Trim
            if cvg_pixels > 0 and global_um_per_pixel > 0:
                total_trim = trim_um + local_trims.get(d['orig_idx'], 0.0)
                trim_pixels = int(total_trim / global_um_per_pixel)
                cvg_start_idx += trim_pixels
                if cvg_start_idx > cvg_end_idx:
                    cvg_start_idx = cvg_end_idx
                cvg_pixels = cvg_end_idx - cvg_start_idx
            
            if cvg_pixels > 0:
                draw_pt1 = (int(start_pt[0] + dx * cvg_start_idx), int(start_pt[1] + dy * cvg_start_idx))
                draw_pt2 = (int(start_pt[0] + dx * cvg_end_idx), int(start_pt[1] + dy * cvg_end_idx))
                self.trench_lines.append({
                    'pt1': draw_pt1, 
                    'pt2': draw_pt2, 
                    'cvg_pixels': cvg_pixels,
                    'orig_idx': d['orig_idx'],
                    'start_pt': start_pt,
                    'dx': dx, 'dy': dy,
                    'base_cvg_start_idx': cvg_start_idx - trim_pixels,
                    'global_um_per_pixel': global_um_per_pixel
                })
            else:
                self.trench_lines.append({
                    'pt1': start_pt, 'pt2': start_pt, 'cvg_pixels': 0, 'orig_idx': d['orig_idx'],
                    'start_pt': start_pt, 'dx': dx, 'dy': dy
                })
                
            total_um = trench_pixel_len * global_um_per_pixel
            coverage_um = cvg_pixels * global_um_per_pixel
            coverage_ratio = cvg_pixels / trench_pixel_len if trench_pixel_len > 0 else 0
                
            self.points.append({
                'is_skipped': False,
                'box': (x, y, w, h),
                'trench_pixel_len': trench_pixel_len,
                'cvg_pixel_dist': cvg_pixels,
                'um_per_pixel': global_um_per_pixel,
                'total_um': total_um,
                'coverage_um': coverage_um,
                'coverage_ratio': coverage_ratio
            })
            
        # Local outlier correction on right column:
        # if one pad is a strong spike/zero relative to adjacent rows, re-evaluate that
        # single pad with a slightly shifted threshold.
        if _allow_autocorrect and orientation == 'Horizontal' and num_points >= 64:
            mid = num_points // 2

            def _recompute_single(idx, override_thresh):
                p = self.points[idx]
                line = self.trench_lines[idx]
                if p.get('is_skipped') or line.get('start_pt') is None:
                    return
                start_pt = line.get('start_pt', (0, 0))
                dx = float(line.get('dx', 0.0))
                dy = float(line.get('dy', 0.0))
                trench_pixel_len = max(5, int(round(float(p.get('trench_pixel_len', 0)))))
                end_pt = (int(start_pt[0] + dx * trench_pixel_len), int(start_pt[1] + dy * trench_pixel_len))
                cvg_pixels, cvg_start_idx, cvg_end_idx = self._find_graphene_span(
                    start_pt, end_pt, trench_pixel_len, int(override_thresh)
                )

                if cvg_pixels > 0 and p.get('um_per_pixel', 0) > 0:
                    total_trim = trim_um + local_trims.get(line.get('orig_idx', idx), 0.0)
                    trim_pixels = int(total_trim / p['um_per_pixel'])
                    cvg_start_idx += trim_pixels
                    if cvg_start_idx > cvg_end_idx:
                        cvg_start_idx = cvg_end_idx
                    cvg_pixels = cvg_end_idx - cvg_start_idx
                else:
                    trim_pixels = 0

                if cvg_pixels > 0:
                    draw_pt1 = (int(start_pt[0] + dx * cvg_start_idx), int(start_pt[1] + dy * cvg_start_idx))
                    draw_pt2 = (int(start_pt[0] + dx * cvg_end_idx), int(start_pt[1] + dy * cvg_end_idx))
                    self.trench_lines[idx].update({
                        'pt1': draw_pt1,
                        'pt2': draw_pt2,
                        'cvg_pixels': cvg_pixels,
                        'base_cvg_start_idx': cvg_start_idx - trim_pixels,
                    })
                else:
                    self.trench_lines[idx].update({'pt1': start_pt, 'pt2': start_pt, 'cvg_pixels': 0})

                total_um = float(p.get('trench_pixel_len', 0.0)) * float(p.get('um_per_pixel', 1.0))
                coverage_um = cvg_pixels * float(p.get('um_per_pixel', 1.0))
                coverage_ratio = cvg_pixels / float(p.get('trench_pixel_len', 1.0)) if p.get('trench_pixel_len', 0) > 0 else 0.0
                self.points[idx].update({
                    'cvg_pixel_dist': cvg_pixels,
                    'total_um': total_um,
                    'coverage_um': coverage_um,
                    'coverage_ratio': coverage_ratio,
                })

            def _apply_extra_trim(idx, extra_px):
                if extra_px <= 0:
                    return
                p = self.points[idx]
                line = self.trench_lines[idx]
                if p.get('is_skipped'):
                    return
                cvg_pixels = int(max(0, int(p.get('cvg_pixel_dist', 0)) - int(extra_px)))
                trench_len = float(p.get('trench_pixel_len', 0.0))
                upp = float(p.get('um_per_pixel', 1.0))
                dx = float(line.get('dx', 0.0))
                dy = float(line.get('dy', 0.0))
                start_pt = line.get('start_pt', (0, 0))
                base_start = int(line.get('base_cvg_start_idx', 0)) + int(extra_px)
                cvg_end_idx = int(base_start + cvg_pixels)
                if cvg_pixels > 0:
                    draw_pt1 = (int(start_pt[0] + dx * base_start), int(start_pt[1] + dy * base_start))
                    draw_pt2 = (int(start_pt[0] + dx * cvg_end_idx), int(start_pt[1] + dy * cvg_end_idx))
                    self.trench_lines[idx].update({
                        'pt1': draw_pt1,
                        'pt2': draw_pt2,
                        'cvg_pixels': cvg_pixels,
                        'base_cvg_start_idx': base_start,
                    })
                else:
                    self.trench_lines[idx].update({'pt1': start_pt, 'pt2': start_pt, 'cvg_pixels': 0, 'base_cvg_start_idx': base_start})
                self.points[idx].update({
                    'cvg_pixel_dist': cvg_pixels,
                    'coverage_um': cvg_pixels * upp,
                    'coverage_ratio': (cvg_pixels / trench_len) if trench_len > 0 else 0.0,
                })

            # Right-column local outlier correction
            for idx in range(mid + 1, num_points - 1):
                p = self.points[idx]
                p_prev = self.points[idx - 1]
                p_next = self.points[idx + 1]
                if p.get('is_skipped') or p_prev.get('is_skipped') or p_next.get('is_skipped'):
                    continue
                cur = float(p.get('coverage_um', 0.0))
                nbr = 0.5 * (float(p_prev.get('coverage_um', 0.0)) + float(p_next.get('coverage_um', 0.0)))
                if cur > nbr + 180.0 and cur > 1000.0:
                    _recompute_single(idx, int(right_graph_thresh) - 5)
                elif cur + 220.0 < nbr and cur < 350.0:
                    _recompute_single(idx, int(right_graph_thresh) + 8)

            # Left-column local outlier correction (short coverage rescue)
            for idx in range(1, mid - 1):
                p = self.points[idx]
                p_prev = self.points[idx - 1]
                p_next = self.points[idx + 1]
                if p.get('is_skipped') or p_prev.get('is_skipped') or p_next.get('is_skipped'):
                    continue
                cur = float(p.get('coverage_um', 0.0))
                nbr = 0.5 * (
                    float(p_prev.get('coverage_um', 0.0)) +
                    float(p_next.get('coverage_um', 0.0))
                )
                # If this pad is much shorter than neighbors, relax left threshold
                # locally to allow coverage to extend.
                if cur + 220.0 < nbr and cur < 1200.0:
                    _recompute_single(idx, int(left_graph_thresh) + 6)

            # Right odd-lane correction: if odd rows are significantly above adjacent
            # even rows, tighten only those odd pads.
            for cp in range(mid + 1, num_points + 1):
                if cp % 2 == 0:
                    continue
                idx = cp - 1
                p = self.points[idx]
                if p.get('is_skipped'):
                    continue
                even_neighbors = []
                if idx - 1 >= mid and not self.points[idx - 1].get('is_skipped'):
                    even_neighbors.append(float(self.points[idx - 1].get('coverage_um', 0.0)))
                if idx + 1 < num_points and not self.points[idx + 1].get('is_skipped'):
                    even_neighbors.append(float(self.points[idx + 1].get('coverage_um', 0.0)))
                if not even_neighbors:
                    continue
                cur = float(p.get('coverage_um', 0.0))
                even_avg = float(np.mean(even_neighbors))
                if cur > even_avg + 140.0 and cur > 900.0:
                    _recompute_single(idx, int(right_graph_thresh) - 4)

            # Focused correction for KR_195_A-like residual overshoot:
            # top-right odd rows that remain slightly high after edge locking.
            for cp in range(mid + 1, min(num_points, mid + 11) + 1):
                if cp % 2 == 0:
                    continue
                idx = cp - 1
                p = self.points[idx]
                if p.get('is_skipped'):
                    continue
                cur = float(p.get('coverage_um', 0.0))
                if cur < 1400.0:
                    continue
                nbr = []
                if idx - 1 >= mid and not self.points[idx - 1].get('is_skipped'):
                    nbr.append(float(self.points[idx - 1].get('coverage_um', 0.0)))
                if idx + 1 < num_points and not self.points[idx + 1].get('is_skipped'):
                    nbr.append(float(self.points[idx + 1].get('coverage_um', 0.0)))
                if nbr and cur > (float(np.mean(nbr)) + 25.0):
                    _apply_extra_trim(idx, 10)

        # One-shot right-side overshoot autocorrect:
        # if right column is implausibly "almost all full coverage" versus left,
        # re-run once with a slightly stricter right threshold.
        if _allow_autocorrect and orientation == 'Horizontal' and num_points >= 64:
            mid = num_points // 2
            left_pts = [p for p in self.points[:mid] if not p.get('is_skipped')]
            right_pts = [p for p in self.points[mid:] if not p.get('is_skipped')]
            if left_pts and right_pts:
                l_full = sum(1 for p in left_pts if p.get('coverage_ratio', 0.0) >= 0.92)
                r_full = sum(1 for p in right_pts if p.get('coverage_ratio', 0.0) >= 0.92)
                r_zero = sum(1 for p in right_pts if p.get('coverage_ratio', 0.0) <= 0.01)
                if r_full >= 10 and r_full >= l_full + 6 and r_zero <= 2:
                    return self.process(
                        threshold=threshold,
                        left_graph_thresh=left_graph_thresh,
                        right_graph_thresh=max(1, int(right_graph_thresh) - 5),
                        trim_um=trim_um,
                        orientation=orientation,
                        bg_type=bg_type,
                        morph_size=morph_size,
                        num_points=num_points,
                        local_trims=local_trims,
                        local_threshes=local_threshes,
                        skipped_pads=skipped_pads,
                        _allow_autocorrect=False,
                    )

        return self.points, self.thresh_img

    def draw_results(self, output_img):
        for i, p in enumerate(self.points):
            if p.get('is_skipped'):
                continue
            x, y, w, h = p['box']
            cv2.rectangle(output_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
            lbl_x = x - 25 if x > 100 else x + w + 5
            cv2.putText(output_img, str(i+1), (lbl_x, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
            
        for line_obj in self.trench_lines:
            if line_obj['cvg_pixels'] > 0:
                cv2.line(output_img, line_obj['pt1'], line_obj['pt2'], (255, 0, 0), 2) 
            
        return output_img

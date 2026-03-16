#!/usr/bin/env python3
"""
HADO WORLD Match Detector - detects stats screens via left-right color split,
and WIN screens via center-ROI color dominance.
Optimized: uses OpenCV for direct video reading (no PNG file I/O).
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile

import cv2
import numpy as np

from extractor import BaseMatchExtractor

logger = logging.getLogger("hadoworld")


def _ts(seconds):
    """Format seconds as MM:SS.s for log output."""
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:04.1f}"


class HadoWorldMatchExtractor(BaseMatchExtractor):
    score_buffer = 8  # WIN表示から8秒後にクリップ終了
    detection_label = "win detected"

    def __init__(self, video_path, output_dir=".", temp_dir=None,
                 progress_callback=None):
        if temp_dir is None:
            temp_dir = os.path.join(tempfile.gettempdir(), "hado_extraction")
        super().__init__(video_path, output_dir, temp_dir, progress_callback)
        self.match_duration = 160
        self.match_buffer = 10

    def _setup_logging(self):
        """Configure file logging to output_dir/debug.log."""
        if logger.handlers:
            return
        logger.setLevel(logging.DEBUG)
        log_path = self.output_dir / "debug.log"
        fh = logging.FileHandler(str(log_path), mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s",
                                          datefmt="%H:%M:%S"))
        logger.addHandler(fh)
        logger.info("=== HADO WORLD Detector started ===")
        logger.info("video: %s", self.video_path)

    def _is_win_screen(self, frame, timestamp=None):
        """Detect WIN screen by color dominance in center ROI.

        WIN screen: one color (red or blue) > 10% AND the other < 5%.
        Stats screen: both colors > 10% → excluded.
        Gameplay: both colors < 7% → excluded.
        Returns (is_win, red_pct, blue_pct) tuple.
        """
        h, w = frame.shape[:2]

        # Center ROI where WIN text appears (y: 25-70%, x: 10-90%)
        roi = frame[int(h * 0.25):int(h * 0.70), int(w * 0.10):int(w * 0.90)]
        total_px = roi.shape[0] * roi.shape[1]

        # OpenCV is BGR
        b_ch, g_ch, r_ch = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]

        # RED WIN text: R>150, R>G+40, R>B+60
        red_px = np.sum((r_ch.astype(np.int16) > 150) &
                        (r_ch.astype(np.int16) > g_ch.astype(np.int16) + 40) &
                        (r_ch.astype(np.int16) > b_ch.astype(np.int16) + 60))
        red_pct = red_px / total_px * 100

        # BLUE WIN text: B>150, B>R+40, G>100
        blue_px = np.sum((b_ch.astype(np.int16) > 150) &
                         (b_ch.astype(np.int16) > r_ch.astype(np.int16) + 40) &
                         (g_ch > 100))
        blue_pct = blue_px / total_px * 100

        is_win = False
        # RED WIN: red dominant, blue absent
        if red_pct > 10 and blue_pct < 5:
            is_win = True
        # BLUE WIN: blue dominant, red absent
        elif blue_pct > 10 and red_pct < 5:
            is_win = True

        return is_win, red_pct, blue_pct

    def detect_stats_screens(self, _frame_count=None):
        """Detect stats screens using left-right color split.

        Stats screen has left=RED team (warm colors), right=BLUE team (cool colors).
        This pattern distinguishes stats from gameplay where colors are scattered.

        Uses adaptive threshold: tries [20, 15, 12, 10, 8] and picks the first
        threshold that yields 2+ segments (to avoid single-frame outliers).
        _frame_count is unused (kept for API compatibility with base class).
        """
        self._report("スタッツ画面検出", "スタッツ画面を検出中...", 8)

        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise RuntimeError(f"動画を開けません: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps * 4))  # 4秒間隔
        total_samples = total_frames // sample_interval

        logger.info("--- detect_stats_screens ---")
        logger.info("fps=%.1f total_frames=%d sample_interval=%d (~%.1fs)",
                     fps, total_frames, sample_interval, sample_interval / fps)

        # Collect all frame data first
        all_frames = []
        frame_idx = 0
        sample_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            sample_count += 1

            # 1/8サイズにリサイズ（ピクセル数1/64で高速化、色割合は統計的に同一）
            small = cv2.resize(frame, (frame.shape[1] // 8, frame.shape[0] // 8))
            h, w = small.shape[:2]
            half_w = w // 2

            # OpenCV is BGR
            b, g, r = small[:, :, 0], small[:, :, 1], small[:, :, 2]

            # Left half: warm/red pixels (R>150, R>G+20, B<150)
            left_r = r[:, :half_w]
            left_g = g[:, :half_w]
            left_b = b[:, :half_w]
            left_warm = np.sum((left_r > 150) & (left_r > left_g + 20) & (left_b < 150))
            left_total = h * half_w
            left_pct = left_warm / left_total * 100

            # Right half: cool/blue pixels (B>130, B>R+20)
            right_r = r[:, half_w:]
            right_b = b[:, half_w:]
            right_blue = np.sum((right_b > 130) & (right_b > right_r + 20))
            right_total = h * (w - half_w)
            right_pct = right_blue / right_total * 100

            # Combined percentage (for adaptive threshold)
            combined_pct = left_pct + right_pct

            timestamp = frame_idx / fps

            # Both sides must have >= 15% color presence (real stats: 23%+)
            if left_pct >= 15 and right_pct >= 15:
                all_frames.append((timestamp, combined_pct))
                logger.debug("  %s left_warm=%.1f%% right_blue=%.1f%% combined=%.1f%% → HIT",
                             _ts(timestamp), left_pct, right_pct, combined_pct)
            elif left_pct >= 1 or right_pct >= 1:
                logger.debug("  %s left_warm=%.1f%% right_blue=%.1f%% → skip (below 15%%)",
                             _ts(timestamp), left_pct, right_pct)

            if sample_count % 10 == 0 or frame_idx + sample_interval >= total_frames:
                pct = 8 + (frame_idx / total_frames) * 30
                self._report(
                    "スタッツ画面検出",
                    f"フレーム {sample_count}/{total_samples} をスキャン中",
                    round(pct, 1)
                )

            frame_idx += 1

        cap.release()

        logger.info("scan done: %d candidate frames from %d samples", len(all_frames), sample_count)

        # Adaptive threshold: pick first threshold that yields 2+ segments
        thresholds = [20, 15, 12, 10, 8]
        stats_frames = []

        for threshold in thresholds:
            candidates = [(ts, pct) for ts, pct in all_frames if pct > threshold]

            if not candidates:
                logger.info("  threshold %d%%: 0 candidates", threshold)
                continue

            # Group candidates into segments to count them
            segment_count = 1
            prev_ts = candidates[0][0]
            for ts, _pct in candidates[1:]:
                if ts > prev_ts + self.gap_tolerance:
                    segment_count += 1
                prev_ts = ts

            logger.info("  threshold %d%%: %d candidates → %d segments",
                         threshold, len(candidates), segment_count)

            # Accept if 2+ segments, or if at lowest threshold accept any result
            if segment_count >= 2 or threshold == thresholds[-1]:
                stats_frames = candidates
                self._report(
                    "スタッツ画面検出",
                    f"閾値{threshold}%で {len(stats_frames)}個検出 "
                    f"({segment_count}セグメント)",
                    38
                )
                logger.info("  → ACCEPTED threshold=%d%%", threshold)
                break

        if not stats_frames:
            self._report("スタッツ画面検出", "スタッツフレーム 0個 検出完了", 38)
            logger.warning("no stats frames detected at any threshold")

        return stats_frames

    def detect_score_display(self, _frame_count, stats_start,
                             max_search_duration=150, next_stats_start=None):
        """Detect WIN screen by full-range scan + pick latest candidate.

        Scans the entire search range and collects all frame data, then
        selects the LATEST WIN candidate (excluding the 30s zone before
        next stats screen where pre-stats animations appear).

        Two-pass selection:
        1. Strong match: one color > 10%, other < 5% → pick latest
        2. Peak detection: one color > 5.5%, other < 2% → pick latest

        Uses per-sample seeking (cap.set for each timestamp) to avoid
        frame-position drift that occurs with sequential reading after a seek.
        """
        search_start_time = stats_start + 60  # 試合開始60秒後から検索

        if next_stats_start is not None:
            search_duration = min(max_search_duration,
                                  next_stats_start - search_start_time)
        else:
            search_duration = max_search_duration

        logger.info("  WIN search: %s → %s (%.0fs)",
                     _ts(search_start_time),
                     _ts(search_start_time + search_duration),
                     search_duration)

        if search_duration <= 0:
            logger.info("  WIN search: skipped (duration<=0)")
            return None

        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            return None

        scan_data = []  # (actual_ts, red_pct, blue_pct)

        # Full-range scan at 0.5s intervals (2fps)
        t = search_start_time
        while t <= search_start_time + search_duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if not ret:
                t += 0.5
                continue

            actual_ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000

            # 1/4サイズにリサイズ（高速化しつつ色割合の精度を維持）
            small = cv2.resize(frame, (frame.shape[1] // 4, frame.shape[0] // 4))
            is_win, red_pct, blue_pct = self._is_win_screen(small, actual_ts)

            scan_data.append((actual_ts, red_pct, blue_pct))

            if red_pct > 3 or blue_pct > 3:
                logger.debug("    %s red=%.1f%% blue=%.1f%%%s",
                             _ts(actual_ts), red_pct, blue_pct,
                             " ★WIN" if is_win else "")

            t += 0.5

        cap.release()

        # Exclusion zone: 30s before next stats (pre-stats animations)
        if next_stats_start is not None:
            exclusion_start = next_stats_start - 30
            logger.debug("  exclusion zone: %s onwards (next_stats=%s)",
                         _ts(exclusion_start), _ts(next_stats_start))
        else:
            exclusion_start = float('inf')

        # Valid candidates: within zone AND not stats screen (both >10%)
        valid = [(ts, r, b) for ts, r, b in scan_data
                 if ts < exclusion_start and not (r > 10 and b > 10)]

        # Pass 1: strong match (>10% dominant, <5% other) → pick latest
        strong = [(ts, r, b) for ts, r, b in valid
                  if (r > 10 and b < 5) or (b > 10 and r < 5)]

        result = None
        if strong:
            ts, r, b = strong[-1]  # latest candidate
            result = ts
            label = "RED" if r > b else "BLUE"
            logger.info("  WIN FOUND: %s %s WIN (red=%.1f%% blue=%.1f%%) "
                         "[%d candidates, picked latest]",
                         _ts(ts), label, r, b, len(strong))

        # Pass 2: peak detection (>5.5% dominant, <2% other) → pick latest
        if result is None:
            peaks = [(ts, r, b) for ts, r, b in valid
                     if (r > 5.5 and b < 2) or (b > 5.5 and r < 2)]
            if peaks:
                ts, r, b = peaks[-1]  # latest candidate
                result = ts
                label = "RED" if r > b else "BLUE"
                logger.info("  WIN PEAK: %s %s WIN (red=%.1f%% blue=%.1f%%) "
                             "[%d peaks, picked latest]",
                             _ts(ts), label, r, b, len(peaks))

        if result is None:
            logger.info("  WIN not found (%d frames scanned)", len(scan_data))

        return result

    def calculate_clip_ranges(self, stats_screens, frame_count, video_duration):
        """Calculate clip ranges: WIN detection with stats-to-stats fallback.

        Primary: detect WIN screen → clip_end = win_time + 8s.
        Fallback: stats-to-stats boundary or match_duration.
        Segments shorter than 80 seconds are filtered out.
        """
        raw_clips = []
        win_count = 0

        logger.info("--- calculate_clip_ranges: %d segments ---", len(stats_screens))
        self._report("WIN検出", "WIN画面を検出中...", 40)

        for i, (ss_start, ss_end) in enumerate(stats_screens):
            clip_start = ss_start
            next_start = stats_screens[i + 1][0] if i + 1 < len(stats_screens) else None

            logger.info("match %d/%d: stats=%s next_stats=%s",
                         i + 1, len(stats_screens), _ts(ss_start),
                         _ts(next_start) if next_start else "None")

            # Try WIN detection
            win_time = self.detect_score_display(
                0, ss_start, next_stats_start=next_start)

            if win_time:
                clip_end = win_time + self.score_buffer
                method = "win detected"
                win_count += 1
            elif next_start:
                clip_end = next_start - 5
                method = "stats boundary"
            else:
                clip_end = min(clip_start + self.match_duration, video_duration)
                method = "fallback"

            duration = clip_end - clip_start

            logger.info("  → %s-%s (%.0fs) [%s]",
                         _ts(clip_start), _ts(clip_end), duration, method)

            raw_clips.append({
                "start": clip_start,
                "end": clip_end,
                "duration": duration,
                "detection_method": method,
            })

            pct = 40 + ((i + 1) / len(stats_screens)) * 20
            self._report(
                "WIN検出",
                f"試合{i + 1}/{len(stats_screens)} [{method}]",
                round(pct, 1)
            )

        # Filter out segments shorter than 80 seconds (real matches are 80s+)
        clips = []
        for clip in raw_clips:
            if clip["duration"] < 80:
                logger.warning("SHORT CLIP: %s-%s (%.0fs < 80s) — 異常な短さ",
                               _ts(clip["start"]), _ts(clip["end"]), clip["duration"])
                continue
            clip["match"] = len(clips) + 1
            clips.append(clip)

        for clip in clips:
            ms, ss = divmod(clip["start"], 60)
            me, se = divmod(clip["end"], 60)
            self._report(
                "WIN検出",
                f"試合{clip['match']}/{len(clips)}: "
                f"{int(ms):02d}:{int(ss):02d}-{int(me):02d}:{int(se):02d} "
                f"[{clip['detection_method']}]",
                60
            )

        total = sum(c['duration'] for c in clips)
        logger.info("=== result: %d clips, win=%d, total=%.0fs ===",
                     len(clips), win_count, total)
        self._report(
            "WIN検出",
            f"{len(clips)}試合検出 (WIN検出: {win_count}, 合計{total:.0f}秒)",
            60
        )

        return clips

    def run(self, cleanup=True, preset="ultrafast"):
        """Run the full extraction pipeline.

        Overrides base class to skip extract_frames() — uses OpenCV direct
        video reading instead of PNG file I/O for major speedup.
        """
        if not shutil.which("ffprobe"):
            if sys.platform == 'darwin':
                install_hint = "  brew install ffmpeg"
            else:
                install_hint = "  https://ffmpeg.org/download.html からダウンロードしてPATHに追加してください"
            raise RuntimeError(
                "ffprobe が見つかりません。\n"
                "以下の方法でインストールしてください:\n"
                f"{install_hint}"
            )

        self.setup_directories()
        self._setup_logging()

        # Get video duration via ffprobe (no frame extraction needed)
        self._report("動画情報取得", "動画情報を取得中...", 0)
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.video_path)
        ]
        duration = float(subprocess.check_output(cmd).decode().strip())
        logger.info("video duration: %.0fs", duration)
        self._report("動画情報取得", f"動画長: {duration:.0f}秒", 8)

        # Detect stats screens (OpenCV direct reading, no PNG files)
        stats_frames = self.detect_stats_screens()

        if not stats_frames:
            self._report("エラー", "スタッツ画面が検出されませんでした", 100)
            if cleanup:
                self.cleanup()
            return None

        # Group into segments (base class method)
        stats_screens = self.group_stats_screens(stats_frames)

        logger.info("--- grouped segments ---")
        for i, (s, e) in enumerate(stats_screens):
            logger.info("  seg %d: %s - %s", i + 1, _ts(s), _ts(e))

        # Calculate clip ranges with WIN detection
        clips = self.calculate_clip_ranges(stats_screens, 0, duration)

        # Save clip data
        clips_file = self.output_dir / "clips_data.json"
        with open(clips_file, 'w') as f:
            json.dump(clips, f, indent=2)

        # Extract clips (base class method, always merges)
        self.extract_clips(clips, preset=preset)

        # Cleanup
        if cleanup:
            self.cleanup()

        return clips

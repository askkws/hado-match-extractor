#!/usr/bin/env python3
"""
HADO Match Detector - detects stats screens (red+orange+cyan) and score displays.
Optimized: uses OpenCV for direct video reading (no PNG file I/O).
"""

import json
import shutil
import subprocess

import cv2
import numpy as np

from extractor import BaseMatchExtractor


class HadoMatchExtractor(BaseMatchExtractor):
    score_buffer = 2.5
    detection_label = "score detected"

    def __init__(self, video_path, output_dir=".", temp_dir="/tmp/hado_extraction",
                 progress_callback=None):
        super().__init__(video_path, output_dir, temp_dir, progress_callback)

        # Detection thresholds
        self.red_threshold = (150, 120, 120)
        self.orange_threshold = (180, 100, 180, 100)
        self.cyan_threshold = (120, 150, 150)
        self.combined_threshold = 15.0

    def detect_stats_screens(self, _frame_count=None):
        """Detect stats screens by red + orange + cyan > 15%.

        Uses OpenCV to read frames directly from video at 4-second intervals.
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

        stats_frames = []
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
            total = small.shape[0] * small.shape[1]

            # OpenCV is BGR
            b, g, r = small[:, :, 0], small[:, :, 1], small[:, :, 2]

            # Red: R>150, G<120, B<120
            red = np.sum((r > self.red_threshold[0]) &
                         (g < self.red_threshold[1]) &
                         (b < self.red_threshold[2]))

            # Orange: R>180, 100<G<180, B<100
            orange = np.sum((r > self.orange_threshold[0]) &
                            (g > self.orange_threshold[1]) &
                            (g < self.orange_threshold[2]) &
                            (b < self.orange_threshold[3]))

            # Cyan: R<120, G>150, B>150
            cyan = np.sum((r < self.cyan_threshold[0]) &
                          (g > self.cyan_threshold[1]) &
                          (b > self.cyan_threshold[2]))

            combined_pct = (red + orange + cyan) / total * 100
            timestamp = frame_idx / fps

            if combined_pct > self.combined_threshold:
                stats_frames.append((timestamp, combined_pct))

            if sample_count % 10 == 0 or frame_idx + sample_interval >= total_frames:
                pct = 8 + (frame_idx / total_frames) * 30
                self._report(
                    "スタッツ画面検出",
                    f"フレーム {sample_count}/{total_samples} をスキャン中",
                    round(pct, 1)
                )

            frame_idx += 1

        cap.release()

        self._report("スタッツ画面検出",
                     f"スタッツフレーム {len(stats_frames)}個 検出完了", 38)

        return stats_frames

    def detect_score_display(self, _frame_count, stats_start,
                             max_search_duration=150, next_stats_start=None):
        """Detect score display: left-half red > 10% AND right-half blue > 10%, diff < 6%.

        Uses OpenCV to seek directly into the video (no PNG file I/O).
        _frame_count is unused (kept for API compatibility with base class).
        """
        search_start_time = stats_start + 80  # 元: frame_index = stats_start//2 + 40 → 40*2=80秒

        # 検索窓を次の試合のstats_startで打ち切る
        if next_stats_start is not None:
            search_duration = min(max_search_duration,
                                  next_stats_start - search_start_time)
        else:
            search_duration = max_search_duration

        if search_duration <= 0:
            return None

        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        # 2秒間隔（元の0.5fpsフレームと同一間隔）
        frame_interval = max(1, int(fps * 2))

        # シーク位置を設定
        cap.set(cv2.CAP_PROP_POS_MSEC, search_start_time * 1000)

        current_frame = 0
        result = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % frame_interval != 0:
                current_frame += 1
                continue

            timestamp = search_start_time + (current_frame / fps)
            if timestamp > search_start_time + search_duration:
                break

            # 1/8サイズにリサイズ
            small = cv2.resize(frame, (frame.shape[1] // 8, frame.shape[0] // 8))
            h, w = small.shape[:2]

            # OpenCV is BGR — convert to RGB-like channel access
            b_ch, g_ch, r_ch = small[:, :, 0], small[:, :, 1], small[:, :, 2]

            left_r = r_ch[:, :w // 2]
            left_g = g_ch[:, :w // 2]
            left_b = b_ch[:, :w // 2]

            right_r = r_ch[:, w // 2:]
            right_g = g_ch[:, w // 2:]
            right_b = b_ch[:, w // 2:]

            # Left half: red (r>120, r>g+30) > 10%
            left_red = np.sum((left_r > 120) & (left_r > left_g + 30))
            left_total = left_r.shape[0] * left_r.shape[1]
            left_red_pct = left_red / left_total * 100

            # Right half: blue (b>120, b>r+30) > 10%
            right_blue = np.sum((right_b > 120) & (right_b > right_r + 30))
            right_total = right_r.shape[0] * right_r.shape[1]
            right_blue_pct = right_blue / right_total * 100

            is_score = (left_red_pct > 10 and right_blue_pct > 10 and
                        abs(left_red_pct - right_blue_pct) < 6)

            if is_score:
                result = timestamp
                break

            current_frame += 1

        cap.release()
        return result

    def run(self, cleanup=True, preset="ultrafast"):
        """Run the full extraction pipeline.

        Overrides base class to skip extract_frames() — uses OpenCV direct
        video reading instead of PNG file I/O for major speedup.
        """
        if not shutil.which("ffprobe"):
            raise RuntimeError(
                "ffprobe が見つかりません。\n"
                "ターミナルで以下を実行してインストールしてください:\n"
                "  brew install ffmpeg"
            )

        self.setup_directories()

        # Get video duration via ffprobe (no frame extraction needed)
        self._report("動画情報取得", "動画情報を取得中...", 0)
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.video_path)
        ]
        duration = float(subprocess.check_output(cmd).decode().strip())
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

        # Calculate clip ranges — frame_count=0 (unused by our overridden methods)
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

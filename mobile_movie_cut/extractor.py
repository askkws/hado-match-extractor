#!/usr/bin/env python3
"""
Base Match Extractor - common processing pipeline for all game types.
Subclasses implement detect_stats_screens() and detect_score_display().
"""

import json
import shutil
import subprocess
from pathlib import Path


class BaseMatchExtractor:
    # Subclasses override these
    score_buffer = 2.5
    detection_label = "score detected"

    def __init__(self, video_path, output_dir=".", temp_dir="/tmp/hado_extraction",
                 progress_callback=None):
        self.video_path = Path(video_path)
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.frames_dir = self.temp_dir / "frames"

        # Progress callback: callback(stage, message, pct)
        self.progress_callback = progress_callback or (lambda stage, msg, pct: None)

        # Grouping
        self.gap_tolerance = 6

        # Match timing
        self.match_duration = 120
        self.match_buffer = 5

    def _report(self, stage, message, pct):
        """Report progress via callback."""
        self.progress_callback(stage, message, pct)

    def setup_directories(self):
        """Create necessary directories."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_frames(self, fps=0.5):
        """Extract frames from video for analysis."""
        self._report("フレーム抽出", "フレームを抽出中...", 0)

        # Get video duration
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.video_path)
        ]
        duration = float(subprocess.check_output(cmd).decode().strip())

        self._report("フレーム抽出", f"動画長: {duration:.0f}秒 フレーム抽出中...", 1)

        # Extract frames
        cmd = [
            "ffmpeg", "-y",
            "-i", str(self.video_path),
            "-vf", f"fps={fps}",
            str(self.frames_dir / "f_%05d.png")
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        frame_count = len(list(self.frames_dir.glob("f_*.png")))
        self._report("フレーム抽出", f"{frame_count}フレーム抽出完了 ({duration:.0f}秒)", 8)

        return frame_count, duration

    def detect_stats_screens(self, frame_count):
        """Detect stats screens. Must be implemented by subclass."""
        raise NotImplementedError

    def detect_score_display(self, frame_count, stats_start,
                             max_search_duration=150, next_stats_start=None):
        """Detect score/win display. Must be implemented by subclass."""
        raise NotImplementedError

    def group_stats_screens(self, stats_frames):
        """Group consecutive stats frames into segments."""
        if not stats_frames:
            return []

        self._report("グルーピング", "スタッツ画面をグルーピング中...", 38)

        segments = []
        seg_start = stats_frames[0][0]
        seg_end = stats_frames[0][0]

        for ts, pct in stats_frames[1:]:
            if ts <= seg_end + self.gap_tolerance:
                seg_end = ts
            else:
                segments.append([seg_start, seg_end])
                seg_start = ts
                seg_end = ts

        segments.append([seg_start, seg_end])

        self._report("グルーピング", f"{len(segments)}試合のスタッツ画面を検出", 40)

        return segments

    def calculate_clip_ranges(self, stats_screens, frame_count, video_duration):
        """Calculate clip start/end times for each match by detecting score displays."""
        clips = []

        self._report("スコア表示検出", "スコア表示を検出中...", 40)

        for i, (ss_start, ss_end) in enumerate(stats_screens):
            clip_start = ss_start

            next_start = stats_screens[i + 1][0] if i + 1 < len(stats_screens) else None
            score_time = self.detect_score_display(
                frame_count, ss_start, next_stats_start=next_start)

            if score_time:
                clip_end = score_time + self.score_buffer
                method = self.detection_label
            else:
                if i + 1 < len(stats_screens):
                    next_start = stats_screens[i + 1][0]
                    clip_end = min(clip_start + self.match_duration,
                                  next_start - self.match_buffer)
                else:
                    clip_end = min(clip_start + self.match_duration, video_duration)
                method = "fallback"

            duration = clip_end - clip_start

            clips.append({
                "match": i + 1,
                "start": clip_start,
                "end": clip_end,
                "duration": duration,
                "detection_method": method
            })

            pct = 40 + ((i + 1) / len(stats_screens)) * 20  # 40% to 60%
            ms, ss = divmod(clip_start, 60)
            me, se = divmod(clip_end, 60)
            self._report(
                "スコア表示検出",
                f"試合{i+1}/{len(stats_screens)}: "
                f"{int(ms):02d}:{int(ss):02d}-{int(me):02d}:{int(se):02d} [{method}]",
                round(pct, 1)
            )

        total = sum(c['duration'] for c in clips)
        detected = sum(1 for c in clips if c['detection_method'] == self.detection_label)
        self._report(
            "スコア表示検出",
            f"{len(clips)}試合検出 (スコア検出: {detected}/{len(clips)})",
            60
        )

        return clips

    def extract_clips(self, clips, preset="ultrafast"):
        """Extract individual match clips from video. Always merges."""
        self._report("クリップ抽出", f"{len(clips)}試合のクリップを抽出中...", 60)

        clip_files = []

        for idx, clip in enumerate(clips):
            match_num = clip['match']
            output_file = self.output_dir / f"match_{match_num:02d}.mp4"
            clip_files.append(output_file)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(clip['start']),
                "-t", str(clip['duration']),
                "-i", str(self.video_path),
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", "23",
                "-c:a", "aac",
                str(output_file)
            ]

            pct = 60 + ((idx + 1) / len(clips)) * 30  # 60% to 90%
            self._report(
                "クリップ抽出",
                f"試合{match_num}/{len(clips)} を抽出中...",
                round(pct, 1)
            )

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        self._report("クリップ抽出", "全クリップ抽出完了", 90)

        # Always merge clips
        self.merge_clips(clip_files)

        return clip_files

    def merge_clips(self, clip_files):
        """Merge all clips into a single video."""
        self._report("まとめ動画生成", "全試合をまとめ動画に結合中...", 90)

        concat_list = self.temp_dir / "concat_list.txt"
        with open(concat_list, 'w') as f:
            for clip_file in clip_files:
                f.write(f"file '{clip_file.absolute()}'\n")

        output_file = self.output_dir / "all_matches_combined.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_file)
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        size_mb = output_file.stat().st_size / (1024 ** 2)
        self._report("まとめ動画生成", f"まとめ動画生成完了 ({size_mb:.0f}MB)", 95)

        return output_file

    def cleanup(self):
        """Remove temporary files."""
        self._report("クリーンアップ", "一時ファイルを削除中...", 95)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._report("クリーンアップ", "クリーンアップ完了", 100)

    def run(self, cleanup=True, preset="ultrafast"):
        """Run the full extraction pipeline."""
        if not shutil.which("ffprobe"):
            raise RuntimeError(
                "ffprobe が見つかりません。\n"
                "ターミナルで以下を実行してインストールしてください:\n"
                "  brew install ffmpeg"
            )

        self.setup_directories()

        # Extract frames
        frame_count, duration = self.extract_frames()

        # Detect stats screens
        stats_frames = self.detect_stats_screens(frame_count)

        if not stats_frames:
            self._report("エラー", "スタッツ画面が検出されませんでした", 100)
            if cleanup:
                self.cleanup()
            return None

        # Group into segments
        stats_screens = self.group_stats_screens(stats_frames)

        # Calculate clip ranges
        clips = self.calculate_clip_ranges(stats_screens, frame_count, duration)

        # Save clip data
        clips_file = self.output_dir / "clips_data.json"
        with open(clips_file, 'w') as f:
            json.dump(clips, f, indent=2)

        # Extract clips (always merges)
        self.extract_clips(clips, preset=preset)

        # Cleanup
        if cleanup:
            self.cleanup()

        return clips

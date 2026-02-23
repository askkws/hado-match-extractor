#!/usr/bin/env python3
"""
Hado Match Extractor
Extracts individual match clips from a full tournament video by detecting stats screens.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image
import numpy as np
import argparse
from tqdm import tqdm


class HadoMatchExtractor:
    def __init__(self, video_path, output_dir=".", temp_dir="/tmp/hado_extraction"):
        self.video_path = Path(video_path)
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.frames_dir = self.temp_dir / "frames"
        self.progress_file = self.temp_dir / "progress.json"
        self._start_time = time.time()

        # Detection thresholds
        self.red_threshold = (150, 120, 120)  # R>150, G<120, B<120
        self.orange_threshold = (180, 100, 180, 100)  # R>180, 100<G<180, B<100
        self.cyan_threshold = (120, 150, 150)  # R<120, G>150, B>150
        self.combined_threshold = 15.0  # percentage
        self.gap_tolerance = 6  # seconds

        # Match timing
        self.match_duration = 120  # seconds per match
        self.match_buffer = 5  # seconds before next stats screen

    def _write_progress(self, phase, step, total, message, extra=None):
        """Write progress to JSON file for external monitoring."""
        elapsed = time.time() - self._start_time
        data = {
            "phase": phase,
            "step": step,
            "total": total,
            "percent": round(step / total * 100, 1) if total > 0 else 0,
            "message": message,
            "elapsed_sec": int(elapsed),
            "elapsed": f"{int(elapsed//60)}m{int(elapsed%60)}s",
            "updated_at": time.strftime("%H:%M:%S"),
        }
        if extra:
            data.update(extra)
        with open(self.progress_file, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def setup_directories(self):
        """Create necessary directories."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_frames(self, fps=0.5):
        """Extract frames from video for analysis."""
        # Get video duration
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.video_path)
        ]
        duration = float(subprocess.check_output(cmd).decode().strip())
        total_frames = int(duration * fps)

        print(f"\n[1/4] フレーム抽出中 ({fps}fps, 動画長: {int(duration//60)}m{int(duration%60)}s, 推定フレーム数: {total_frames})")

        # Extract frames with progress monitoring
        cmd = [
            "ffmpeg", "-y",
            "-i", str(self.video_path),
            "-vf", f"fps={fps}",
            str(self.frames_dir / "f_%05d.png")
        ]

        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self._write_progress("frames", 0, total_frames, "フレーム抽出開始")
        with tqdm(total=total_frames, unit="frame", ncols=80, bar_format="{l_bar}{bar}| {n}/{total} [{elapsed}<{remaining}]") as pbar:
            prev_count = 0
            while process.poll() is None:
                current_count = len(list(self.frames_dir.glob("f_*.png")))
                if current_count > prev_count:
                    pbar.update(current_count - prev_count)
                    prev_count = current_count
                    self._write_progress("frames", current_count, total_frames,
                                         f"フレーム抽出中 {current_count}/{total_frames}")
                time.sleep(1)
            # Final update
            current_count = len(list(self.frames_dir.glob("f_*.png")))
            pbar.update(current_count - prev_count)
            self._write_progress("frames", current_count, current_count, "フレーム抽出完了")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

        frame_count = len(list(self.frames_dir.glob("f_*.png")))
        print(f"  完了: {frame_count}フレーム抽出 (動画長: {duration:.0f}s)")

        return frame_count, duration

    def detect_stats_screens(self, frame_count):
        """Detect stats screens by analyzing frame colors."""
        print(f"\n[2/4] スタッツ画面を検出中 ({frame_count}フレーム解析)...")

        stats_frames = []

        self._write_progress("detect", 0, frame_count, "スタッツ画面検出開始")
        with tqdm(total=frame_count, unit="frame", ncols=80,
                  bar_format="{l_bar}{bar}| {n}/{total} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
            for i in range(1, frame_count + 1):
                frame_path = self.frames_dir / f"f_{i:05d}.png"
                if not frame_path.exists():
                    pbar.update(1)
                    continue

                img = Image.open(frame_path)
                # Resize to speed up processing
                img = img.resize((img.width // 4, img.height // 4))
                pixels = list(img.getdata())
                total = len(pixels)

                # Count colored pixels
                red_count = sum(1 for r, g, b in pixels
                              if r > self.red_threshold[0]
                              and g < self.red_threshold[1]
                              and b < self.red_threshold[2])

                orange_count = sum(1 for r, g, b in pixels
                                 if r > self.orange_threshold[0]
                                 and g > self.orange_threshold[1]
                                 and g < self.orange_threshold[2]
                                 and b < self.orange_threshold[3])

                cyan_count = sum(1 for r, g, b in pixels
                               if r < self.cyan_threshold[0]
                               and g > self.cyan_threshold[1]
                               and b > self.cyan_threshold[2])

                combined_pct = (red_count + orange_count + cyan_count) / total * 100
                timestamp = (i - 1) * 2  # 0.5 fps = 2 seconds per frame

                if combined_pct > self.combined_threshold:
                    stats_frames.append((timestamp, combined_pct))
                    pbar.set_postfix({"検出": len(stats_frames)})

                pbar.update(1)
                if i % 100 == 0:
                    self._write_progress("detect", i, frame_count,
                                         f"スタッツ画面検出中 {i}/{frame_count}",
                                         {"matches_found": len(stats_frames)})

        print(f"  完了: スタッツ画面 {len(stats_frames)}件検出")
        return stats_frames

    def detect_score_display(self, frame_count, stats_start, max_search_duration=150):
        """Detect score display screen after a match."""
        import numpy as np

        # Start searching 80 seconds after stats (typical match duration)
        search_start_frame = (stats_start // 2) + 40  # 80 seconds / 2
        search_end_frame = min(search_start_frame + (max_search_duration // 2), frame_count)

        for i in range(int(search_start_frame), int(search_end_frame) + 1):
            frame_path = self.frames_dir / f"f_{i:05d}.png"
            if not frame_path.exists():
                continue

            img = Image.open(frame_path)
            img = img.resize((img.width // 4, img.height // 4))
            pixels = np.array(img)

            h, w = pixels.shape[:2]
            left_half = pixels[:, :w//2]
            right_half = pixels[:, w//2:]

            # Count red in left half (R > 120, R > G + 30)
            left_red = np.sum((left_half[:,:,0] > 120) &
                            (left_half[:,:,0] > left_half[:,:,1] + 30))
            left_red_pct = left_red / (left_half.shape[0] * left_half.shape[1]) * 100

            # Count blue in right half (B > 120, B > R + 30)
            right_blue = np.sum((right_half[:,:,2] > 120) &
                              (right_half[:,:,2] > right_half[:,:,0] + 30))
            right_blue_pct = right_blue / (right_half.shape[0] * right_half.shape[1]) * 100

            # Score display: red on left, blue on right, balanced
            is_score = (left_red_pct > 10 and right_blue_pct > 10 and
                       abs(left_red_pct - right_blue_pct) < 6)

            if is_score:
                timestamp = (i - 1) * 2
                return timestamp

        return None

    def group_stats_screens(self, stats_frames):
        """Group consecutive stats frames into segments."""
        if not stats_frames:
            return []

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

        print(f"\nDetected {len(segments)} stats screen appearances:")
        for i, (s, e) in enumerate(segments):
            ms, ss = divmod(s, 60)
            me, se = divmod(e, 60)
            print(f"  Match {i+1:2d}: Stats at {int(ms):02d}:{int(ss):02d}-{int(me):02d}:{int(se):02d}")

        return segments

    def calculate_clip_ranges(self, stats_screens, frame_count, video_duration):
        """Calculate clip start/end times for each match by detecting score displays."""
        clips = []

        print("\nDetecting score displays for precise clip ranges...")

        for i, (ss_start, ss_end) in enumerate(stats_screens):
            clip_start = ss_start

            # Try to detect score display
            score_time = self.detect_score_display(frame_count, ss_start)

            if score_time:
                # Score display found - add 3 seconds buffer (HADO logo appears after)
                clip_end = score_time + 2.5  # Add 2.5 seconds after score display
                method = "score detected"
            else:
                # Fallback to old method
                if i + 1 < len(stats_screens):
                    next_start = stats_screens[i + 1][0]
                    clip_end = min(clip_start + self.match_duration, next_start - self.match_buffer)
                else:
                    clip_end = min(clip_start + self.match_duration, video_duration)
                method = "fallback"

            duration = clip_end - clip_start
            ms, ss = divmod(clip_start, 60)
            me, se = divmod(clip_end, 60)

            print(f"  Match {i+1:2d}: {int(ms):02d}:{int(ss):02d} - {int(me):02d}:{int(se):02d}  ({duration}s) [{method}]")

            clips.append({
                "match": i + 1,
                "start": clip_start,
                "end": clip_end,
                "duration": duration,
                "detection_method": method
            })

        total = sum(c['duration'] for c in clips)
        detected = sum(1 for c in clips if c['detection_method'] == 'score detected')
        print(f"\nTotal: {len(clips)} clips, {total}s ({total//60}m{total%60}s)")
        print(f"Score displays detected: {detected}/{len(clips)}")

        return clips

    def extract_clips(self, clips, preset="ultrafast", merge=False):
        """Extract individual match clips from video."""
        print(f"\n[4/4] 試合クリップ抽出中 ({len(clips)}試合)...")

        preview_files = []

        self._write_progress("extract", 0, len(clips), "クリップ抽出開始",
                             {"total_matches": len(clips)})
        with tqdm(total=len(clips), unit="試合", ncols=80,
                  bar_format="{l_bar}{bar}| {n}/{total}試合 [{elapsed}<{remaining}]") as pbar:
            for clip in clips:
                match_num = clip['match']
                output_file = self.output_dir / f"match_{match_num:02d}.mp4"
                preview_files.append(output_file)

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

                pbar.set_postfix({"現在": f"Match {match_num:02d}"})
                self._write_progress("extract", match_num - 1, len(clips),
                                     f"Match {match_num:02d} を抽出中",
                                     {"current_match": match_num, "total_matches": len(clips)})
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                pbar.update(1)

        print(f"  完了: 全{len(clips)}試合を抽出")

        if merge:
            self.merge_clips(preview_files)

        return preview_files

    def merge_clips(self, clip_files):
        """Merge all clips into a single video."""
        print("\nMerging all clips into one video...")

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

        print(f"Merged video saved: {output_file}")
        print(f"Size: {output_file.stat().st_size / (1024**3):.1f}GB")

        return output_file

    def cleanup(self):
        """Remove temporary files."""
        print("\nCleaning up temporary files...")
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run(self, cleanup=True, merge=False, preset="ultrafast"):
        """Run the full extraction pipeline."""
        start_time = time.time()
        print(f"\n{'='*50}")
        print(f"HADO Match Extractor 開始")
        print(f"  動画: {self.video_path.name}")
        print(f"  出力: {self.output_dir}")
        print(f"  プリセット: {preset}")
        print(f"{'='*50}")

        self.setup_directories()

        # Extract frames
        frame_count, duration = self.extract_frames()

        # Detect stats screens
        stats_frames = self.detect_stats_screens(frame_count)

        if not stats_frames:
            self._write_progress("error", 0, 1, "ERROR: スタッツ画面が検出されませんでした")
            print("ERROR: スタッツ画面が検出されませんでした")
            return None

        # Group into segments
        stats_screens = self.group_stats_screens(stats_frames)

        # Calculate clip ranges (now detects score displays)
        print(f"\n[3/4] スコア表示を検出中...")
        clips = self.calculate_clip_ranges(stats_screens, frame_count, duration)

        # Save clip data
        clips_file = self.output_dir / "clips_data.json"
        with open(clips_file, 'w') as f:
            json.dump(clips, f, indent=2)

        # Extract clips
        clip_files = self.extract_clips(clips, preset=preset, merge=merge)

        # Cleanup
        if cleanup:
            self.cleanup()

        elapsed = time.time() - start_time
        self._write_progress("done", len(clips), len(clips), "抽出完了",
                             {"total_matches": len(clips), "output_dir": str(self.output_dir)})
        print(f"\n{'='*50}")
        print(f"完了! 処理時間: {int(elapsed//60)}m{int(elapsed%60)}s")
        print(f"抽出試合数: {len(clips)}")
        print(f"出力先: {self.output_dir}")
        print(f"{'='*50}")

        return clips


def main():
    parser = argparse.ArgumentParser(description="Extract Hado match clips from tournament video")
    parser.add_argument("video", help="Input video file path")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current)")
    parser.add_argument("-t", "--temp", default="/tmp/hado_extraction", help="Temporary directory")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep temporary files")
    parser.add_argument("--merge", action="store_true", help="Merge all clips into one video")
    parser.add_argument("--preset", default="ultrafast", choices=["ultrafast", "fast", "medium", "slow"],
                       help="FFmpeg encoding preset (default: ultrafast)")

    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"ERROR: Video file not found: {args.video}")
        sys.exit(1)

    extractor = HadoMatchExtractor(
        video_path=args.video,
        output_dir=args.output,
        temp_dir=args.temp
    )

    clips = extractor.run(
        cleanup=not args.no_cleanup,
        merge=args.merge,
        preset=args.preset
    )

    if clips:
        print("\n" + "="*50)
        print("EXTRACTION COMPLETE!")
        print(f"Extracted {len(clips)} match clips")
        print(f"Output directory: {args.output}")
        print("="*50)


if __name__ == "__main__":
    main()

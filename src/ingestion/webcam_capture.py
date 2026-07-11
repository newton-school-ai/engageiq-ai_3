"""Webcam capture pipeline supporting webcam, file, and RTSP inputs."""

import argparse
import logging
import sys
import time

import cv2

from src.pipeline.capture import TimestampedFrame, WebcamCapture

__all__ = ["WebcamCapture", "TimestampedFrame"]

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Webcam Capture Ingestion CLI")
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Webcam index (int) or video file path (str)",
    )
    parser.add_argument("--fps", type=int, default=15, help="Target FPS")
    parser.add_argument(
        "--duration", type=float, default=10.0, help="Duration to run in seconds"
    )
    args = parser.parse_args()

    # Determine if source is 'webcam' or digit or file path
    source_val = args.source
    if source_val == "webcam":
        source_val = 0
    elif source_val.isdigit():
        source_val = int(source_val)

    try:
        cap = WebcamCapture(source=source_val, fps=args.fps)
    except Exception as e:
        print(f"Error initializing WebcamCapture: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"WebcamCapture Ingestion started. Source: {source_val}, Target FPS: {args.fps}, Duration: {args.duration}s"
    )
    frames_count = 0
    start_time = None

    try:
        for frame in cap.stream(duration=args.duration):
            if start_time is None:
                start_time = time.time()
            frames_count += 1
            # Try to show a window (handle environments without GUI gracefully)
            try:
                cv2.imshow("Webcam Ingestion Stream", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            except Exception:
                pass
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        cap.release()

    if start_time is not None:
        elapsed = time.time() - start_time
        actual_fps = frames_count / elapsed if elapsed > 0 else 0.0
        print(f"Captured {frames_count} frames in {elapsed:.2f} seconds.")
        print(f"Actual FPS: {actual_fps:.2f} (Target: {args.fps})")
    else:
        print("No frames were captured.")

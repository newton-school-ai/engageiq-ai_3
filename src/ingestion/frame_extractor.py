"""Frame preprocessing: face crop, resize, normalize, FPS control."""

import argparse
import logging
import sys

import cv2

from src.pipeline.capture import WebcamCapture
from src.pipeline.preprocessor import FramePreprocessor

# Alias FramePreprocessor as FrameExtractor for backward compatibility
FrameExtractor = FramePreprocessor

__all__ = ["FramePreprocessor", "FrameExtractor"]

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Frame Extractor Ingestion CLI")
    parser.add_argument(
        "--input",
        type=str,
        default="0",
        help="Webcam index (int) or video file path (str)",
    )
    parser.add_argument("--output-fps", type=int, default=10, help="Target output FPS")
    args = parser.parse_args()

    source_val = args.input
    if source_val.isdigit():
        source_val = int(source_val)

    try:
        cap = WebcamCapture(source=source_val, fps=args.output_fps)
        extractor = FramePreprocessor()
    except Exception as e:
        print(f"Error initializing frame extractor: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"FrameExtractor Ingestion CLI started. Input: {source_val}, Output FPS: {args.output_fps}"
    )
    try:
        for frame in cap.stream():
            processed = extractor.process(frame)
            # Display processed frame. Note that cv2.imshow expects BGR, but processed is RGB and float32 normalized.
            # So to display it correctly, convert back to BGR and scale to uint8 range.
            display_frame = cv2.cvtColor(
                (processed * 255.0).astype("uint8"), cv2.COLOR_RGB2BGR
            )
            try:
                cv2.imshow("Preprocessed Stream", display_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            except Exception:
                pass
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        cap.release()

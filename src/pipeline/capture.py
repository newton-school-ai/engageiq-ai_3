"""Webcam and video capture module with FPS regulation and timestamp metadata."""

import argparse
import logging
import sys
import time
from typing import Generator, List, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class TimestampedFrame(np.ndarray):
    """
    A numpy array subclass that carries a timestamp attribute.
    This preserves full compatibility with OpenCV/MediaPipe operations
    while carrying acquisition or processing timestamps.
    """

    def __new__(cls, input_array, timestamp: Optional[float] = None):
        obj = np.asarray(input_array).view(cls)
        obj.timestamp = timestamp if timestamp is not None else time.time()
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.timestamp = getattr(obj, "timestamp", None)


class WebcamCapture:
    """
    WebcamCapture captures frames from a local webcam or video file.
    It regulates frame retrieval speed to maintain a target FPS.
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        fps: int = 15,
        resolution: Tuple[int, int] = (640, 480),
    ):
        """
        Initialize WebcamCapture.

        Args:
            source: Webcam device index (int) or path to pre-recorded video (str).
            fps: Target frames per second to capture.
            resolution: Requested camera resolution as (width, height).
        """
        self.source = source
        self.fps = fps
        self.resolution = resolution
        self.frame_delay = 1.0 / fps if fps > 0 else 0.0
        self.last_frame_time = 0.0

        # Handle string representing an integer (e.g. CLI arguments)
        parsed_source = source
        if isinstance(source, str) and source.isdigit():
            parsed_source = int(source)

        logger.info(f"Opening video source: {parsed_source}")
        self.cap = cv2.VideoCapture(parsed_source)
        if not self.cap.isOpened():
            error_msg = f"Failed to open video source: {source}"
            logger.error(error_msg)
            self.release()
            raise RuntimeError(error_msg)

        # Apply settings if it's an integer webcam source
        if isinstance(parsed_source, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"Configured webcam source {source} to {actual_w}x{actual_h}")
        else:
            logger.info(f"Opened video file: {source}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def read(self) -> Tuple[bool, Optional[TimestampedFrame], float]:
        """
        Read a single frame, regulating the execution rate to match the target FPS.

        Returns:
            A tuple of (success, frame, timestamp).
        """
        if self.cap is None or not self.cap.isOpened():
            return False, None, 0.0

        # Regulate FPS by sleeping if reading too fast
        if self.frame_delay > 0 and self.last_frame_time > 0:
            elapsed = time.time() - self.last_frame_time
            sleep_time = self.frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        success, frame = self.cap.read()
        timestamp = time.time()

        if not success or frame is None:
            return False, None, timestamp

        self.last_frame_time = timestamp
        timestamped = TimestampedFrame(frame, timestamp=timestamp)
        return True, timestamped, timestamp

    def capture_one(self) -> Optional[TimestampedFrame]:
        """
        Capture and return a single frame.

        Returns:
            The captured frame, or None if reading failed.
        """
        success, frame, _ = self.read()
        return frame if success else None

    def capture(self, duration: float) -> List[TimestampedFrame]:
        """
        Capture frames for a specific duration in seconds.

        Args:
            duration: Length of time to capture in seconds.

        Returns:
            A list of TimestampedFrame objects.
        """
        frames = []
        start_time = time.time()
        while (time.time() - start_time) < duration:
            success, frame, _ = self.read()
            if not success:
                break
            frames.append(frame)
        return frames

    def stream(
        self, duration: Optional[float] = None
    ) -> Generator[TimestampedFrame, None, None]:
        """
        A generator yielding frames at the regulated target FPS.

        Args:
            duration: Maximum duration of the stream in seconds. If None, runs indefinitely.
        """
        start_time = time.time()
        while True:
            if duration is not None and (time.time() - start_time) >= duration:
                break
            success, frame, _ = self.read()
            if not success:
                break
            yield frame

    def release(self):
        """Release OpenCV resources and close any open windows."""
        if hasattr(self, "cap") and self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Webcam Capture CLI")
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Webcam index (int) or video file path (str)",
    )
    parser.add_argument("--fps", type=int, default=15, help="Target FPS")
    parser.add_argument(
        "--duration", type=float, default=5.0, help="Duration to run in seconds"
    )
    args = parser.parse_args()

    # Determine if source is an integer index
    source_val = args.source
    if source_val.isdigit():
        source_val = int(source_val)

    try:
        cap = WebcamCapture(source=source_val, fps=args.fps)
    except Exception as e:
        print(f"Error initializing WebcamCapture: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"WebcamCapture started. Source: {source_val}, Target FPS: {args.fps}, Duration: {args.duration}s"
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
                cv2.imshow("Webcam Stream", frame)
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

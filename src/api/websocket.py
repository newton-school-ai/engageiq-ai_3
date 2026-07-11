"""WebSocket endpoint for real-time frame streaming and engagement score push-back.

Architecture:
- Browser sends base64-encoded BGR frames over a persistent WebSocket connection.
- Each frame is decoded, passed through the preprocessing pipeline, and scored.
- Engagement score + state are pushed back to the client on every frame.
- A ConnectionManager keeps a registry of all live sessions so the teacher
  dashboard (#33) and nudge delivery system (#21) can broadcast to individual
  students or all students in a session.
"""

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, Optional

import numpy as np
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from src.pipeline.preprocessor import FramePreprocessor
from src.scoring.engagement_score import compute_engagement_score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic-free message schemas (plain dicts for speed; validated below)
# ---------------------------------------------------------------------------
# Incoming  → {"frame": "<base64>", "timestamp": 1.0}
# Outgoing  → {"type": "engagement", "session_id": "...", "student_id": "...",
#               "score": 72.5, "state": "engaged", "timestamp": 1.0,
#               "frame_id": 42}
#           | {"type": "error", "message": "..."}
#           | {"type": "ack", "message": "Connected", "session_id": "..."}


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manages all active WebSocket connections, keyed by (session_id, student_id).

    Provides helpers for broadcasting to a whole session (used by the teacher
    dashboard) and for pushing nudges to a specific student.
    """

    def __init__(self) -> None:
        # { session_id: { student_id: WebSocket } }
        self._connections: Dict[str, Dict[str, WebSocket]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, session_id: str, student_id: str, ws: WebSocket) -> None:
        """Register an authenticated WebSocket."""
        self._connections.setdefault(session_id, {})[student_id] = ws
        logger.info(
            "WebSocket connected — session=%s student=%s  active_sessions=%d",
            session_id,
            student_id,
            len(self._connections),
        )

    def disconnect(self, session_id: str, student_id: str) -> None:
        """Remove a WebSocket and clean up empty session buckets."""
        session = self._connections.get(session_id, {})
        session.pop(student_id, None)
        if not session:
            self._connections.pop(session_id, None)
        logger.info(
            "WebSocket disconnected — session=%s student=%s  active_sessions=%d",
            session_id,
            student_id,
            len(self._connections),
        )

    # ------------------------------------------------------------------
    # Sending helpers
    # ------------------------------------------------------------------

    async def send(self, session_id: str, student_id: str, payload: dict) -> None:
        """Send a JSON payload to a specific student.  Silently drops if gone."""
        ws = self._connections.get(session_id, {}).get(student_id)
        if ws is not None:
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to send to session=%s student=%s: %s",
                    session_id,
                    student_id,
                    exc,
                )

    async def broadcast_to_session(self, session_id: str, payload: dict) -> None:
        """Broadcast a JSON payload to every student in a session (teacher dashboard)."""
        students = self._connections.get(session_id, {})
        tasks = [ws.send_json(payload) for ws in students.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for exc in results:
            if isinstance(exc, Exception):
                logger.warning("Broadcast error in session=%s: %s", session_id, exc)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_student_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, {}))

    def is_connected(self, session_id: str, student_id: str) -> bool:
        return student_id in self._connections.get(session_id, {})


# Singleton used by all route handlers and injectable in tests
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Frame processor (one per connection, owns its own preprocessor)
# ---------------------------------------------------------------------------


class FrameProcessor:
    """Decodes a base64 frame, preprocesses it, and returns an engagement score.

    The CV detection pipeline (gaze, pose, expression, alertness) is not yet
    fully wired—stubs return placeholder scores so the WebSocket layer can be
    tested in isolation.  Replace the stub calls with real detector calls once
    those modules (Issues #6-#12) are merged.
    """

    def __init__(self) -> None:
        self._preprocessor = FramePreprocessor(target_size=(640, 480))
        self._frame_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, payload: dict) -> dict:
        """Decode, preprocess, and score one frame.

        Args:
            payload: dict with keys ``frame`` (base64 str) and ``timestamp`` (float).

        Returns:
            Engagement result dict ready to send back to the client.

        Raises:
            ValueError: If the payload is malformed or the frame cannot be decoded.
        """
        self._frame_counter += 1
        frame_b64: Optional[str] = payload.get("frame")
        timestamp: float = float(payload.get("timestamp", time.time()))

        if not frame_b64:
            raise ValueError("Payload missing required key 'frame'")

        frame = self._decode_frame(frame_b64)
        preprocessed = self._preprocessor.process(frame)

        score = self._score_frame(preprocessed, timestamp)
        return {
            "type": "engagement",
            "score": round(score, 2),
            "state": self._score_to_state(score),
            "timestamp": timestamp,
            "frame_id": self._frame_counter,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_frame(frame_b64: str) -> np.ndarray:
        """Decode a base64-encoded raw pixel buffer into a uint8 NumPy array.

        The browser encodes raw RGB bytes (width=640, height=480) as base64.
        We reshape into (480, 640, 3) and hand off to the preprocessor.

        Raises:
            ValueError: On base64 or shape mismatch errors.
        """
        try:
            raw_bytes = base64.b64decode(frame_b64)
        except Exception as exc:
            raise ValueError(f"base64 decode failed: {exc}") from exc

        buffer = np.frombuffer(raw_bytes, dtype=np.uint8)

        # Try JPEG / PNG decode path first (browser MediaStream → canvas.toBlob)
        decoded = _try_imdecode(buffer)
        if decoded is not None:
            return decoded

        # Fall back to raw pixel buffer path (testing / Python clients)
        n_pixels = buffer.size
        if n_pixels % 3 != 0:
            raise ValueError(
                f"Raw buffer size {n_pixels} is not divisible by 3 — "
                "expected RGB or BGR pixel data"
            )
        n_total = n_pixels // 3
        # Pick the closest 4:3 resolution; default to 640×480
        h, w = _infer_dimensions(n_total)
        try:
            return buffer.reshape(h, w, 3)
        except ValueError as exc:
            raise ValueError(
                f"Cannot reshape {n_pixels} bytes into ({h}, {w}, 3): {exc}"
            ) from exc

    @staticmethod
    def _score_frame(frame: np.ndarray, timestamp: float) -> float:  # noqa: ARG004
        """Run CV detectors and return a 0-100 engagement score.

        NOTE: Detectors are stubbed until Issues #6-#12 land.  The stub
        derives a plausible score from frame statistics so the WebSocket
        layer is fully testable now.
        """
        # TODO(#6):  Replace with GazeClassifier.predict(frame)
        # TODO(#7):  Replace with HeadPoseEstimator.predict(frame)
        # TODO(#8):  Replace with ExpressionClassifier.predict(frame)
        # TODO(#9):  Replace with DrowsinessDetector.predict(frame)
        gaze_score = float(np.clip(frame.mean() * 100, 0, 100))
        pose_score = float(np.clip(frame.std() * 200, 0, 100))
        expression_score = 50.0  # neutral placeholder
        alertness_score = 75.0  # awake placeholder

        return compute_engagement_score(
            gaze_score=gaze_score,
            pose_score=pose_score,
            expression_score=expression_score,
            alertness_score=alertness_score,
        )

    @staticmethod
    def _score_to_state(score: float) -> str:
        """Map a 0-100 engagement score to a human-readable state label."""
        if score >= 75:
            return "engaged"
        if score >= 50:
            return "passive"
        if score >= 25:
            return "distracted"
        return "drowsy"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _try_imdecode(buffer: np.ndarray) -> Optional[np.ndarray]:
    """Attempt OpenCV JPEG/PNG decode; return None if it fails."""
    try:
        import cv2  # local import to avoid hard dep in unit tests

        img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        return img if img is not None else None
    except Exception:  # noqa: BLE001
        return None


def _infer_dimensions(n_pixels: int) -> tuple:
    """Derive (height, width) for a raw pixel buffer.

    Tries standard resolutions first, then falls back to a square approximation.
    """
    standard = [
        (480, 640),
        (720, 1280),
        (1080, 1920),
        (240, 320),
    ]
    for h, w in standard:
        if h * w == n_pixels:
            return h, w
    # Generic fallback: square-ish
    side = int(n_pixels**0.5)
    return side, side


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------


def _authenticate_token(session_id: str, token: Optional[str]) -> bool:
    """Validate a session token.

    Production: look up token in DB / Redis.
    Development: accept any non-empty token, or no token at all when
    ``settings.debug`` is True.

    Args:
        session_id: The session the client is trying to join.
        token:      Bearer token passed as a query parameter.

    Returns:
        True if the connection should be allowed.
    """
    from src.config.settings import (
        settings,
    )  # noqa: PLC0415   # deferred to avoid circular import

    if settings.debug:
        # In debug mode, allow unauthenticated connections (e.g. local testing)
        return True

    # TODO(#15): Replace with real JWT / session-token validation
    return bool(token)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/session/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    student_id: str = Query(default="anonymous"),
    token: Optional[str] = Query(default=None),
) -> None:
    """Stream frames from a student browser and push engagement scores back.

    URL: ``ws://host/ws/session/{session_id}?student_id=<id>&token=<jwt>``

    Message flow::

        Client  →  {"frame": "<base64>", "timestamp": 1234567890.123}
        Server  ←  {"type": "engagement", "score": 72.5, "state": "engaged",
                     "session_id": "1", "student_id": "alice",
                     "timestamp": 1234567890.123, "frame_id": 1}

    Error responses::

        Server  ←  {"type": "error", "message": "..."}

    The connection is closed with 1008 (policy violation) if authentication
    fails.
    """
    # --- Authentication --------------------------------------------------- #
    if not _authenticate_token(session_id, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(
            "Rejected unauthenticated connection — session=%s student=%s",
            session_id,
            student_id,
        )
        return

    # --- Handshake -------------------------------------------------------- #
    await websocket.accept()
    manager.connect(session_id, student_id, websocket)

    await websocket.send_json(
        {
            "type": "ack",
            "message": "Connected",
            "session_id": session_id,
            "student_id": student_id,
        }
    )

    processor = FrameProcessor()

    # --- Message loop ----------------------------------------------------- #
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                payload: Dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            try:
                result = processor.process(payload)
            except ValueError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Unexpected error processing frame — session=%s student=%s",
                    session_id,
                    student_id,
                )
                await websocket.send_json(
                    {"type": "error", "message": "Internal processing error"}
                )
                continue

            result["session_id"] = session_id
            result["student_id"] = student_id

            await websocket.send_json(result)

    except WebSocketDisconnect as exc:
        logger.info(
            "Client disconnected — session=%s student=%s code=%s",
            session_id,
            student_id,
            exc.code,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unhandled error in WebSocket loop — session=%s student=%s",
            session_id,
            student_id,
        )
    finally:
        # Always clean up, even if an unexpected exception fired
        manager.disconnect(session_id, student_id)
        logger.debug(
            "Cleaned up connection — session=%s student=%s", session_id, student_id
        )

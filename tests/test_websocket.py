"""Tests for the WebSocket frame-streaming endpoint.

Covers the three required acceptance criteria:
  1. Connection — client connects and receives an ACK.
  2. Frame processing — a valid base64 frame is decoded, processed, and an
     engagement score is returned.
  3. Disconnect handling — client disconnect is cleaned up without errors.

Additional tests:
  4. Invalid JSON is met with an error response (not a crash).
  5. Missing 'frame' key returns an error response.
  6. Multiple concurrent connections are tracked independently.

Run with:
    pytest tests/test_websocket.py -v
"""

import asyncio
import base64
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from src.api.main import app
from src.api.websocket import ConnectionManager, FrameProcessor, manager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_frame_b64(height: int = 480, width: int = 640) -> str:
    """Build a random raw-pixel base64 string that matches the expected shape."""
    raw = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    return base64.b64encode(raw.tobytes()).decode()


def _frame_payload(timestamp: float = 1.0) -> str:
    """Return a JSON-encoded frame message."""
    return json.dumps({"frame": _make_frame_b64(), "timestamp": timestamp})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Synchronous TestClient (uses ASGI transport)."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_manager():
    """Ensure ConnectionManager is empty before each test."""
    manager._connections.clear()
    yield
    manager._connections.clear()


# ---------------------------------------------------------------------------
# 1. Connection test
# ---------------------------------------------------------------------------


def test_websocket_connection_and_ack(client: TestClient):
    """A client connecting to /ws/session/{id} should receive an ACK message."""
    with client.websocket_connect(
        "/ws/session/test-session?student_id=student-1"
    ) as ws:
        ack = ws.receive_json()

    assert ack["type"] == "ack"
    assert ack["session_id"] == "test-session"
    assert ack["student_id"] == "student-1"
    assert "Connected" in ack["message"]


def test_websocket_connection_registers_in_manager(client: TestClient):
    """Connecting should register the student in ConnectionManager."""
    with client.websocket_connect("/ws/session/reg-session?student_id=alice") as ws:
        ws.receive_json()  # consume ACK
        assert manager.is_connected("reg-session", "alice")

    # After disconnect, entry is cleaned up
    assert not manager.is_connected("reg-session", "alice")


# ---------------------------------------------------------------------------
# 2. Frame processing test
# ---------------------------------------------------------------------------


def test_websocket_frame_processing_returns_engagement(client: TestClient):
    """Sending a valid base64 frame should return an engagement score response."""
    with client.websocket_connect("/ws/session/s1?student_id=bob") as ws:
        ws.receive_json()  # consume ACK

        ws.send_text(_frame_payload(timestamp=42.0))
        response = ws.receive_json()

    assert response["type"] == "engagement"
    assert response["session_id"] == "s1"
    assert response["student_id"] == "bob"
    assert 0.0 <= response["score"] <= 100.0
    assert response["state"] in {"engaged", "passive", "distracted", "drowsy"}
    assert response["timestamp"] == 42.0
    assert response["frame_id"] == 1


def test_websocket_frame_id_increments_per_frame(client: TestClient):
    """Each processed frame should increment the frame_id counter."""
    with client.websocket_connect("/ws/session/s2?student_id=carol") as ws:
        ws.receive_json()  # consume ACK

        for expected_id in range(1, 4):
            ws.send_text(_frame_payload())
            response = ws.receive_json()
            assert response["frame_id"] == expected_id


def test_websocket_invalid_json_returns_error(client: TestClient):
    """Sending malformed JSON should return an error, not crash the connection."""
    with client.websocket_connect("/ws/session/s3?student_id=dan") as ws:
        ws.receive_json()  # consume ACK

        ws.send_text("this is not json")
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "JSON" in error["message"]


def test_websocket_missing_frame_key_returns_error(client: TestClient):
    """Payload without a 'frame' key should return an error message."""
    with client.websocket_connect("/ws/session/s4?student_id=eve") as ws:
        ws.receive_json()  # consume ACK

        ws.send_text(json.dumps({"timestamp": 1.0}))
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "frame" in error["message"].lower()


# ---------------------------------------------------------------------------
# 3. Disconnect handling test
# ---------------------------------------------------------------------------


def test_websocket_disconnect_cleans_up(client: TestClient):
    """Disconnecting should remove the entry from ConnectionManager."""
    with client.websocket_connect("/ws/session/d1?student_id=frank") as ws:
        ws.receive_json()  # consume ACK
        assert manager.is_connected("d1", "frank")

    # Outside the context manager, disconnect has already occurred
    assert not manager.is_connected("d1", "frank")
    assert manager.active_student_count("d1") == 0


def test_websocket_disconnect_does_not_affect_other_students(client: TestClient):
    """Disconnecting one student should leave other students' connections intact."""
    with client.websocket_connect("/ws/session/group?student_id=grace") as ws_grace:
        ws_grace.receive_json()  # consume ACK

        with client.websocket_connect("/ws/session/group?student_id=hank") as ws_hank:
            ws_hank.receive_json()  # consume ACK

            # Both connected
            assert manager.is_connected("group", "grace")
            assert manager.is_connected("group", "hank")

        # hank disconnected
        assert not manager.is_connected("group", "hank")
        assert manager.is_connected("group", "grace")


# ---------------------------------------------------------------------------
# 4. Multiple concurrent connections
# ---------------------------------------------------------------------------


def test_websocket_multiple_concurrent_connections(client: TestClient):
    """Multiple students can connect to the same session simultaneously."""
    student_ids = ["s1", "s2", "s3"]
    contexts = [
        client.websocket_connect(f"/ws/session/multi?student_id={sid}")
        for sid in student_ids
    ]

    sockets: list[WebSocketTestSession] = []
    try:
        for ctx in contexts:
            ws = ctx.__enter__()
            ws.receive_json()  # consume ACK
            sockets.append(ws)

        assert manager.active_student_count("multi") == len(student_ids)

        # Each socket can independently send and receive
        for ws in sockets:
            ws.send_text(_frame_payload())
            resp = ws.receive_json()
            assert resp["type"] == "engagement"
    finally:
        for ctx in contexts:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 5. Unit tests for FrameProcessor (no HTTP / WS overhead)
# ---------------------------------------------------------------------------


class TestFrameProcessor:
    """Unit tests for FrameProcessor.process() in isolation."""

    def test_process_valid_raw_frame(self):
        """A correctly shaped raw-pixel base64 frame should succeed."""
        proc = FrameProcessor()
        payload = {"frame": _make_frame_b64(480, 640), "timestamp": 99.0}
        result = proc.process(payload)

        assert result["type"] == "engagement"
        assert 0.0 <= result["score"] <= 100.0
        assert result["frame_id"] == 1
        assert result["timestamp"] == 99.0

    def test_process_increments_frame_id(self):
        """Frame IDs should be monotonically increasing within one processor."""
        proc = FrameProcessor()
        payload = {"frame": _make_frame_b64(), "timestamp": 1.0}
        for i in range(1, 6):
            result = proc.process(payload)
            assert result["frame_id"] == i

    def test_process_missing_frame_raises(self):
        """Missing 'frame' key should raise ValueError."""
        proc = FrameProcessor()
        with pytest.raises(ValueError, match="frame"):
            proc.process({"timestamp": 1.0})

    def test_process_bad_base64_raises(self):
        """Completely invalid base64 data should raise ValueError."""
        proc = FrameProcessor()
        with pytest.raises(ValueError):
            proc.process({"frame": "!!!not-base64!!!", "timestamp": 1.0})


# ---------------------------------------------------------------------------
# 6. ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Unit tests for ConnectionManager lifecycle methods."""

    def test_connect_and_is_connected(self):
        cm = ConnectionManager()
        fake_ws = object()  # type: ignore[assignment]
        cm.connect("sess", "stu", fake_ws)  # type: ignore[arg-type]
        assert cm.is_connected("sess", "stu")

    def test_disconnect_removes_entry(self):
        cm = ConnectionManager()
        fake_ws = object()  # type: ignore[assignment]
        cm.connect("sess", "stu", fake_ws)  # type: ignore[arg-type]
        cm.disconnect("sess", "stu")
        assert not cm.is_connected("sess", "stu")

    def test_disconnect_empty_session_cleaned(self):
        cm = ConnectionManager()
        fake_ws = object()  # type: ignore[assignment]
        cm.connect("sess", "stu", fake_ws)  # type: ignore[arg-type]
        cm.disconnect("sess", "stu")
        assert "sess" not in cm._connections

    def test_active_student_count(self):
        cm = ConnectionManager()
        for i in range(3):
            cm.connect("sess", f"stu-{i}", object())  # type: ignore[arg-type]
        assert cm.active_student_count("sess") == 3

    def test_disconnect_nonexistent_is_safe(self):
        cm = ConnectionManager()
        cm.disconnect("no-session", "no-student")  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_to_session(self):
        """broadcast_to_session should call send_json on every connected WebSocket."""

        class FakeWS:
            def __init__(self):
                self.sent = []

            async def send_json(self, data):
                self.sent.append(data)

        cm = ConnectionManager()
        ws1, ws2 = FakeWS(), FakeWS()
        cm.connect("bcast", "s1", ws1)  # type: ignore[arg-type]
        cm.connect("bcast", "s2", ws2)  # type: ignore[arg-type]

        await cm.broadcast_to_session("bcast", {"type": "nudge"})

        assert ws1.sent == [{"type": "nudge"}]
        assert ws2.sent == [{"type": "nudge"}]

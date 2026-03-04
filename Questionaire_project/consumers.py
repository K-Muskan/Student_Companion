import asyncio
import base64
import binascii
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils.dateparse import parse_datetime

from .emotion_limits import consume_frame_quota, release_connection, touch_connection, try_acquire_connection
from .emotion_worker import EmotionInferenceWorker, STATUS_OK as WORKER_STATUS_OK

STATUS_OK = "ok"
STATUS_NO_FACE = "no_face"
STATUS_ERROR = "error"
STATUS_QUALITY_LOW = "quality_low"
STATUS_RATE_LIMITED = "rate_limited"

logger = logging.getLogger(__name__)

_worker_guard = threading.Lock()
_worker_instance: Optional[EmotionInferenceWorker] = None


def get_inference_worker(max_memory_mb: int) -> EmotionInferenceWorker:
    global _worker_instance
    with _worker_guard:
        if _worker_instance is None:
            _worker_instance = EmotionInferenceWorker(max_memory_mb=max_memory_mb)
        _worker_instance.ensure_running()
        return _worker_instance


class EmotionStreamConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.correlation_id = uuid.uuid4().hex
        self.lease_id = uuid.uuid4().hex
        self.assessment_id = int(self.scope["url_route"]["kwargs"]["assessment_id"])
        self.client_ip = self._resolve_client_ip()
        self.analysis_interval = float(getattr(settings, "EMOTION_ANALYZE_INTERVAL_SECONDS", 1.0))
        self.max_image_bytes = int(getattr(settings, "EMOTION_MAX_IMAGE_BYTES", 1500000))
        self.max_encoded_image_bytes = int(getattr(settings, "EMOTION_MAX_ENCODED_IMAGE_BYTES", 2200000))
        self.max_pixels = int(getattr(settings, "EMOTION_MAX_PIXELS", 2073600))
        self.max_width = int(getattr(settings, "EMOTION_MAX_WIDTH", 1920))
        self.max_height = int(getattr(settings, "EMOTION_MAX_HEIGHT", 1080))
        self.min_brightness = int(getattr(settings, "EMOTION_MIN_BRIGHTNESS", 20))
        self.max_brightness = int(getattr(settings, "EMOTION_MAX_BRIGHTNESS", 235))
        self.min_blur_variance = float(getattr(settings, "EMOTION_MIN_BLUR_VARIANCE", 35.0))
        self.min_face_confidence = float(getattr(settings, "EMOTION_MIN_FACE_CONFIDENCE", 0.55))
        self.inference_timeout = float(getattr(settings, "EMOTION_INFERENCE_TIMEOUT_SECONDS", 6.0))
        self.inference_max_memory_mb = int(getattr(settings, "EMOTION_INFERENCE_MAX_MEMORY_MB", 512))
        self.inference_restart_threshold = int(getattr(settings, "EMOTION_WORKER_RESTART_TIMEOUT_THRESHOLD", 3))
        self.max_connections_per_ip = int(getattr(settings, "EMOTION_MAX_CONNECTIONS_PER_IP", 4))
        self.max_connections_per_assessment = int(getattr(settings, "EMOTION_MAX_CONNECTIONS_PER_ASSESSMENT", 1))
        self.max_frames_per_assessment_window = int(getattr(settings, "EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW", 120))
        self.frame_quota_window_seconds = int(getattr(settings, "EMOTION_FRAME_QUOTA_WINDOW_SECONDS", 60))
        self.connection_ttl_seconds = int(getattr(settings, "EMOTION_CONNECTION_TTL_SECONDS", 120))
        self.face_track_iou_threshold = float(getattr(settings, "EMOTION_FACE_TRACK_IOU_THRESHOLD", 0.25))
        self.allowed_origins = set(getattr(settings, "EMOTION_ALLOWED_ORIGINS", []))
        self.allowed_origin_suffixes = tuple(getattr(settings, "EMOTION_ALLOWED_ORIGIN_SUFFIXES", []))
        self.heartbeat_grace_seconds = float(getattr(settings, "EMOTION_HEARTBEAT_GRACE_SECONDS", 90.0))
        self.heartbeat_check_seconds = float(getattr(settings, "EMOTION_HEARTBEAT_CHECK_SECONDS", 5.0))
        self.enforce_ping_timeout = bool(getattr(settings, "EMOTION_ENFORCE_PING_TIMEOUT", True))

        self.last_analyzed_at = 0.0
        self.last_ping_at = time.monotonic()
        self.last_message_at = time.monotonic()
        self.processing = False
        self.subject_box: Optional[Tuple[int, int, int, int]] = None
        self._connection_acquired = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        if not self._origin_allowed():
            await self.close(code=4403)
            return

        allowed = await self._can_access_assessment(self.assessment_id)
        if not allowed:
            await self.close(code=4403)
            return

        acquired = try_acquire_connection(
            client_ip=self.client_ip,
            assessment_id=self.assessment_id,
            lease_id=self.lease_id,
            max_ip=self.max_connections_per_ip,
            max_assessment=self.max_connections_per_assessment,
            ttl_seconds=max(30, self.connection_ttl_seconds),
        )
        if not acquired:
            await self.close(code=4429)
            return
        self._connection_acquired = True

        await self.accept()
        self._heartbeat_task = asyncio.create_task(self._watch_heartbeat())
        logger.info(
            "emotion_websocket_connected",
            extra={"correlation_id": self.correlation_id, "assessment_id": self.assessment_id, "client_ip": self.client_ip},
        )
        await self.send_json(
            {
                "type": "connection",
                "status": "connected",
                "assessment_id": self.assessment_id,
                "analysis_interval_seconds": self.analysis_interval,
                "max_reconnect_attempts": int(getattr(settings, "EMOTION_MAX_RECONNECT_ATTEMPTS", 5)),
                "heartbeat_interval_seconds": float(getattr(settings, "EMOTION_HEARTBEAT_INTERVAL_SECONDS", 15)),
                "heartbeat_grace_seconds": self.heartbeat_grace_seconds,
                "correlation_id": self.correlation_id,
            }
        )

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        self.last_message_at = time.monotonic()
        if self._connection_acquired:
            touch_connection(self.lease_id, ttl_seconds=max(30, self.connection_ttl_seconds))
        msg_type = content.get("type")
        if msg_type == "ping":
            self.last_ping_at = time.monotonic()
            await self.send_json({"type": "pong", "ts": content.get("ts"), "server_ts": time.time(), "correlation_id": self.correlation_id})
            return

        if msg_type != "frame":
            await self.send_json({"type": "error", "message": "Unsupported message type", "correlation_id": self.correlation_id})
            return

        try:
            payload_assessment_id = int(content.get("assessment_id", -1))
        except (TypeError, ValueError):
            await self.send_json({"type": "error", "message": "assessment_id invalid", "correlation_id": self.correlation_id})
            return
        if payload_assessment_id != self.assessment_id:
            await self.send_json({"type": "error", "message": "assessment_id mismatch", "correlation_id": self.correlation_id})
            return

        image_base64 = content.get("image_base64")
        question_id = content.get("question_id")
        client_ts_raw = content.get("client_ts")
        frame_id = content.get("frame_id") or uuid.uuid4().hex
        if not image_base64:
            await self.send_json({"type": "error", "message": "image_base64 missing", "correlation_id": self.correlation_id})
            return

        now = time.monotonic()
        if self.processing:
            await self.send_json(
                {"type": "frame_result", "frame_id": frame_id, "status": "dropped", "reason": "busy", "correlation_id": self.correlation_id}
            )
            return
        if now - self.last_analyzed_at < self.analysis_interval:
            await self.send_json(
                {"type": "frame_result", "frame_id": frame_id, "status": "dropped", "reason": "throttled", "correlation_id": self.correlation_id}
            )
            return

        quota_ok, quota_count = consume_frame_quota(
            self.assessment_id,
            self.max_frames_per_assessment_window,
            self.frame_quota_window_seconds,
        )
        if not quota_ok:
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion="",
                emotion_scores={},
                confidence=None,
                status=STATUS_RATE_LIMITED,
                client_ts_raw=client_ts_raw,
            )
            logger.info(
                "emotion_frame_rate_limited",
                extra={"correlation_id": self.correlation_id, "assessment_id": self.assessment_id, "quota_count": quota_count},
            )
            await self.send_json({"type": "frame_result", "frame_id": frame_id, "status": STATUS_RATE_LIMITED, "correlation_id": self.correlation_id})
            return

        self.processing = True
        self.last_analyzed_at = now
        started = time.monotonic()
        try:
            result = await self._analyze_frame(image_base64, frame_id)
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion=result.get("dominant_emotion", ""),
                emotion_scores=result.get("emotion_scores", {}),
                confidence=result.get("confidence"),
                status=result.get("status", STATUS_ERROR),
                client_ts_raw=client_ts_raw,
            )
            status = result.get("status", STATUS_ERROR)
            payload = {
                "type": "frame_result",
                "frame_id": frame_id,
                "status": status,
                "dominant_emotion": result.get("dominant_emotion", ""),
                "emotion_scores": result.get("emotion_scores", {}),
                "confidence": result.get("confidence"),
                "latency_ms": int((time.monotonic() - started) * 1000),
                "correlation_id": self.correlation_id,
            }
            if result.get("message"):
                payload["message"] = result["message"]
            if result.get("details"):
                payload["details"] = result["details"]
            logger.info(
                "emotion_frame_processed",
                extra={
                    "correlation_id": self.correlation_id,
                    "assessment_id": self.assessment_id,
                    "status": status,
                    "latency_ms": payload["latency_ms"],
                },
            )
            await self.send_json(payload)
        except ValueError as exc:
            logger.warning(
                "emotion_frame_validation_failed",
                extra={
                    "correlation_id": self.correlation_id,
                    "assessment_id": self.assessment_id,
                    "reason": str(exc),
                },
            )
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion="",
                emotion_scores={},
                confidence=None,
                status=STATUS_ERROR,
                client_ts_raw=client_ts_raw,
            )
            await self.send_json(
                {
                    "type": "frame_result",
                    "frame_id": frame_id,
                    "status": STATUS_ERROR,
                    "message": "invalid_frame",
                    "correlation_id": self.correlation_id,
                }
            )
        except Exception:
            logger.exception("emotion_analysis_failed", extra={"correlation_id": self.correlation_id, "assessment_id": self.assessment_id})
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion="",
                emotion_scores={},
                confidence=None,
                status=STATUS_ERROR,
                client_ts_raw=client_ts_raw,
            )
            await self.send_json(
                {"type": "frame_result", "frame_id": frame_id, "status": STATUS_ERROR, "message": "analysis_failed", "correlation_id": self.correlation_id}
            )
        finally:
            self.processing = False

    async def disconnect(self, close_code):
        try:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None
        finally:
            try:
                if self._connection_acquired:
                    release_connection(self.lease_id, ttl_seconds=max(30, self.connection_ttl_seconds))
            finally:
                self.processing = False
                logger.info(
                    "emotion_websocket_disconnected",
                    extra={
                        "correlation_id": getattr(self, "correlation_id", "n/a"),
                        "assessment_id": getattr(self, "assessment_id", None),
                        "close_code": close_code,
                    },
                )

    async def _analyze_frame(self, image_base64: str, frame_id: str) -> Dict[str, Any]:
        image_bytes = self._decode_base64_image(image_base64)
        if len(image_bytes) > self.max_image_bytes:
            return self._error_result("image_too_large")

        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return self._error_result("decode_failed")
        h, w = frame.shape[:2]
        if h <= 0 or w <= 0:
            return self._error_result("invalid_dimensions")
        if h > self.max_height or w > self.max_width or (h * w) > self.max_pixels:
            return self._error_result("oversize_dimensions")
        passes_quality, quality_meta = self._passes_quality_gate(frame)
        if not passes_quality:
            return {
                "status": STATUS_QUALITY_LOW,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": None,
                "message": quality_meta.get("reason", "quality_low"),
                "details": quality_meta,
            }

        worker = get_inference_worker(self.inference_max_memory_mb)
        request_id = uuid.uuid4().hex
        queued = await asyncio.to_thread(
            worker.submit,
            {
                "type": "frame",
                "request_id": request_id,
                "frame_id": frame_id,
                "assessment_id": self.assessment_id,
                "correlation_id": self.correlation_id,
                "image_bytes": image_bytes,
            },
        )
        if not queued:
            return self._error_result("worker_queue_full", {"reason": "inference_backpressure"})

        worker_result = await asyncio.to_thread(worker.wait_for, request_id, self.inference_timeout)
        if worker_result is None:
            await asyncio.to_thread(worker.register_timeout, self.inference_restart_threshold)
            logger.warning("emotion_inference_timeout", extra={"correlation_id": self.correlation_id, "assessment_id": self.assessment_id})
            return self._error_result("timeout", {"reason": "inference_timeout"})

        if worker_result.get("status") != WORKER_STATUS_OK:
            worker_error = str(worker_result.get("error", "worker_error"))[:200]
            lower_err = worker_error.lower()
            if "no module named 'deepface'" in lower_err or "deepface_import_failed" in lower_err:
                # Import/config issue should not trigger crash-restart loops.
                return self._error_result("model_unavailable", {"reason": worker_error})
            if worker_result.get("error") == "worker_crashed":
                await asyncio.to_thread(worker.register_crash, self.inference_restart_threshold)
            else:
                await asyncio.to_thread(worker.register_error, self.inference_restart_threshold)
            return self._error_result("worker_error", {"reason": worker_error})
        await asyncio.to_thread(worker.register_success)

        faces = worker_result.get("faces") or []
        if not faces:
            return {"status": STATUS_NO_FACE, "dominant_emotion": "", "emotion_scores": {}, "confidence": None, "message": "no_face_detected"}
        if len(faces) > 1 and self.subject_box is None:
            return {"status": STATUS_NO_FACE, "dominant_emotion": "", "emotion_scores": {}, "confidence": None, "message": "multiple_faces_detected"}

        best_face = self._pick_subject_face(faces)
        if best_face is None:
            return {"status": STATUS_NO_FACE, "dominant_emotion": "", "emotion_scores": {}, "confidence": None, "message": "subject_tracking_lost"}
        confidence = self._face_conf(best_face)
        if confidence < self.min_face_confidence:
            return {
                "status": STATUS_QUALITY_LOW,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": confidence,
                "message": "face_confidence_low",
                "details": {
                    "face_confidence": confidence,
                    "min_face_confidence": self.min_face_confidence,
                },
            }

        dominant_emotion = str(best_face.get("dominant_emotion", "") or "")
        raw_scores = best_face.get("emotion", {}) or {}
        emotion_scores: Dict[str, float] = {}
        for key, value in raw_scores.items():
            try:
                emotion_scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if not dominant_emotion:
            return {
                "status": STATUS_NO_FACE,
                "dominant_emotion": "",
                "emotion_scores": emotion_scores,
                "confidence": confidence,
                "message": "dominant_emotion_missing",
            }
        return {
            "status": STATUS_OK,
            "dominant_emotion": dominant_emotion,
            "emotion_scores": emotion_scores,
            "confidence": confidence,
        }

    def _decode_base64_image(self, image_base64: str) -> bytes:
        payload = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
        encoded_len = len(payload.encode("utf-8"))
        if encoded_len > self.max_encoded_image_bytes:
            raise ValueError("encoded payload too large")
        expected_decoded = (len(payload) * 3) // 4
        if expected_decoded > self.max_image_bytes:
            raise ValueError("decoded payload exceeds max bytes")
        try:
            return base64.b64decode(payload, validate=True)
        except binascii.Error as exc:
            raise ValueError("invalid base64 payload") from exc

    def _error_result(self, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"status": STATUS_ERROR, "message": message, "dominant_emotion": "", "emotion_scores": {}, "confidence": None}
        if details:
            payload["details"] = details
        return payload

    def _passes_quality_gate(self, frame: np.ndarray) -> Tuple[bool, Dict[str, Any]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        if blur_var < self.min_blur_variance:
            return False, {
                "reason": "blur_low",
                "blur_variance": blur_var,
                "min_blur_variance": self.min_blur_variance,
                "brightness": brightness,
            }
        if brightness < self.min_brightness:
            return False, {
                "reason": "brightness_low",
                "brightness": brightness,
                "min_brightness": self.min_brightness,
                "blur_variance": blur_var,
            }
        if brightness > self.max_brightness:
            return False, {
                "reason": "brightness_high",
                "brightness": brightness,
                "max_brightness": self.max_brightness,
                "blur_variance": blur_var,
            }
        return True, {"reason": "ok", "blur_variance": blur_var, "brightness": brightness}

    def _face_conf(self, face: Dict[str, Any]) -> float:
        value = face.get("face_confidence")
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _face_box(self, face: Dict[str, Any]) -> Optional[Tuple[int, int, int, int]]:
        region = face.get("region") or {}
        try:
            x, y = int(region.get("x", 0)), int(region.get("y", 0))
            w, h = int(region.get("w", 0)), int(region.get("h", 0))
        except (TypeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return (x, y, x + w, y + h)

    def _iou(self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
        inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter = inter_w * inter_h
        if inter == 0:
            return 0.0
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / max(area_a + area_b - inter, 1)

    def _pick_subject_face(self, faces: list) -> Optional[Dict[str, Any]]:
        if len(faces) == 1:
            self.subject_box = self._face_box(faces[0])
            return faces[0]
        if self.subject_box is None:
            return None
        best = None
        best_iou = 0.0
        for face in faces:
            box = self._face_box(face)
            if not box:
                continue
            score = self._iou(self.subject_box, box)
            if score > best_iou:
                best_iou = score
                best = face
        if best is None or best_iou < self.face_track_iou_threshold:
            return None
        self.subject_box = self._face_box(best)
        return best

    def _origin_allowed(self) -> bool:
        origin = None
        headers = dict(self.scope.get("headers") or [])
        if b"origin" in headers:
            origin = headers[b"origin"].decode("utf-8", "ignore").rstrip("/")
        if not self.allowed_origins and not self.allowed_origin_suffixes:
            return False
        if origin is None:
            return False
        normalized = origin.rstrip("/")
        if normalized in {o.rstrip("/") for o in self.allowed_origins}:
            return True
        parsed = urlparse(normalized)
        hostname = (parsed.hostname or "").lower()
        for suffix in self.allowed_origin_suffixes:
            suffix_norm = str(suffix or "").strip().lower()
            if suffix_norm and hostname.endswith(suffix_norm):
                return True
        return False

    def _resolve_client_ip(self) -> str:
        client = self.scope.get("client")
        if isinstance(client, (list, tuple)) and client:
            return str(client[0])
        return "unknown"

    @database_sync_to_async
    def _can_access_assessment(self, assessment_id: int) -> bool:
        from .models import Assessment

        assessment = Assessment.objects.filter(id=assessment_id).first()
        if not assessment:
            return False
        user = self.scope.get("user")
        if user and user.is_authenticated:
            return assessment.user_id == user.id
        session = self.scope.get("session")
        session_key = getattr(session, "session_key", None)
        return bool(session_key and assessment.session_key == session_key)

    @database_sync_to_async
    def _save_record(
        self,
        assessment_id: int,
        question_id: Optional[int],
        dominant_emotion: str,
        emotion_scores: Dict[str, float],
        confidence: Optional[float],
        status: str,
        client_ts_raw: Optional[str],
    ):
        from .models import Assessment, EmotionRecord, Question

        assessment = Assessment.objects.filter(id=assessment_id).first()
        if not assessment:
            return
        if question_id is not None:
            try:
                question_id = int(question_id)
            except (TypeError, ValueError):
                question_id = None
        question = Question.objects.filter(id=question_id).first() if question_id is not None else None
        client_ts = parse_datetime(client_ts_raw) if client_ts_raw else None
        EmotionRecord.objects.create(
            assessment=assessment,
            question=question,
            dominant_emotion=dominant_emotion,
            emotion_scores=emotion_scores,
            confidence=confidence,
            status=status,
            client_ts=client_ts,
        )

    async def _safe_save_record(self, **kwargs):
        try:
            await self._save_record(**kwargs)
        except Exception:
            logger.exception(
                "emotion_record_save_failed",
                extra={"correlation_id": self.correlation_id, "assessment_id": self.assessment_id},
            )

    async def _watch_heartbeat(self):
        try:
            while True:
                await asyncio.sleep(max(1.0, self.heartbeat_check_seconds))
                if not self._connection_acquired:
                    return
                age = time.monotonic() - self.last_message_at
                if age > max(60.0, self.heartbeat_grace_seconds):
                    logger.warning(
                        "emotion_ping_timeout",
                        extra={
                            "correlation_id": self.correlation_id,
                            "assessment_id": self.assessment_id,
                            "age_seconds": round(age, 2),
                            "enforce_close": self.enforce_ping_timeout,
                        },
                    )
                    if self.enforce_ping_timeout:
                        await self.close(code=4408)
                        return
        except asyncio.CancelledError:
            return

import asyncio
import base64
import binascii
import logging
import platform
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .emotion_limits import consume_frame_quota, release_connection, touch_connection, try_acquire_connection
from .emotion_services import finalize_scale_emotion_session
from .emotion_worker import EmotionInferenceWorker, STATUS_OK as WORKER_STATUS_OK, analyze_frame_sync

STATUS_OK = "ok"
STATUS_NO_FACE = "no_face"
STATUS_ERROR = "error"
STATUS_QUALITY_LOW = "quality_low"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_FALLBACK = "fallback"
STATUS_UNCERTAIN = "uncertain"

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
    def _log_event(
        self,
        level: int,
        event: str,
        *,
        frame_id: Optional[str] = None,
        debug_only: bool = False,
        **extra: Any,
    ) -> None:
        if debug_only and not getattr(self, "emotion_debug", False):
            return
        payload = {
            "correlation_id": getattr(self, "correlation_id", None),
            "assessment_id": getattr(self, "assessment_id", None),
            "frame_id": frame_id,
        }
        payload.update(extra)
        logger.log(level, event, extra=payload)

    def _normalize_result_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload or {})
        from .models import EmotionRecord

        valid_statuses = {choice[0] for choice in EmotionRecord.STATUS_CHOICES}
        status = str(normalized.get("status") or STATUS_FALLBACK)
        if status not in valid_statuses:
            status = STATUS_FALLBACK

        dominant_emotion = str(normalized.get("dominant_emotion") or "").strip() or "neutral"

        raw_scores = normalized.get("emotion_scores") or {}
        emotion_scores: Dict[str, float] = {}
        if isinstance(raw_scores, dict):
            for key, value in raw_scores.items():
                key_text = str(key or "").strip()
                if not key_text:
                    continue
                try:
                    emotion_scores[key_text] = float(value)
                except (TypeError, ValueError):
                    continue
        if not emotion_scores:
            fallback_score = normalized.get("confidence")
            try:
                fallback_score = float(fallback_score) if fallback_score is not None else 0.1
            except (TypeError, ValueError):
                fallback_score = 0.1
            emotion_scores = {dominant_emotion: max(fallback_score, 0.1)}
        elif dominant_emotion not in emotion_scores:
            top_key = max(emotion_scores, key=emotion_scores.get)
            dominant_emotion = top_key or dominant_emotion

        normalized["status"] = status
        normalized["dominant_emotion"] = dominant_emotion
        normalized["emotion_scores"] = emotion_scores
        if normalized.get("confidence") is None:
            normalized["confidence"] = 0.1 if status == STATUS_FALLBACK else None
        return normalized

    def _fallback_result(self, reason: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "status": STATUS_FALLBACK,
            "dominant_emotion": "neutral",
            "emotion_scores": {"neutral": 0.1},
            "confidence": 0.1,
            "message": "emotion_fallback_applied",
            "details": {"reason": reason},
        }
        if details:
            payload["details"].update(details)
        return self._normalize_result_payload(payload)

    def _loop_is_usable(self) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return not loop.is_closed()

    async def connect(self):
        self.correlation_id = uuid.uuid4().hex
        self.lease_id = uuid.uuid4().hex
        self.assessment_id = int(self.scope["url_route"]["kwargs"]["assessment_id"])
        self.scale = str(self.scope["url_route"]["kwargs"]["scale"])
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
        self.uncertain_threshold = float(getattr(settings, "EMOTION_UNCERTAIN_THRESHOLD", 45.0))
        self.angry_suppression_threshold = float(getattr(settings, "EMOTION_ANGRY_SUPPRESSION_THRESHOLD", 60.0))
        self.identical_result_window = max(2, int(getattr(settings, "EMOTION_IDENTICAL_RESULT_WINDOW", 5)))
        self.debug_noise_test = bool(getattr(settings, "EMOTION_DEBUG_NOISE_TEST", False))
        self.inference_timeout = float(getattr(settings, "EMOTION_INFERENCE_TIMEOUT_SECONDS", 6.0))
        self.inference_max_memory_mb = int(getattr(settings, "EMOTION_INFERENCE_MAX_MEMORY_MB", 512))
        self.inference_restart_threshold = int(getattr(settings, "EMOTION_WORKER_RESTART_TIMEOUT_THRESHOLD", 3))
        self.max_connections_per_ip = int(getattr(settings, "EMOTION_MAX_CONNECTIONS_PER_IP", 4))
        self.max_connections_per_assessment = int(getattr(settings, "EMOTION_MAX_CONNECTIONS_PER_ASSESSMENT", 1))
        self.max_frames_per_assessment_window = int(getattr(settings, "EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW", 120))
        self.frame_quota_window_seconds = int(getattr(settings, "EMOTION_FRAME_QUOTA_WINDOW_SECONDS", 60))
        self.connection_ttl_seconds = int(getattr(settings, "EMOTION_CONNECTION_TTL_SECONDS", 120))
        self.face_track_iou_threshold = float(getattr(settings, "EMOTION_FACE_TRACK_IOU_THRESHOLD", 0.25))
        self.min_face_area_ratio = float(getattr(settings, "EMOTION_MIN_FACE_AREA_RATIO", 0.03))
        self.allowed_origins = set(getattr(settings, "EMOTION_ALLOWED_ORIGINS", []))
        self.allowed_origin_suffixes = tuple(getattr(settings, "EMOTION_ALLOWED_ORIGIN_SUFFIXES", []))
        self.heartbeat_grace_seconds = float(getattr(settings, "EMOTION_HEARTBEAT_GRACE_SECONDS", 90.0))
        self.heartbeat_check_seconds = float(getattr(settings, "EMOTION_HEARTBEAT_CHECK_SECONDS", 5.0))
        self.enforce_ping_timeout = bool(getattr(settings, "EMOTION_ENFORCE_PING_TIMEOUT", True))
        self.emotion_debug = bool(getattr(settings, "EMOTION_DEBUG", False))
        self.use_direct_inference = platform.system().lower() == "windows"

        self.last_analyzed_at = 0.0
        self.last_ping_at = time.monotonic()
        self.last_message_at = time.monotonic()
        self.connection_started_at = time.monotonic()
        self.frame_sequence = 0
        self.processing = False
        self.subject_box: Optional[Tuple[int, int, int, int]] = None
        self.recent_frame_hashes = deque(maxlen=self.identical_result_window)
        self.recent_result_signatures = deque(maxlen=self.identical_result_window)
        self._connection_acquired = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        if self.scale not in {"depression", "stress", "anxiety"}:
            await self.close(code=4400)
            return

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
        await self._start_scale_session()
        self._heartbeat_task = asyncio.create_task(self._watch_heartbeat())
        self._log_event(
            logging.INFO,
            "emotion_websocket_connected",
            scale=self.scale,
            client_ip=self.client_ip,
        )
        await self.send_json(
            {
                "type": "connection",
                "status": "connected",
                "assessment_id": self.assessment_id,
                "scale": self.scale,
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
        payload_scale = str(content.get("scale") or self.scale)
        client_ts_raw = content.get("client_ts")
        frame_id = content.get("frame_id") or uuid.uuid4().hex
        frame_number = content.get("frame_number")
        timestamp_sec = content.get("timestamp_sec")
        if not image_base64:
            await self.send_json({"type": "error", "message": "image_base64 missing", "correlation_id": self.correlation_id})
            return
        if payload_scale != self.scale:
            await self.send_json({"type": "error", "message": "scale mismatch", "correlation_id": self.correlation_id})
            await self.close(code=4409)
            return

        self.frame_sequence += 1
        if frame_number is None:
            frame_number = self.frame_sequence
        try:
            frame_number = int(frame_number)
        except (TypeError, ValueError):
            frame_number = self.frame_sequence
        if timestamp_sec is None:
            timestamp_sec = round(time.monotonic() - self.connection_started_at, 3)
        try:
            timestamp_sec = float(timestamp_sec)
        except (TypeError, ValueError):
            timestamp_sec = round(time.monotonic() - self.connection_started_at, 3)

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
                scale=self.scale,
                question_id=question_id,
                frame_id=frame_id,
                frame_number=frame_number,
                timestamp_sec=timestamp_sec,
                dominant_emotion="neutral",
                emotion_scores={"neutral": 0.1},
                confidence=0.1,
                status=STATUS_RATE_LIMITED,
                client_ts_raw=client_ts_raw,
            )
            self._log_event(logging.INFO, "emotion_frame_rate_limited", frame_id=frame_id, quota_count=quota_count)
            await self.send_json({"type": "frame_result", "frame_id": frame_id, "status": STATUS_RATE_LIMITED, "correlation_id": self.correlation_id})
            return

        self.processing = True
        self.last_analyzed_at = now
        started = time.monotonic()
        try:
            result = self._normalize_result_payload(await self._analyze_frame(image_base64, frame_id))
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                scale=self.scale,
                question_id=question_id,
                frame_id=frame_id,
                frame_number=frame_number,
                timestamp_sec=timestamp_sec,
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
                "frame_number": frame_number,
                "timestamp_sec": timestamp_sec,
                "status": status,
                "dominant_emotion": result.get("dominant_emotion", ""),
                "emotion_scores": result.get("emotion_scores", {}),
                "confidence": result.get("confidence"),
                "emotion": result.get("dominant_emotion", ""),
                "scores": result.get("emotion_scores", {}),
                "latency_ms": int((time.monotonic() - started) * 1000),
                "correlation_id": self.correlation_id,
            }
            if result.get("message"):
                payload["message"] = result["message"]
            if result.get("details"):
                payload["details"] = result["details"]
            self._log_event(
                logging.INFO,
                "emotion_inference_result",
                frame_id=frame_id,
                status=status,
                dominant_emotion=payload.get("dominant_emotion"),
                latency_ms=payload["latency_ms"],
            )
            await self.send_json(payload)
        except ValueError as exc:
            self._log_event(logging.WARNING, "emotion_frame_validation_failed", frame_id=frame_id, reason=str(exc))
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                scale=self.scale,
                question_id=question_id,
                frame_id=frame_id,
                frame_number=frame_number,
                timestamp_sec=timestamp_sec,
                dominant_emotion="neutral",
                emotion_scores={"neutral": 0.1},
                confidence=0.1,
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
            logger.exception(
                "emotion_analysis_failed",
                extra={
                    "correlation_id": self.correlation_id,
                    "assessment_id": self.assessment_id,
                    "frame_id": frame_id,
                },
            )
            await self._safe_save_record(
                assessment_id=self.assessment_id,
                scale=self.scale,
                question_id=question_id,
                frame_id=frame_id,
                frame_number=frame_number,
                timestamp_sec=timestamp_sec,
                dominant_emotion="neutral",
                emotion_scores={"neutral": 0.1},
                confidence=0.1,
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
                await self._finish_scale_session()
                if self._connection_acquired:
                    release_connection(self.lease_id, ttl_seconds=max(30, self.connection_ttl_seconds))
            finally:
                self.processing = False
                self._log_event(
                    logging.INFO,
                    "emotion_websocket_disconnected",
                    scale=getattr(self, "scale", None),
                    close_code=close_code,
                )

    async def _analyze_frame(self, image_base64: str, frame_id: str) -> Dict[str, Any]:
        if not self._loop_is_usable():
            self._log_event(logging.WARNING, "emotion_loop_closed_skip_processing", frame_id=frame_id)
            return self._error_result("loop_closed")
        try:
            image_bytes = self._decode_base64_image(image_base64)
        except ValueError as exc:
            self._log_event(logging.WARNING, "emotion_base64_decode_failed", frame_id=frame_id, reason=str(exc))
            raise
        if len(image_bytes) > self.max_image_bytes:
            return self._error_result("image_too_large")

        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return self._error_result("decode_failed")
        if not isinstance(frame, np.ndarray):
            return self._error_result("invalid_frame_array")
        h, w = frame.shape[:2]
        frame_hash = str(hash(frame.tobytes()))
        pixel_sum = int(np.sum(frame, dtype=np.int64))
        print("Frame:", frame_id, "Hash:", frame_hash, "PixelSum:", pixel_sum)
        self._log_event(logging.DEBUG, "emotion_frame_decoded", frame_id=frame_id, debug_only=True, height=h, width=w)
        self._log_event(logging.DEBUG, "emotion_frame_shape", frame_id=frame_id, debug_only=True, shape=list(frame.shape))
        self._log_event(logging.INFO, "emotion_frame_fingerprint", frame_id=frame_id, frame_hash=frame_hash, pixel_sum=pixel_sum)
        if h <= 0 or w <= 0:
            return self._error_result("invalid_dimensions")
        if h > self.max_height or w > self.max_width or (h * w) > self.max_pixels:
            return self._error_result("oversize_dimensions")
        if self.recent_frame_hashes and self.recent_frame_hashes[-1] == frame_hash:
            self._log_event(logging.WARNING, "emotion_duplicate_frame_hash", frame_id=frame_id, frame_hash=frame_hash)
            return self._error_result("duplicate_frame", {"frame_hash": frame_hash})
        passes_quality, quality_meta = self._passes_quality_gate(frame)
        quality_warning = None if passes_quality else quality_meta
        if self.emotion_debug:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self._log_event(
                logging.DEBUG,
                "emotion_frame_stats",
                frame_id=frame_id,
                debug_only=True,
                mean_brightness=round(float(np.mean(gray)), 2),
                min_pixel=int(np.min(gray)),
                max_pixel=int(np.max(gray)),
            )

        if self.use_direct_inference:
            try:
                worker_result = analyze_frame_sync(frame, debug_noise=self.debug_noise_test)
                self._log_event(logging.INFO, "emotion_direct_inference_used", frame_id=frame_id)
            except Exception as exc:
                logger.exception(
                    "emotion_direct_inference_failed",
                    extra={
                        "correlation_id": self.correlation_id,
                        "assessment_id": self.assessment_id,
                        "frame_id": frame_id,
                        "reason": str(exc),
                    },
                )
                return self._fallback_result("direct_inference_failed", {"error": str(exc)})
        else:
            try:
                worker = get_inference_worker(self.inference_max_memory_mb)
            except Exception as exc:
                logger.exception(
                    "emotion_worker_start_failed",
                    extra={
                        "correlation_id": self.correlation_id,
                        "assessment_id": self.assessment_id,
                        "frame_id": frame_id,
                        "reason": str(exc),
                    },
                )
                return self._fallback_result("worker_start_failed", {"error": str(exc)})
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
                self._log_event(logging.WARNING, "emotion_worker_queue_full", frame_id=frame_id)
                return self._error_result("worker_queue_full", {"reason": "inference_backpressure"})

            worker_result = await asyncio.to_thread(worker.wait_for, request_id, self.inference_timeout)
            if worker_result is None:
                await asyncio.to_thread(worker.register_timeout, self.inference_restart_threshold)
                self._log_event(logging.WARNING, "emotion_inference_timeout", frame_id=frame_id)
                return self._error_result("timeout", {"reason": "inference_timeout"})

            if worker_result.get("status") != WORKER_STATUS_OK:
                worker_error = str(worker_result.get("error", "worker_error"))[:200]
                self._log_event(logging.ERROR, "emotion_worker_result_error", frame_id=frame_id, worker_error=worker_result.get("error"))
                return self._fallback_result("worker_error", {"reason": worker_error})
            await asyncio.to_thread(worker.register_success)

        faces = worker_result.get("faces") or []
        self._log_event(
            logging.INFO,
            "emotion_worker_debug",
            frame_id=frame_id,
            frame_hash=worker_result.get("frame_hash"),
            processed_hash=worker_result.get("processed_hash"),
            pixel_sum_before=worker_result.get("pixel_sum_before"),
            pixel_sum_after=worker_result.get("pixel_sum_after"),
            detector_backend=worker_result.get("detector_backend"),
            align=worker_result.get("align"),
            used_preprocessed_frame=worker_result.get("used_preprocessed_frame"),
            debug_only=True,
        )
        self._log_event(
            logging.INFO,
            "emotion_deepface_raw_result",
            frame_id=frame_id,
            raw_emotion=(faces[0].get("emotion", {}) if faces and isinstance(faces[0], dict) else {}),
            debug_only=True,
        )
        if not faces:
            self._reset_realtime_diagnostics()
            payload = {"status": STATUS_QUALITY_LOW, "dominant_emotion": "uncertain", "emotion_scores": {"uncertain": 100.0}, "confidence": 0.1, "message": "no_face_detected"}
            if quality_warning:
                payload["details"] = quality_warning
            return self._normalize_result_payload(payload)

        best_face = self._pick_subject_face(faces)
        if best_face is None:
            self._reset_realtime_diagnostics()
            payload = {"status": STATUS_QUALITY_LOW, "dominant_emotion": "uncertain", "emotion_scores": {"uncertain": 100.0}, "confidence": 0.1, "message": "subject_tracking_lost"}
            if quality_warning:
                payload["details"] = quality_warning
            return self._normalize_result_payload(payload)
        confidence = self._face_conf(best_face)
        face_box = self._face_box(best_face)
        if face_box is not None:
            x1, y1, x2, y2 = face_box
            face_area = max(0, x2 - x1) * max(0, y2 - y1)
            frame_area = max(1, h * w)
            face_area_ratio = face_area / frame_area
            face_width = max(0, x2 - x1)
            face_height = max(0, y2 - y1)
            print("Face region:", face_width, "x", face_height, "Face confidence:", confidence)
            self._log_event(
                logging.INFO,
                "emotion_face_detected",
                frame_id=frame_id,
                face_width=face_width,
                face_height=face_height,
                face_confidence=round(confidence, 4),
                face_area_ratio=round(face_area_ratio, 4),
            )
            if face_area_ratio < self.min_face_area_ratio:
                self._reset_realtime_diagnostics()
                return self._normalize_result_payload(
                    {
                        "status": STATUS_QUALITY_LOW,
                        "dominant_emotion": "uncertain",
                        "emotion_scores": {"uncertain": 100.0},
                        "confidence": confidence if confidence is not None else 0.1,
                        "message": "face_area_too_small",
                        "details": {
                            "face_area_ratio": round(face_area_ratio, 4),
                            "min_face_area_ratio": self.min_face_area_ratio,
                        },
                    }
                )
        result = self._build_emotion_decision(
            raw_scores=best_face.get("emotion", {}) or {},
            confidence=confidence,
            quality_warning=quality_warning,
            frame_id=frame_id,
            frame_hash=frame_hash,
        )
        if self._scores_look_stuck(frame_hash, result.get("emotion_scores", {})):
            self._log_event(
                logging.ERROR,
                "emotion_identical_scores_detected",
                frame_id=frame_id,
                frame_hash=frame_hash,
                emotion_scores=result.get("emotion_scores", {}),
            )
            try:
                redetect_result = analyze_frame_sync(frame, prefer_alternate=True, debug_noise=True)
                alt_faces = redetect_result.get("faces") or []
                alt_face = self._pick_subject_face(alt_faces)
                if alt_face is not None:
                    result = self._build_emotion_decision(
                        raw_scores=alt_face.get("emotion", {}) or {},
                        confidence=self._face_conf(alt_face),
                        quality_warning=quality_warning,
                        frame_id=frame_id,
                        frame_hash=f"{frame_hash}:redetect",
                    )
                    result.setdefault("details", {})
                    result["details"]["forced_redetect"] = True
            except Exception as exc:
                self._log_event(
                    logging.ERROR,
                    "emotion_forced_redetect_failed",
                    frame_id=frame_id,
                    frame_hash=frame_hash,
                    error=str(exc),
                )
        return result

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
        payload = {
            "status": STATUS_ERROR,
            "message": message,
            "dominant_emotion": "neutral",
            "emotion_scores": {"neutral": 0.1},
            "confidence": 0.1,
        }
        if details:
            payload["details"] = details
        return self._normalize_result_payload(payload)

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

    def _clean_emotion_scores(self, raw_scores: Dict[str, Any]) -> Dict[str, float]:
        emotion_scores: Dict[str, float] = {}
        for key, value in (raw_scores or {}).items():
            try:
                score = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
            label = str(key or "").strip().lower()
            if label:
                emotion_scores[label] = score
        return emotion_scores

    def _normalize_percentage_scores(self, emotion_scores: Dict[str, float]) -> Dict[str, float]:
        if not emotion_scores:
            return {}
        total = float(sum(max(0.0, value) for value in emotion_scores.values()))
        if total <= 1e-6:
            return {}
        return {
            emotion: round((max(0.0, value) / total) * 100.0, 2)
            for emotion, value in emotion_scores.items()
        }

    def _apply_angry_bias_guard(self, emotion_scores: Dict[str, float]) -> Tuple[Dict[str, float], bool]:
        guarded_scores = dict(emotion_scores)
        angry_score = float(guarded_scores.get("angry", 0.0))
        if angry_score <= 0.0:
            return guarded_scores, False
        is_angry_top = angry_score >= max(guarded_scores.values())
        if is_angry_top and angry_score < self.angry_suppression_threshold:
            guarded_scores["angry"] = 0.0
            return guarded_scores, True
        return guarded_scores, False

    def _top_emotions(self, emotion_scores: Dict[str, float], limit: int = 3):
        return sorted(emotion_scores.items(), key=lambda item: item[1], reverse=True)[:limit]

    def _reset_realtime_diagnostics(self) -> None:
        self.recent_frame_hashes.clear()
        self.recent_result_signatures.clear()

    def _emotion_signature(self, emotion_scores: Dict[str, float]) -> Tuple[Tuple[str, float], ...]:
        return tuple(sorted((emotion, round(float(score), 2)) for emotion, score in emotion_scores.items()))

    def _scores_look_stuck(self, frame_hash: str, emotion_scores: Dict[str, float]) -> bool:
        signature = self._emotion_signature(emotion_scores)
        self.recent_frame_hashes.append(frame_hash)
        self.recent_result_signatures.append(signature)
        if len(self.recent_result_signatures) < self.identical_result_window:
            return False
        all_same_scores = len(set(self.recent_result_signatures)) == 1
        has_frame_variation = len(set(self.recent_frame_hashes)) > 1
        return all_same_scores and has_frame_variation

    def _build_emotion_decision(
        self,
        *,
        raw_scores: Dict[str, Any],
        confidence: float,
        quality_warning: Optional[Dict[str, Any]],
        frame_id: str,
        frame_hash: str,
    ) -> Dict[str, Any]:
        raw_clean_scores = self._clean_emotion_scores(raw_scores)
        raw_normalized_scores = self._normalize_percentage_scores(raw_clean_scores)
        print("DeepFace raw emotion:", raw_normalized_scores)
        self._log_event(
            logging.INFO,
            "emotion_top_three_raw",
            frame_id=frame_id,
            top_three=self._top_emotions(raw_normalized_scores),
        )

        if not raw_normalized_scores:
            return self._fallback_result(
                "emotion_scores_missing",
                {"face_confidence": confidence},
            )

        guarded_scores, angry_suppressed = self._apply_angry_bias_guard(raw_normalized_scores)
        final_scores = self._normalize_percentage_scores(guarded_scores)
        top_three = self._top_emotions(final_scores)
        self._log_event(logging.INFO, "emotion_top_three", frame_id=frame_id, top_three=top_three)

        dominant_emotion = top_three[0][0] if top_three else ""
        top_emotion_score = top_three[0][1] if top_three else 0.0
        print("DeepFace dominant_emotion:", dominant_emotion or "unknown")

        if not dominant_emotion:
            return self._fallback_result(
                "dominant_emotion_missing",
                {
                    "raw_scores": raw_normalized_scores,
                    "face_confidence": confidence,
                },
            )

        details: Dict[str, Any] = {}
        if quality_warning:
            details.update(quality_warning)
        if angry_suppressed:
            details["angry_suppressed"] = True
            details["angry_suppression_threshold"] = self.angry_suppression_threshold
        details["raw_top_three"] = self._top_emotions(raw_normalized_scores)
        details["final_top_three"] = top_three
        details["frame_hash"] = frame_hash

        if top_emotion_score < self.uncertain_threshold:
            return self._normalize_result_payload(
                {
                    "status": STATUS_UNCERTAIN,
                    "dominant_emotion": dominant_emotion,
                    "emotion_scores": final_scores,
                    "confidence": confidence,
                    "message": "top_emotion_below_threshold",
                    "details": {
                        **details,
                        "top_emotion_score": round(top_emotion_score, 2),
                        "threshold": self.uncertain_threshold,
                    },
                }
            )

        status = STATUS_OK if confidence >= self.min_face_confidence else STATUS_QUALITY_LOW
        if confidence < self.min_face_confidence:
            status = STATUS_OK
        return self._normalize_result_payload(
            {
                "status": status,
                "dominant_emotion": dominant_emotion,
                "emotion_scores": final_scores,
                "confidence": confidence,
                "details": details,
            }
        )

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
        if not faces:
            return None
        if len(faces) == 1:
            return faces[0]
        best = None
        best_score = -1.0
        for face in faces:
            box = self._face_box(face)
            area = 0
            if box:
                x1, y1, x2, y2 = box
                area = max(0, x2 - x1) * max(0, y2 - y1)
            score = self._face_conf(face) * 1000000.0 + float(area)
            if score > best_score:
                best_score = score
                best = face
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
    def _start_scale_session(self):
        from .models import Assessment, ScaleEmotionSession

        assessment = Assessment.objects.filter(id=self.assessment_id).first()
        if not assessment:
            return
        ScaleEmotionSession.objects.create(
            assessment=assessment,
            scale=self.scale,
        )

    @database_sync_to_async
    def _finish_scale_session(self):
        from .models import Assessment

        assessment = Assessment.objects.filter(id=self.assessment_id).first()
        if not assessment:
            return
        session = finalize_scale_emotion_session(assessment, self.scale)
        if not session:
            return
        session.ended_at = timezone.now()
        session.save(
            update_fields=[
                "ended_at",
                "total_frames",
                "overall_dominant_emotion",
                "distress_ratio",
            ]
        )

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
        scale: str,
        question_id: Optional[int],
        frame_id: str,
        frame_number: Optional[int],
        timestamp_sec: Optional[float],
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
        normalized = self._normalize_result_payload(
            {
                "dominant_emotion": dominant_emotion,
                "emotion_scores": emotion_scores,
                "confidence": confidence,
                "status": status,
            }
        )
        logger.warning(
            "emotion_record_save_payload",
            extra={
                "correlation_id": self.correlation_id,
                "assessment_id": assessment_id,
                "frame_id": frame_id,
                "frame_number": frame_number,
                "timestamp_sec": timestamp_sec,
                "dominant_emotion": normalized["dominant_emotion"],
                "status": normalized["status"],
                "worker_result": {
                    "dominant_emotion": normalized["dominant_emotion"],
                    "emotion_scores": normalized["emotion_scores"],
                    "confidence": normalized["confidence"],
                    "status": normalized["status"],
                },
            },
        )
        print("Frame:", frame_id, "Emotion:", normalized["dominant_emotion"])
        EmotionRecord.objects.create(
            assessment=assessment,
            scale=scale,
            question=question,
            frame_id=frame_id,
            frame_number=frame_number,
            timestamp_sec=timestamp_sec,
            dominant_emotion=normalized["dominant_emotion"],
            emotion_scores=normalized["emotion_scores"],
            confidence=normalized["confidence"],
            status=normalized["status"],
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

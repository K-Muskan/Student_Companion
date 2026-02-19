import asyncio
import base64
import binascii
import logging
import time
from typing import Any, Dict, Optional

import cv2
import numpy as np
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils.dateparse import parse_datetime

from .models import Assessment, EmotionRecord, Question

logger = logging.getLogger(__name__)
DeepFace = None


def _get_deepface():
    global DeepFace
    if DeepFace is None:
        from deepface import DeepFace as DeepFaceModule
        DeepFace = DeepFaceModule
    return DeepFace


class EmotionStreamConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.assessment_id = int(self.scope["url_route"]["kwargs"]["assessment_id"])
        self.analysis_interval = float(getattr(settings, "EMOTION_ANALYZE_INTERVAL_SECONDS", 1.0))
        self.max_image_bytes = int(getattr(settings, "EMOTION_MAX_IMAGE_BYTES", 1500000))
        self.last_analyzed_at = 0.0
        self.processing = False

        allowed = await self._can_access_assessment(self.assessment_id)
        if not allowed:
            await self.close(code=4403)
            return

        await self.accept()
        await self.send_json(
            {
                "type": "connection",
                "status": "connected",
                "assessment_id": self.assessment_id,
                "analysis_interval_seconds": self.analysis_interval,
            }
        )

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        if content.get("type") != "frame":
            await self.send_json({"type": "error", "message": "Unsupported message type"})
            return

        payload_assessment_id = int(content.get("assessment_id", -1))
        if payload_assessment_id != self.assessment_id:
            await self.send_json({"type": "error", "message": "assessment_id mismatch"})
            return

        image_base64 = content.get("image_base64")
        question_id = content.get("question_id")
        client_ts_raw = content.get("client_ts")

        if not image_base64:
            await self.send_json({"type": "error", "message": "image_base64 missing"})
            return

        now = time.monotonic()
        if self.processing:
            await self.send_json({"type": "frame_result", "status": "dropped", "reason": "busy"})
            return

        if now - self.last_analyzed_at < self.analysis_interval:
            await self.send_json({"type": "frame_result", "status": "dropped", "reason": "throttled"})
            return

        self.processing = True
        self.last_analyzed_at = now

        try:
            result = await asyncio.to_thread(self._analyze_frame, image_base64)
            await self._save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion=result.get("dominant_emotion", ""),
                emotion_scores=result.get("emotion_scores", {}),
                confidence=result.get("confidence"),
                status=result.get("status", EmotionRecord.STATUS_ERROR),
                client_ts_raw=client_ts_raw,
            )
            await self.send_json(
                {
                    "type": "frame_result",
                    "status": result.get("status"),
                    "dominant_emotion": result.get("dominant_emotion", ""),
                    "emotion_scores": result.get("emotion_scores", {}),
                    "confidence": result.get("confidence"),
                }
            )
        except Exception as exc:
            logger.exception("Emotion analysis failed: %s", exc)
            await self._save_record(
                assessment_id=self.assessment_id,
                question_id=question_id,
                dominant_emotion="",
                emotion_scores={},
                confidence=None,
                status=EmotionRecord.STATUS_ERROR,
                client_ts_raw=client_ts_raw,
            )
            await self.send_json(
                {
                    "type": "frame_result",
                    "status": EmotionRecord.STATUS_ERROR,
                    "message": "analysis_failed",
                }
            )
        finally:
            self.processing = False

    async def disconnect(self, close_code):
        logger.info(
            "Emotion websocket disconnected: assessment=%s code=%s",
            self.assessment_id,
            close_code,
        )

    def _analyze_frame(self, image_base64: str) -> Dict[str, Any]:
        image_bytes = self._decode_base64_image(image_base64)
        if len(image_bytes) > self.max_image_bytes:
            return {
                "status": EmotionRecord.STATUS_ERROR,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": None,
            }

        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {
                "status": EmotionRecord.STATUS_ERROR,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": None,
            }

        try:
            deepface = _get_deepface()
        except Exception as import_err:
            logger.exception("DeepFace import failed: %s", import_err)
            return {
                "status": EmotionRecord.STATUS_ERROR,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": None,
            }

        analysis = deepface.analyze(
            img_path=frame,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend="opencv",
        )

        faces = analysis if isinstance(analysis, list) else [analysis]
        if not faces:
            return {
                "status": EmotionRecord.STATUS_NO_FACE,
                "dominant_emotion": "",
                "emotion_scores": {},
                "confidence": None,
            }

        def face_conf(face: Dict[str, Any]) -> float:
            value = face.get("face_confidence")
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        best_face = max(faces, key=face_conf)
        dominant_emotion = str(best_face.get("dominant_emotion", "") or "")
        raw_scores = best_face.get("emotion", {}) or {}

        emotion_scores = {}
        for key, value in raw_scores.items():
            try:
                emotion_scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

        if not dominant_emotion:
            return {
                "status": EmotionRecord.STATUS_NO_FACE,
                "dominant_emotion": "",
                "emotion_scores": emotion_scores,
                "confidence": None,
            }

        confidence = face_conf(best_face)
        return {
            "status": EmotionRecord.STATUS_OK,
            "dominant_emotion": dominant_emotion,
            "emotion_scores": emotion_scores,
            "confidence": confidence,
        }

    def _decode_base64_image(self, image_base64: str) -> bytes:
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        try:
            return base64.b64decode(image_base64, validate=True)
        except binascii.Error:
            return base64.b64decode(image_base64)

    @database_sync_to_async
    def _can_access_assessment(self, assessment_id: int) -> bool:
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
        assessment = Assessment.objects.get(id=assessment_id)

        question = None
        if question_id is not None:
            question = Question.objects.filter(id=question_id).first()

        client_ts = None
        if client_ts_raw:
            client_ts = parse_datetime(client_ts_raw)

        EmotionRecord.objects.create(
            assessment=assessment,
            question=question,
            dominant_emotion=dominant_emotion,
            emotion_scores=emotion_scores,
            confidence=confidence,
            status=status,
            client_ts=client_ts,
        )

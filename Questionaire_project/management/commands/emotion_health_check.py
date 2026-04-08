import json
import uuid

import cv2
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction

from Questionaire_project.emotion_worker import EmotionInferenceWorker, check_deepface_import
from Questionaire_project.models import Assessment, EmotionRecord


class Command(BaseCommand):
    help = "Runs a full emotion pipeline health check: import, inference, and DB write."

    def handle(self, *args, **options):
        status = {"deepface_import": False, "inference": False, "db_write": False}
        reasons = []

        import_error = check_deepface_import(raise_on_error=False)
        if import_error:
            reasons.append(f"DeepFace import failed: {import_error}")
            self._print_result(False, reasons, status)
            return
        status["deepface_import"] = True

        worker = EmotionInferenceWorker(max_memory_mb=1024)
        request_id = uuid.uuid4().hex
        try:
            frame = np.full((224, 224, 3), 220, dtype=np.uint8)
            cv2.circle(frame, (112, 112), 60, (40, 40, 40), 3)
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                reasons.append("Failed to encode test frame.")
                self._print_result(False, reasons, status)
                return

            queued = worker.submit({"type": "frame", "request_id": request_id, "frame_id": "health-check", "image_bytes": encoded.tobytes()})
            if not queued:
                reasons.append("Worker queue rejected the health-check frame.")
                self._print_result(False, reasons, status)
                return
            result = worker.wait_for(request_id, 15.0)
            if result is None:
                reasons.append("Inference timed out.")
                self._print_result(False, reasons, status)
                return
            if result.get("status") != "ok":
                reasons.append(f"Inference failed: {result.get('error') or result}")
                self._print_result(False, reasons, status)
                return
            status["inference"] = True
        finally:
            worker.stop()

        record_id = None
        try:
            with transaction.atomic():
                assessment = Assessment.objects.create(
                    session_key="emotion-health-check",
                    assessment_token=f"emotion-health-check:{uuid.uuid4().hex}",
                )
                record = EmotionRecord.objects.create(
                    assessment=assessment,
                    scale="anxiety",
                    frame_id=f"health-{uuid.uuid4().hex[:12]}",
                    dominant_emotion="neutral",
                    emotion_scores={"neutral": 0.1},
                    confidence=0.1,
                    status=EmotionRecord.STATUS_FALLBACK,
                )
                record_id = record.id
            status["db_write"] = True
        except Exception as exc:
            reasons.append(f"DB write failed: {exc}")

        ok = all(status.values())
        if ok:
            self.stdout.write(self.style.SUCCESS("OK emotion health check passed"))
        else:
            self.stdout.write(self.style.ERROR("FAIL emotion health check failed"))
        self.stdout.write(json.dumps({"status": status, "record_id": record_id, "reasons": reasons}, indent=2))

    def _print_result(self, ok: bool, reasons, status):
        if ok:
            self.stdout.write(self.style.SUCCESS("OK emotion health check passed"))
        else:
            self.stdout.write(self.style.ERROR("FAIL emotion health check failed"))
        self.stdout.write(json.dumps({"status": status, "reasons": reasons}, indent=2))

import json
import uuid
from pathlib import Path
from typing import Callable, Dict, Tuple
from unittest import mock

import cv2
import numpy as np
from django.core.management.base import BaseCommand, CommandError

from Questionaire_project.emotion_worker import EmotionInferenceWorker, check_deepface_import


class Command(BaseCommand):
    help = "Runs emotion worker smoke tests and prints PASS/FAIL for each scenario."

    def add_arguments(self, parser):
        parser.add_argument("--image", type=str, help="Optional image path for the normal inference scenario.")
        parser.add_argument("--timeout", type=float, default=10.0, help="Seconds to wait for worker results.")
        parser.add_argument("--max-memory-mb", type=int, default=1024, help="Memory limit passed to the worker process.")

    def handle(self, *args, **options):
        import_error = check_deepface_import(raise_on_error=False)
        if import_error:
            raise CommandError(f"DeepFace import failed: {import_error}")

        scenarios: Tuple[Tuple[str, Callable[[dict], Dict[str, object]]], ...] = (
            ("normal_inference", self._scenario_normal),
            ("fallback_mode", self._scenario_fallback),
            ("invalid_image", self._scenario_invalid_image),
            ("timeout_mode", self._scenario_timeout),
        )

        all_passed = True
        for name, scenario in scenarios:
            try:
                result = scenario(options)
                self.stdout.write(self.style.SUCCESS(f"PASS {name}"))
                self.stdout.write(json.dumps(result, indent=2, default=str))
            except Exception as exc:
                all_passed = False
                self.stdout.write(self.style.ERROR(f"FAIL {name}: {exc}"))

        if not all_passed:
            raise CommandError("One or more emotion worker scenarios failed.")

    def _scenario_normal(self, options):
        image_bytes, frame_meta = self._build_test_frame(options.get("image"))
        return self._submit_and_wait(
            image_bytes=image_bytes,
            timeout=float(options["timeout"]),
            max_memory_mb=int(options["max_memory_mb"]),
            frame_id="normal-inference",
            extra={"frame_meta": frame_meta},
        )

    def _scenario_fallback(self, options):
        image_bytes, _ = self._build_test_frame(options.get("image"))
        worker = EmotionInferenceWorker(max_memory_mb=int(options["max_memory_mb"]))
        request_id = uuid.uuid4().hex
        try:
            with mock.patch.object(worker, "ensure_running", return_value=None), mock.patch.object(worker, "_local_mode", True), mock.patch.object(worker, "_local_deepface", object()), mock.patch(
                "Questionaire_project.emotion_worker._analyze_image_bytes",
                side_effect=RuntimeError("forced_fallback_path"),
            ):
                queued = worker.submit({"type": "frame", "request_id": request_id, "frame_id": "fallback-mode", "image_bytes": image_bytes})
                if not queued:
                    raise RuntimeError("Worker queue rejected fallback scenario.")
                result = worker.wait_for(request_id, float(options["timeout"]))
        finally:
            worker.stop()
        if result is None or result.get("status") != "error":
            raise RuntimeError(f"Expected error result for fallback scenario, got: {result}")
        return result

    def _scenario_invalid_image(self, options):
        result = self._submit_and_wait(
            image_bytes=b"this-is-not-a-jpeg",
            timeout=float(options["timeout"]),
            max_memory_mb=int(options["max_memory_mb"]),
            frame_id="invalid-image",
        )
        if result.get("error") != "decode_failed":
            raise RuntimeError(f"Expected decode_failed, got: {result}")
        return result

    def _scenario_timeout(self, options):
        image_bytes, _ = self._build_test_frame(options.get("image"))
        worker = EmotionInferenceWorker(max_memory_mb=int(options["max_memory_mb"]))
        request_id = uuid.uuid4().hex
        try:
            with mock.patch.object(worker, "ensure_running", return_value=None), mock.patch.object(worker, "submit", return_value=True):
                result = worker.wait_for(request_id, 0.01)
        finally:
            worker.stop()
        if result is not None:
            raise RuntimeError(f"Expected timeout None result, got: {result}")
        return {"status": "timeout", "request_id": request_id}

    def _submit_and_wait(self, *, image_bytes: bytes, timeout: float, max_memory_mb: int, frame_id: str, extra: Dict[str, object] | None = None):
        worker = EmotionInferenceWorker(max_memory_mb=max_memory_mb)
        request_id = uuid.uuid4().hex
        try:
            queued = worker.submit(
                {
                    "type": "frame",
                    "request_id": request_id,
                    "frame_id": frame_id,
                    "image_bytes": image_bytes,
                }
            )
            if not queued:
                raise RuntimeError("Worker queue rejected the test frame.")
            result = worker.wait_for(request_id, timeout)
            if result is None:
                raise RuntimeError("Timed out waiting for worker result.")
            if extra:
                result = {**extra, **result}
            return result
        finally:
            worker.stop()

    def _build_test_frame(self, image_path: str | None):
        if image_path:
            resolved = Path(image_path).expanduser()
            if not resolved.is_file():
                raise CommandError(f"Image not found: {resolved}")
            frame = cv2.imread(str(resolved), cv2.IMREAD_COLOR)
            if frame is None:
                raise CommandError(f"Unable to decode image: {resolved}")
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise CommandError(f"Unable to JPEG-encode image: {resolved}")
            height, width = frame.shape[:2]
            return encoded.tobytes(), {"source": str(resolved), "height": int(height), "width": int(width)}

        frame = np.full((224, 224, 3), 240, dtype=np.uint8)
        cv2.circle(frame, (112, 112), 70, (180, 180, 180), 3)
        cv2.circle(frame, (85, 95), 10, (50, 50, 50), -1)
        cv2.circle(frame, (139, 95), 10, (50, 50, 50), -1)
        cv2.ellipse(frame, (112, 142), (30, 16), 0, 10, 170, (60, 60, 60), 3)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise CommandError("Unable to JPEG-encode synthetic test frame.")
        return encoded.tobytes(), {"source": "synthetic-face-like-frame", "height": 224, "width": 224}

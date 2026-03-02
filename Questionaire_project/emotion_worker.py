import logging
import multiprocessing as mp
import os
import queue
import threading
import time
from typing import Any, Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_ERROR = "error"


def _set_process_memory_limit(max_mb: int):
    if max_mb <= 0:
        return
    try:
        import resource  # type: ignore
    except Exception:
        return
    bytes_limit = int(max_mb) * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
    except Exception:
        return


def _worker_main(input_queue: "mp.Queue", output_queue: "mp.Queue", max_memory_mb: int):
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    try:
        import warnings

        warnings.filterwarnings("ignore", message=".*sparse_softmax_cross_entropy.*")
    except Exception:
        pass

    _set_process_memory_limit(max_memory_mb)
    deepface = None
    deepface_error = None
    try:
        from deepface import DeepFace as DeepFaceModule

        deepface = DeepFaceModule
    except Exception as exc:
        deepface_error = str(exc)

    while True:
        try:
            task = input_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        except Exception:
            continue

        if not isinstance(task, dict):
            continue
        if task.get("type") == "shutdown":
            return

        request_id = task.get("request_id")
        image_bytes = task.get("image_bytes")
        if not request_id:
            continue
        if deepface is None:
            output_queue.put({"request_id": request_id, "status": STATUS_ERROR, "error": deepface_error or "deepface_import_failed"})
            continue
        if not isinstance(image_bytes, (bytes, bytearray)):
            output_queue.put({"request_id": request_id, "status": STATUS_ERROR, "error": "invalid_image_bytes"})
            continue

        try:
            np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                output_queue.put({"request_id": request_id, "status": STATUS_ERROR, "error": "decode_failed"})
                continue

            analysis = deepface.analyze(
                img_path=frame,
                actions=["emotion"],
                enforce_detection=False,
                detector_backend="opencv",
            )
            faces = analysis if isinstance(analysis, list) else [analysis]
            output_queue.put({"request_id": request_id, "status": STATUS_OK, "faces": faces})
        except Exception as exc:
            output_queue.put({"request_id": request_id, "status": STATUS_ERROR, "error": str(exc)})


class EmotionInferenceWorker:
    def __init__(self, max_memory_mb: int = 512):
        self.max_memory_mb = int(max_memory_mb)
        self.ctx = mp.get_context("spawn")
        self.input_queue: Optional[mp.Queue] = None
        self.output_queue: Optional[mp.Queue] = None
        self.process: Optional[mp.Process] = None
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._timeout_failures = 0
        self._crash_failures = 0

    def ensure_running(self):
        if self.process is not None and self.process.is_alive():
            return
        self.restart()

    def restart(self):
        self.stop()
        self.input_queue = self.ctx.Queue(maxsize=32)
        self.output_queue = self.ctx.Queue(maxsize=32)
        self.process = self.ctx.Process(target=_worker_main, args=(self.input_queue, self.output_queue, self.max_memory_mb))
        self.process.daemon = True
        self.process.start()
        with self._lock:
            self._pending = {}
            self._timeout_failures = 0
            self._crash_failures = 0

    def stop(self):
        if self.input_queue is not None:
            try:
                self.input_queue.put_nowait({"type": "shutdown"})
            except Exception:
                pass
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1.0)
        self.process = None
        self.input_queue = None
        self.output_queue = None

    def submit(self, payload: Dict[str, Any]) -> bool:
        self.ensure_running()
        if self.input_queue is None:
            return False
        try:
            self.input_queue.put(payload, timeout=0.05)
            return True
        except Exception:
            return False

    def _read_output_once(self, timeout: float):
        if self.output_queue is None:
            return
        try:
            item = self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return
        except Exception:
            return
        if isinstance(item, dict):
            req = item.get("request_id")
            if req:
                with self._lock:
                    self._pending[str(req)] = item

    def wait_for(self, request_id: str, timeout: float) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + max(0.01, timeout)
        while time.monotonic() < deadline:
            with self._lock:
                existing = self._pending.pop(request_id, None)
                if existing is not None:
                    return existing
            self._read_output_once(timeout=min(0.15, max(0.01, deadline - time.monotonic())))

            if self.process is not None and not self.process.is_alive():
                with self._lock:
                    self._crash_failures += 1
                return {"request_id": request_id, "status": STATUS_ERROR, "error": "worker_crashed"}
        return None

    def register_timeout(self, restart_threshold: int):
        with self._lock:
            self._timeout_failures += 1
            failures = self._timeout_failures
        if failures >= max(1, int(restart_threshold)):
            logger.warning("emotion_worker_restart_timeout_threshold", extra={"failures": failures})
            self.restart()

    def register_crash(self, restart_threshold: int):
        with self._lock:
            self._crash_failures += 1
            failures = self._crash_failures
        if failures >= max(1, int(restart_threshold)):
            logger.warning("emotion_worker_restart_crash_threshold", extra={"failures": failures})
            self.restart()

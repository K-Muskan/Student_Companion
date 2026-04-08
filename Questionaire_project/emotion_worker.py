import logging
import multiprocessing as mp
import os
import platform
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)
_DEEPFACE_MODULE_CACHE: Any = None

STATUS_OK = "ok"
STATUS_ERROR = "error"
DEFAULT_TARGET_FRAME_SIZE = (224, 224)
ANALYZE_CONFIGS = (
    {"detector_backend": "retinaface", "align": True, "use_preprocessed": False},
    {"detector_backend": "opencv", "align": True, "use_preprocessed": False},
    {"detector_backend": "retinaface", "align": True, "use_preprocessed": True},
    {"detector_backend": "opencv", "align": True, "use_preprocessed": True},
)


def _worker_log(level: int, event: str, **extra: Any) -> None:
    payload = {"correlation_id": extra.pop("correlation_id", None), "assessment_id": extra.pop("assessment_id", None), "frame_id": extra.pop("frame_id", None)}
    payload.update(extra)
    logger.log(level, event, extra=payload)


def check_deepface_import(raise_on_error: bool = False) -> Optional[str]:
    try:
        deepface_module = get_deepface_module()

        if not hasattr(deepface_module, "analyze"):
            raise ImportError("DeepFace.analyze is not available in the installed package.")
        return None
    except Exception as exc:
        logger.exception("emotion_worker_deepface_import_failed", extra={"correlation_id": None, "assessment_id": None, "frame_id": None})
        error = f"{exc.__class__.__name__}: {exc}"
        if raise_on_error:
            raise RuntimeError(f"DeepFace import failed: {error}") from exc
        return error


def get_deepface_module() -> Any:
    global _DEEPFACE_MODULE_CACHE
    if _DEEPFACE_MODULE_CACHE is None:
        from deepface import DeepFace as DeepFaceModule

        _DEEPFACE_MODULE_CACHE = DeepFaceModule
    return _DEEPFACE_MODULE_CACHE


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


def _normalize_brightness(frame_rgb: np.ndarray, target_mean: float = 128.0) -> np.ndarray:
    if frame_rgb.size == 0:
        return frame_rgb
    hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    value_channel = hsv[:, :, 2].astype(np.float32)
    current_mean = float(np.mean(value_channel))
    if current_mean <= 1e-6:
        return frame_rgb
    scale = max(0.75, min(1.35, target_mean / current_mean))
    hsv[:, :, 2] = np.clip(value_channel * scale, 0, 255).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def _apply_clahe(frame_rgb: np.ndarray, clip_limit: float = 2.0, tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    if frame_rgb.size == 0:
        return frame_rgb
    lab = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    l_channel = clahe.apply(l_channel)
    normalized_lab = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(normalized_lab, cv2.COLOR_LAB2RGB)


def preprocess_frame_for_inference(frame: np.ndarray) -> np.ndarray:
    if not isinstance(frame, np.ndarray):
        raise TypeError("frame must be a numpy array")
    if frame.size == 0:
        raise ValueError("frame is empty")

    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim != 3:
        raise ValueError("frame must have 2 or 3 dimensions")

    # DeepFace expects RGB input; CLAHE on the luminance channel helps reduce
    # harsh lighting swings that otherwise push neutral faces toward angry.
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_rgb = _normalize_brightness(frame_rgb)
    frame_rgb = _apply_clahe(frame_rgb)
    frame_rgb = cv2.resize(frame_rgb, DEFAULT_TARGET_FRAME_SIZE, interpolation=cv2.INTER_AREA)
    return frame_rgb


def _frame_hash(frame: np.ndarray) -> str:
    return str(hash(np.ascontiguousarray(frame).tobytes()))


def _pixel_sum(frame: np.ndarray) -> int:
    return int(np.sum(frame, dtype=np.int64))


def _maybe_apply_debug_noise(frame_rgb: np.ndarray, enabled: bool) -> np.ndarray:
    if not enabled:
        return frame_rgb
    noisy = frame_rgb.copy()
    noise = np.random.randint(-2, 3, size=noisy.shape, dtype=np.int16)
    noisy = np.clip(noisy.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return noisy


def _face_has_emotion(face: Dict[str, Any]) -> bool:
    return isinstance(face, dict) and bool(face.get("emotion"))


def _run_deepface_analysis(
    deepface: Any,
    frame: np.ndarray,
    *,
    prefer_alternate: bool = False,
    debug_noise: bool = False,
) -> Dict[str, Any]:
    pre_pixel_sum = _pixel_sum(frame)
    processed_frame = preprocess_frame_for_inference(frame)
    processed_frame = _maybe_apply_debug_noise(processed_frame, enabled=debug_noise)
    post_pixel_sum = _pixel_sum(processed_frame)
    frame_hash = _frame_hash(frame)
    processed_hash = _frame_hash(processed_frame)
    print("Preprocess pixel sum before:", pre_pixel_sum, "after:", post_pixel_sum)

    configs: List[Dict[str, Any]] = list(ANALYZE_CONFIGS)
    if prefer_alternate:
        configs = configs[2:] + configs[:2]

    errors = []
    for config in configs:
        source_frame = processed_frame if config.get("use_preprocessed") else frame
        analysis_input = np.ascontiguousarray(source_frame.copy())
        try:
            analysis = deepface.analyze(
                img_path=analysis_input,
                actions=["emotion"],
                enforce_detection=False,
                detector_backend=config["detector_backend"],
                align=config["align"],
            )
            faces = analysis if isinstance(analysis, list) else [analysis]
            if any(_face_has_emotion(face) for face in faces):
                return {
                    "status": STATUS_OK,
                    "faces": faces,
                    "frame_hash": frame_hash,
                    "processed_hash": processed_hash,
                    "pixel_sum_before": pre_pixel_sum,
                    "pixel_sum_after": post_pixel_sum,
                    "detector_backend": config["detector_backend"],
                    "align": config["align"],
                    "used_preprocessed_frame": bool(config.get("use_preprocessed")),
                }
        except Exception as exc:
            errors.append(f"{config['detector_backend']} align={config['align']}: {exc}")
            continue

    return {
        "status": STATUS_ERROR,
        "error": "; ".join(errors) if errors else "no_emotion_faces_detected",
        "frame_hash": frame_hash,
        "processed_hash": processed_hash,
        "pixel_sum_before": pre_pixel_sum,
        "pixel_sum_after": post_pixel_sum,
    }


def _analyze_image_bytes(image_bytes: bytes, deepface: Any) -> Dict[str, Any]:
    np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"status": STATUS_ERROR, "error": "decode_failed"}
    return _run_deepface_analysis(deepface, frame)


def analyze_frame_sync(frame: np.ndarray, *, prefer_alternate: bool = False, debug_noise: bool = False) -> Dict[str, Any]:
    if not isinstance(frame, np.ndarray):
        return {"status": STATUS_ERROR, "error": "invalid_frame_type"}
    if frame.size == 0:
        return {"status": STATUS_ERROR, "error": "empty_frame"}

    deepface_error = check_deepface_import(raise_on_error=False)
    if deepface_error:
        return {"status": STATUS_ERROR, "error": deepface_error}

    return _run_deepface_analysis(
        get_deepface_module(),
        frame,
        prefer_alternate=prefer_alternate,
        debug_noise=debug_noise,
    )


def _worker_main(input_queue: "mp.Queue", output_queue: "mp.Queue", max_memory_mb: int):
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    def _safe_put(payload: Dict[str, Any]):
        try:
            output_queue.put(payload, timeout=0.2)
        except Exception:
            return

    try:
        import warnings

        warnings.filterwarnings("ignore", message=".*sparse_softmax_cross_entropy.*")
    except Exception:
        pass

    _set_process_memory_limit(max_memory_mb)
    deepface_error = check_deepface_import(raise_on_error=False)
    if deepface_error:
        _worker_log(logging.ERROR, "emotion_worker_startup_failed", error=deepface_error)
        return

    deepface = get_deepface_module()
    _worker_log(logging.INFO, "emotion_worker_started", mode="process")

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
        correlation_id = task.get("correlation_id")
        assessment_id = task.get("assessment_id")
        frame_id = task.get("frame_id")
        if not request_id:
            continue
        if not isinstance(image_bytes, (bytes, bytearray)):
            _safe_put({"request_id": request_id, "status": STATUS_ERROR, "error": "invalid_image_bytes"})
            continue

        try:
            result = _analyze_image_bytes(bytes(image_bytes), deepface)
            result["request_id"] = request_id
            _safe_put(result)
            _worker_log(
                logging.INFO,
                "emotion_worker_inference_result",
                correlation_id=correlation_id,
                assessment_id=assessment_id,
                frame_id=frame_id,
                status=result.get("status"),
            )
        except Exception as exc:
            _safe_put({"request_id": request_id, "status": STATUS_ERROR, "error": str(exc)})
            _worker_log(
                logging.ERROR,
                "emotion_worker_inference_failed",
                correlation_id=correlation_id,
                assessment_id=assessment_id,
                frame_id=frame_id,
                error=str(exc),
            )


class EmotionInferenceWorker:
    def __init__(self, max_memory_mb: int = 512):
        self.max_memory_mb = int(max_memory_mb)
        self.max_queue_size = 32
        self.ctx = mp.get_context("spawn")
        self.input_queue: Optional[mp.Queue] = None
        self.output_queue: Optional[mp.Queue] = None
        self.process: Optional[mp.Process] = None
        self._local_mode = False
        self._local_deepface: Any = None
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._pending_ts: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._timeout_failures = 0
        self._crash_failures = 0
        self._error_failures = 0

    def ensure_running(self):
        if self.process is not None and self.process.is_alive():
            return
        self.restart()

    def restart(self):
        check_deepface_import(raise_on_error=True)
        self.stop()
        self._local_mode = False
        self._local_deepface = None
        if platform.system().lower() == "windows":
            self.process = None
            self.input_queue = None
            self.output_queue = None
            self._local_mode = True
            self._local_deepface = get_deepface_module()
            _worker_log(logging.WARNING, "emotion_worker_started", mode="local_windows_direct")
            with self._lock:
                self._pending = {}
                self._pending_ts = {}
                self._timeout_failures = 0
                self._crash_failures = 0
                self._error_failures = 0
            return
        try:
            self.input_queue = self.ctx.Queue(maxsize=self.max_queue_size)
            self.output_queue = self.ctx.Queue(maxsize=self.max_queue_size)
            self.process = self.ctx.Process(target=_worker_main, args=(self.input_queue, self.output_queue, self.max_memory_mb))
            self.process.daemon = True
            self.process.start()
            _worker_log(logging.INFO, "emotion_worker_started", mode="process")
        except Exception:
            logger.exception("emotion_worker_spawn_failed_using_local_fallback", extra={"correlation_id": None, "assessment_id": None, "frame_id": None})

            self.process = None
            self.input_queue = None
            self.output_queue = None
            self._local_mode = True
            self._local_deepface = get_deepface_module()
            _worker_log(logging.WARNING, "emotion_worker_started", mode="local_fallback")
        with self._lock:
            self._pending = {}
            self._pending_ts = {}
            self._timeout_failures = 0
            self._crash_failures = 0
            self._error_failures = 0

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
        self._local_mode = False
        self._local_deepface = None

    def submit(self, payload: Dict[str, Any]) -> bool:
        self.ensure_running()
        correlation_id = payload.get("correlation_id")
        assessment_id = payload.get("assessment_id")
        frame_id = payload.get("frame_id")
        if self._local_mode:
            request_id = str(payload.get("request_id") or "")
            image_bytes = payload.get("image_bytes")
            if not request_id:
                return False
            with self._lock:
                pending_count = len(self._pending)
            if pending_count >= self.max_queue_size:
                _worker_log(
                    logging.WARNING,
                    "emotion_worker_queue_rejected",
                    correlation_id=correlation_id,
                    assessment_id=assessment_id,
                    frame_id=frame_id,
                    queue_size=pending_count,
                )
                return False
            if not isinstance(image_bytes, (bytes, bytearray)):
                result = {"request_id": request_id, "status": STATUS_ERROR, "error": "invalid_image_bytes"}
            else:
                try:
                    result = _analyze_image_bytes(bytes(image_bytes), self._local_deepface)
                    result["request_id"] = request_id
                except Exception as exc:
                    result = {"request_id": request_id, "status": STATUS_ERROR, "error": str(exc)}
            with self._lock:
                self._pending[request_id] = result
                self._pending_ts[request_id] = time.monotonic()
            return True
        if self.input_queue is None:
            return False
        try:
            self.input_queue.put(payload, timeout=0.05)
            return True
        except Exception:
            _worker_log(
                logging.WARNING,
                "emotion_worker_queue_rejected",
                correlation_id=correlation_id,
                assessment_id=assessment_id,
                frame_id=frame_id,
            )
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
                    self._pending_ts[str(req)] = time.monotonic()

    def _cleanup_stale_pending(self, max_age_seconds: float):
        now = time.monotonic()
        stale = []
        with self._lock:
            for req, ts in self._pending_ts.items():
                if now - ts > max_age_seconds:
                    stale.append(req)
            for req in stale:
                self._pending.pop(req, None)
                self._pending_ts.pop(req, None)

    def wait_for(self, request_id: str, timeout: float) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + max(0.01, timeout)
        while time.monotonic() < deadline:
            self._cleanup_stale_pending(max_age_seconds=max(5.0, timeout * 3))
            with self._lock:
                existing = self._pending.pop(request_id, None)
                self._pending_ts.pop(request_id, None)
                if existing is not None:
                    return existing
            self._read_output_once(timeout=min(0.15, max(0.01, deadline - time.monotonic())))

            if self.process is not None and not self.process.is_alive():
                with self._lock:
                    self._crash_failures += 1
                _worker_log(logging.ERROR, "emotion_worker_crashed")
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

    def register_error(self, restart_threshold: int):
        with self._lock:
            self._error_failures += 1
            failures = self._error_failures
        if failures >= max(1, int(restart_threshold)):
            logger.warning("emotion_worker_restart_error_threshold", extra={"failures": failures})
            self.restart()

    def register_success(self):
        with self._lock:
            self._timeout_failures = 0
            self._crash_failures = 0
            self._error_failures = 0

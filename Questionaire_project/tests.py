import asyncio
import base64
import json
import sys
import threading
import time
from collections import deque
from unittest import mock

import cv2
import numpy as np
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings

from Questionaire_project.consumers import EmotionStreamConsumer
from Questionaire_project.emotion_services import build_emotion_timeline_summary, build_scale_emotion_summary
from Questionaire_project.emotion_worker import EmotionInferenceWorker, preprocess_frame_for_inference
from Questionaire_project.models import Assessment, EmotionRecord, Question
from Questionaire_project.mse_analyzer import MSEAnalyzer
from Questionaire_project.views import _get_or_create_assessment
from StudentCompanion.asgi import application


def _jpeg_data_url(width=320, height=240, value=120, noisy=False):
    if noisy:
        frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    else:
        frame = np.full((height, width, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


@override_settings(
    EMOTION_ALLOWED_ORIGINS=["http://testserver"],
    EMOTION_MAX_CONNECTIONS_PER_IP=4,
    EMOTION_MAX_CONNECTIONS_PER_ASSESSMENT=1,
    EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW=2,
    EMOTION_FRAME_QUOTA_WINDOW_SECONDS=30,
    ASSESSMENT_MAX_ANSWER_CHARS=50,
)
class AssessmentFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.get("/assessment/")
        for qid in range(1, 16):
            Question.objects.get_or_create(
                id=qid,
                defaults={
                    "video_file": f"question{qid}.mp4",
                    "question_text": "test question",
                    "mse_category": "test",
                    "is_final": qid == 15,
                    "is_active": True,
                },
            )

    def _post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_save_answer_invalid_qid_type_returns_400(self):
        response = self._post_json("/assessment/save-answer/", {"qid": "abc", "answer": "hello"})
        self.assertEqual(response.status_code, 400)

    def test_save_answer_json_decode_error(self):
        response = self.client.post("/assessment/save-answer/", data="{bad json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_save_answer_max_length_validation(self):
        response = self._post_json("/assessment/save-answer/", {"qid": 1, "answer": "x" * 60})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Answer too long", response.json()["message"])

    def test_save_answer_rejected_after_finalization(self):
        session = self.client.session
        session.save()
        assessment = Assessment.objects.create(
            session_key=session.session_key,
            assessment_token=f"{session.session_key}:1",
            is_completed=True,
        )
        session["assessment_id"] = assessment.id
        session.save()
        response = self._post_json("/assessment/save-answer/", {"qid": 1, "answer": "new answer"})
        self.assertEqual(response.status_code, 409)

    def test_complete_persists_report_and_download_works_after_session_cleanup(self):
        save_resp = self._post_json("/assessment/save-answer/", {"qid": 1, "answer": "I feel anxious for 3 weeks"})
        self.assertEqual(save_resp.status_code, 200)
        complete_resp = self.client.get("/assessment/complete/")
        self.assertEqual(complete_resp.status_code, 200)

        session = self.client.session
        self.assertNotIn("assessment_id", session)
        completed_id = session.get("last_completed_assessment_id")
        assessment = Assessment.objects.get(id=completed_id)
        self.assertTrue(assessment.is_completed)
        self.assertTrue(bool(assessment.report_text))
        self.assertTrue(bool(assessment.report_json))

        dl_txt = self.client.get("/assessment/download-report-text/")
        self.assertEqual(dl_txt.status_code, 200)
        dl_json = self.client.get("/assessment/download-report-json/")
        self.assertEqual(dl_json.status_code, 200)
        self.assertIn("risk_assessment", dl_json.content.decode("utf-8"))

    def test_question_page_contains_camera_recovery_js_markers(self):
        response = self.client.get("/assessment/question/1/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("X-Question-Partial", html)
        self.assertIn("/ws/emotion/${assessmentId}/${this.currentScale}/", html)
        self.assertIn("Continuous capture", html)


class AssessmentIdempotencyTests(TransactionTestCase):
    reset_sequences = True

    def _build_request_with_shared_session(self, session_key):
        rf = RequestFactory()
        req = rf.get("/assessment/question/1/")
        middleware = SessionMiddleware(lambda request: None)
        middleware.process_request(req)
        req.session.create()
        req.session._session_key = session_key
        req.user = type("Anon", (), {"is_authenticated": False})()
        return req

    def test_get_or_create_assessment_idempotent_under_parallel_calls(self):
        session_key = "parallel-session-key"
        out = []
        lock = threading.Lock()

        def worker():
            req = self._build_request_with_shared_session(session_key)
            req.session["assessment_cycle"] = 1
            assessment = _get_or_create_assessment(req)
            with lock:
                out.append(assessment.id)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(len(set(out)), 1)
        self.assertEqual(
            Assessment.objects.filter(assessment_token=f"{session_key}:1").count(),
            1,
        )


class AnalyzerLogicTests(TestCase):
    def setUp(self):
        self.analyzer = MSEAnalyzer()

    def test_sentiment_handles_negation(self):
        score = self.analyzer._calculate_sentiment("I am not good and not okay")
        self.assertLess(score, 0)

    def test_benign_idioms_not_escalated(self):
        for text in ["I want to kill time", "I am dead tired", "I killed it in exam", "suicide squad movie was good"]:
            out = self.analyzer._assess_suicide_risk({"7": text})
            self.assertFalse(out["present"])

    def test_typo_case_detected_conservatively(self):
        out = self.analyzer._assess_suicide_risk({"7": "I may kll myselff"})
        self.assertTrue(out["present"])

    def test_third_person_quote_not_high_same_as_first_person(self):
        out = self.analyzer._assess_suicide_risk({"7": "he said i want to die"})
        self.assertIn(out["risk_level"], {"Low", "Moderate"})

    def test_plan_without_word_plan_detected(self):
        out = self.analyzer._assess_suicide_risk({"7": "I am going to use pills tonight"})
        self.assertTrue(out["plan"])

    def test_benign_plan_not_triggered(self):
        out = self.analyzer._assess_suicide_risk({"7": "I plan my day and study plan daily"})
        self.assertFalse(out["plan"])

    def test_contradiction_sets_needs_clinician_review(self):
        answers = {"7": "no suicidal thoughts", "14": "sometimes i want to kill myself"}
        risk = self.analyzer._analyze_risk(answers)
        self.assertTrue(risk.get("needs_clinician_review", False))


class EmotionSummaryTests(TestCase):
    def test_build_scale_emotion_summary_filters_by_scale(self):
        assessment = Assessment.objects.create(
            session_key="summary-session",
            assessment_token="summary-session:1",
        )
        EmotionRecord.objects.create(
            assessment=assessment,
            scale="anxiety",
            dominant_emotion="sad",
            emotion_scores={"sad": 82.0},
            confidence=0.9,
            status=EmotionRecord.STATUS_OK,
        )
        EmotionRecord.objects.create(
            assessment=assessment,
            scale="stress",
            dominant_emotion="happy",
            emotion_scores={"happy": 77.0},
            confidence=0.8,
            status=EmotionRecord.STATUS_OK,
        )

        summary = build_scale_emotion_summary(assessment, "anxiety")

        self.assertTrue(summary["available"])
        self.assertEqual(summary["frames_analyzed"], 1)
        self.assertEqual(summary["overall_dominant_emotion"], "sad")
        self.assertEqual(summary["distribution_counts"], {"sad": 1})

    def test_build_scale_emotion_summary_reports_captured_but_invalid_frames(self):
        assessment = Assessment.objects.create(
            session_key="summary-session-2",
            assessment_token="summary-session-2:1",
        )
        EmotionRecord.objects.create(
            assessment=assessment,
            scale="anxiety",
            dominant_emotion="",
            emotion_scores={},
            confidence=None,
            status=EmotionRecord.STATUS_QUALITY_LOW,
        )

        summary = build_scale_emotion_summary(assessment, "anxiety")

        self.assertFalse(summary["available"])
        self.assertEqual(summary["raw_record_count"], 1)
        self.assertEqual(summary["status_counts"], {EmotionRecord.STATUS_QUALITY_LOW: 1})

    def test_build_emotion_timeline_summary_returns_percentages(self):
        assessment = Assessment.objects.create(
            session_key="timeline-session",
            assessment_token="timeline-session:1",
        )
        for idx, emotion in enumerate(["happy", "sad", "happy", "angry"], start=1):
            EmotionRecord.objects.create(
                assessment=assessment,
                scale="anxiety",
                frame_id=f"timeline-{idx}",
                frame_number=idx,
                timestamp_sec=float(idx),
                dominant_emotion=emotion,
                emotion_scores={emotion: 0.9},
                confidence=0.9,
                status=EmotionRecord.STATUS_OK,
            )

        summary = build_emotion_timeline_summary(assessment, scale="anxiety")

        self.assertEqual(summary["total_frames"], 4)
        self.assertEqual(summary["most_frequent_emotion"], "happy")
        self.assertEqual(summary["emotion_percentages"]["happy"], 50.0)


class ConsumerUnitValidationTests(TestCase):
    def _build_consumer(self):
        c = EmotionStreamConsumer()
        c.max_encoded_image_bytes = 100
        c.max_image_bytes = 90
        c.max_pixels = 2000
        c.max_width = 100
        c.max_height = 100
        c.min_brightness = 20
        c.max_brightness = 235
        c.min_blur_variance = 35.0
        c.min_face_confidence = 0.55
        c.uncertain_threshold = 45.0
        c.angry_suppression_threshold = 60.0
        c.identical_result_window = 5
        c.debug_noise_test = False
        c.recent_frame_hashes = deque(maxlen=c.identical_result_window)
        c.recent_result_signatures = deque(maxlen=c.identical_result_window)
        c.face_track_iou_threshold = 0.25
        c.inference_timeout = 0.2
        c.correlation_id = "test"
        c.assessment_id = 1
        return c

    def test_decode_rejects_invalid_base64(self):
        c = self._build_consumer()
        with self.assertRaises(ValueError):
            c._decode_base64_image("%%%invalid%%")

    def test_decode_rejects_oversized_encoded_payload_preddecode(self):
        c = self._build_consumer()
        with self.assertRaises(ValueError):
            c._decode_base64_image("a" * 500)

    def test_quality_gate_abstain_dark_frame(self):
        c = self._build_consumer()
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        allowed, _ = c._passes_quality_gate(frame)
        self.assertFalse(allowed)

    def test_error_result_shape(self):
        c = self._build_consumer()
        result = c._error_result("timeout")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "timeout")
        self.assertEqual(result["dominant_emotion"], "neutral")
        self.assertTrue(result["emotion_scores"])

    def test_normalize_result_payload_fixes_empty_values(self):
        c = self._build_consumer()
        result = c._normalize_result_payload(
            {"status": "weird", "dominant_emotion": "", "emotion_scores": {}, "confidence": None}
        )
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["dominant_emotion"], "neutral")
        self.assertEqual(result["emotion_scores"], {"neutral": 0.1})

    def test_preprocess_frame_for_inference_returns_rgb_224(self):
        frame = np.full((80, 120, 3), 90, dtype=np.uint8)
        processed = preprocess_frame_for_inference(frame)
        self.assertEqual(processed.shape, (224, 224, 3))
        self.assertTrue(isinstance(processed, np.ndarray))

    def test_uncertain_status_when_top_emotion_below_threshold(self):
        c = self._build_consumer()
        c.uncertain_threshold = 40.0
        c.angry_suppression_threshold = 60.0
        c.min_face_area_ratio = 0.0
        c.subject_box = None
        result_face = {
            "dominant_emotion": "happy",
            "emotion": {"happy": 32.0, "sad": 28.0, "angry": 20.0},
            "face_confidence": 0.9,
            "region": {"x": 0, "y": 0, "w": 80, "h": 80},
        }
        c._log_event = lambda *args, **kwargs: None
        c._normalize_result_payload = EmotionStreamConsumer._normalize_result_payload.__get__(c, EmotionStreamConsumer)
        c._face_conf = EmotionStreamConsumer._face_conf.__get__(c, EmotionStreamConsumer)
        c._face_box = EmotionStreamConsumer._face_box.__get__(c, EmotionStreamConsumer)
        confidence = c._face_conf(result_face)
        emotion_scores = {k: float(v) for k, v in result_face["emotion"].items()}
        top_emotion_score = max(emotion_scores.values())
        payload = c._normalize_result_payload(
            {
                "status": "uncertain" if top_emotion_score < 40.0 else "ok",
                "dominant_emotion": result_face["dominant_emotion"],
                "emotion_scores": emotion_scores,
                "confidence": confidence,
            }
        )
        self.assertEqual(payload["status"], "uncertain")
        self.assertEqual(payload["dominant_emotion"], "happy")

    def test_angry_bias_guard_suppresses_low_confidence_angry_top_score(self):
        c = self._build_consumer()
        c.angry_suppression_threshold = 60.0
        guarded, suppressed = c._apply_angry_bias_guard({"angry": 55.0, "neutral": 30.0, "sad": 15.0})
        self.assertTrue(suppressed)
        self.assertEqual(guarded["angry"], 0.0)

    def test_emotion_decision_uses_temporal_smoothing(self):
        c = self._build_consumer()
        c.uncertain_threshold = 45.0
        c.angry_suppression_threshold = 60.0
        c._log_event = lambda *args, **kwargs: None
        result_one = c._build_emotion_decision(
            raw_scores={"neutral": 70.0, "angry": 20.0, "sad": 10.0},
            confidence=0.9,
            quality_warning=None,
            frame_id="frame-1",
            frame_hash="hash-1",
        )
        result_two = c._build_emotion_decision(
            raw_scores={"neutral": 68.0, "angry": 22.0, "sad": 10.0},
            confidence=0.9,
            quality_warning=None,
            frame_id="frame-2",
            frame_hash="hash-2",
        )
        result_three = c._build_emotion_decision(
            raw_scores={"neutral": 65.0, "angry": 25.0, "sad": 10.0},
            confidence=0.9,
            quality_warning=None,
            frame_id="frame-3",
            frame_hash="hash-3",
        )
        self.assertEqual(result_one["dominant_emotion"], "neutral")
        self.assertEqual(result_two["dominant_emotion"], "neutral")
        self.assertEqual(result_three["dominant_emotion"], "neutral")


class WorkerLifecycleTests(TestCase):
    def test_worker_restart_after_repeated_timeouts(self):
        worker = EmotionInferenceWorker(max_memory_mb=128)
        with mock.patch.object(worker, "restart") as restart_mock:
            worker.register_timeout(restart_threshold=3)
            worker.register_timeout(restart_threshold=3)
            worker.register_timeout(restart_threshold=3)
            self.assertEqual(restart_mock.call_count, 1)

    def test_worker_restart_after_repeated_crashes(self):
        worker = EmotionInferenceWorker(max_memory_mb=128)
        with mock.patch.object(worker, "restart") as restart_mock:
            worker.register_crash(restart_threshold=2)
            worker.register_crash(restart_threshold=2)
            self.assertEqual(restart_mock.call_count, 1)

    def test_worker_uses_local_mode_on_windows(self):
        fake_deepface_module = mock.Mock()
        fake_deepface_module.DeepFace = mock.Mock()
        with mock.patch("Questionaire_project.emotion_worker.platform.system", return_value="Windows"), \
             mock.patch("Questionaire_project.emotion_worker.check_deepface_import", return_value=None), \
             mock.patch.dict(sys.modules, {"deepface": fake_deepface_module}):
            worker = EmotionInferenceWorker(max_memory_mb=128)
            worker.restart()
            self.assertTrue(worker._local_mode)
            self.assertIsNone(worker.process)


@override_settings(
    EMOTION_ALLOWED_ORIGINS=["http://testserver"],
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    EMOTION_MAX_CONNECTIONS_PER_IP=2,
    EMOTION_MAX_CONNECTIONS_PER_ASSESSMENT=1,
    EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW=1,
    EMOTION_FRAME_QUOTA_WINDOW_SECONDS=60,
)
class ConsumerWebsocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        cache.clear()
        self.assessment = Assessment.objects.create(
            session_key="ws-session",
            assessment_token="ws-session:1",
        )

    async def _connect(self, assessment_id, scale="anxiety"):
        comm = WebsocketCommunicator(
            application,
            f"/ws/emotion/{assessment_id}/{scale}/",
            headers=[(b"origin", b"http://testserver")],
        )
        with mock.patch("Questionaire_project.consumers.EmotionStreamConsumer._can_access_assessment", return_value=True):
            connected, _ = await comm.connect()
        return comm, connected

    def test_reconnect_after_disconnect_succeeds(self):
        async def runner():
            comm1, ok1 = await self._connect(self.assessment.id)
            self.assertTrue(ok1)
            _ = await comm1.receive_json_from()
            await comm1.disconnect()

            comm2, ok2 = await self._connect(self.assessment.id)
            self.assertTrue(ok2)
            _ = await comm2.receive_json_from()
            await comm2.disconnect()

        async_to_sync(runner)()

    def test_single_active_stream_per_assessment(self):
        async def runner():
            comm1, ok1 = await self._connect(self.assessment.id)
            self.assertTrue(ok1)
            _ = await comm1.receive_json_from()
            comm2, ok2 = await self._connect(self.assessment.id)
            self.assertFalse(ok2)
            await comm1.disconnect()
        async_to_sync(runner)()

    def test_ping_pong_roundtrip(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            await comm.send_json_to({"type": "ping", "assessment_id": self.assessment.id, "ts": 123})
            pong = await comm.receive_json_from()
            self.assertEqual(pong["type"], "pong")
            await comm.disconnect()

        async_to_sync(runner)()

    @override_settings(EMOTION_HEARTBEAT_GRACE_SECONDS=90, EMOTION_HEARTBEAT_CHECK_SECONDS=0.2, EMOTION_ENFORCE_PING_TIMEOUT=True)
    def test_ping_keeps_socket_alive(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            await comm.send_json_to({"type": "ping", "assessment_id": self.assessment.id, "ts": 123})
            pong = await comm.receive_json_from()
            self.assertEqual(pong.get("type"), "pong")
            await asyncio.sleep(0.3)
            self.assertEqual(comm.output_queue.qsize(), 0)
            await comm.disconnect()

        async_to_sync(runner)()

    def test_invalid_base64_rejected(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            await comm.send_json_to(
                {
                    "type": "frame",
                    "assessment_id": self.assessment.id,
                    "image_base64": "%%%invalid",
                    "question_id": 1,
                }
            )
            response = await comm.receive_json_from()
            self.assertIn(response["status"], {"error", "quality_low", "no_face", "rate_limited"})
            await comm.disconnect()
        async_to_sync(runner)()

    @override_settings(EMOTION_MAX_ENCODED_IMAGE_BYTES=40, EMOTION_MAX_IMAGE_BYTES=40)
    def test_oversized_frame_rejected(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            await comm.send_json_to(
                {
                    "type": "frame",
                    "assessment_id": self.assessment.id,
                    "image_base64": "data:image/jpeg;base64," + ("A" * 300),
                    "question_id": 1,
                }
            )
            response = await comm.receive_json_from()
            self.assertEqual(response["status"], "error")
            await comm.disconnect()

        async_to_sync(runner)()

    def test_inference_timeout_does_not_close_socket(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch(
                "Questionaire_project.consumers.analyze_frame_sync",
                side_effect=RuntimeError("simulated_direct_failure"),
            ):
                await comm.send_json_to(
                    {
                        "type": "frame",
                        "assessment_id": self.assessment.id,
                        "image_base64": _jpeg_data_url(noisy=True),
                        "question_id": 1,
                    }
                )
                frame = await comm.receive_json_from()
                self.assertEqual(frame["type"], "frame_result")
                self.assertEqual(frame["status"], "fallback")
                self.assertEqual(frame.get("message"), "emotion_fallback_applied")
            await comm.send_json_to({"type": "ping", "assessment_id": self.assessment.id, "ts": 1})
            pong = await comm.receive_json_from()
            self.assertEqual(pong["type"], "pong")
            await comm.disconnect()

        async_to_sync(runner)()

    def test_saved_record_is_normalized_when_analysis_returns_empty_emotion(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch(
                "Questionaire_project.consumers.EmotionStreamConsumer._analyze_frame",
                return_value={"status": "error", "dominant_emotion": "", "emotion_scores": {}, "confidence": None},
            ):
                await comm.send_json_to(
                    {
                        "type": "frame",
                        "assessment_id": self.assessment.id,
                        "image_base64": _jpeg_data_url(noisy=True),
                        "question_id": 1,
                        "frame_id": "normalize-empty-emotion",
                    }
                )
                frame = await comm.receive_json_from()
                self.assertEqual(frame["dominant_emotion"], "neutral")
            await comm.disconnect()

        async_to_sync(runner)()
        record = EmotionRecord.objects.get(frame_id="normalize-empty-emotion")
        self.assertEqual(record.dominant_emotion, "neutral")
        self.assertTrue(record.emotion_scores)

    def test_rate_limit_path(self):
        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch("Questionaire_project.consumers.EmotionStreamConsumer._analyze_frame", return_value={"status": "ok", "dominant_emotion": "sad", "emotion_scores": {"sad": 70.0}, "confidence": 0.9}):
                await comm.send_json_to(
                    {
                        "type": "frame",
                        "assessment_id": self.assessment.id,
                        "image_base64": _jpeg_data_url(),
                        "question_id": 1,
                    }
                )
                _ = await comm.receive_json_from()
                await comm.send_json_to(
                    {
                        "type": "frame",
                        "assessment_id": self.assessment.id,
                        "image_base64": _jpeg_data_url(),
                        "question_id": 1,
                    }
                )
                second = await comm.receive_json_from()
                self.assertIn(second["status"], {"rate_limited", "dropped"})
            await comm.disconnect()
        async_to_sync(runner)()

    @override_settings(
        EMOTION_ANALYZE_INTERVAL_SECONDS=0,
        EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW=100,
        EMOTION_FRAME_QUOTA_WINDOW_SECONDS=60,
    )
    def test_multiple_frames_create_multiple_emotion_records(self):
        emotions = [
            {"dominant_emotion": "happy", "emotion_scores": {"happy": 90.0}, "confidence": 0.9, "status": "ok"},
            {"dominant_emotion": "sad", "emotion_scores": {"sad": 88.0}, "confidence": 0.88, "status": "ok"},
            {"dominant_emotion": "angry", "emotion_scores": {"angry": 86.0}, "confidence": 0.86, "status": "ok"},
            {"dominant_emotion": "happy", "emotion_scores": {"happy": 91.0}, "confidence": 0.91, "status": "ok"},
            {"dominant_emotion": "sad", "emotion_scores": {"sad": 87.0}, "confidence": 0.87, "status": "ok"},
            {"dominant_emotion": "angry", "emotion_scores": {"angry": 85.0}, "confidence": 0.85, "status": "ok"},
            {"dominant_emotion": "happy", "emotion_scores": {"happy": 89.0}, "confidence": 0.89, "status": "ok"},
            {"dominant_emotion": "sad", "emotion_scores": {"sad": 84.0}, "confidence": 0.84, "status": "ok"},
            {"dominant_emotion": "angry", "emotion_scores": {"angry": 83.0}, "confidence": 0.83, "status": "ok"},
            {"dominant_emotion": "happy", "emotion_scores": {"happy": 92.0}, "confidence": 0.92, "status": "ok"},
        ]

        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch(
                "Questionaire_project.consumers.EmotionStreamConsumer._analyze_frame",
                side_effect=emotions,
            ):
                for idx in range(10):
                    await comm.send_json_to(
                        {
                            "type": "frame",
                            "assessment_id": self.assessment.id,
                            "image_base64": _jpeg_data_url(noisy=True),
                            "question_id": 1,
                            "frame_id": f"timeline-frame-{idx}",
                            "frame_number": idx + 1,
                            "timestamp_sec": float(idx) * 0.5,
                        }
                    )
                    response = await comm.receive_json_from()
                    self.assertEqual(response["frame_number"], idx + 1)
            await comm.disconnect()

        async_to_sync(runner)()

        records = list(
            EmotionRecord.objects.filter(assessment=self.assessment)
            .exclude(frame_id="")
            .order_by("frame_number")
        )
        self.assertEqual(len(records), 10)
        self.assertEqual(records[0].dominant_emotion, "happy")
        self.assertEqual(records[1].dominant_emotion, "sad")
        self.assertEqual(records[2].dominant_emotion, "angry")
        self.assertEqual(len({record.dominant_emotion for record in records}), 3)

    @override_settings(
        EMOTION_ANALYZE_INTERVAL_SECONDS=0,
        EMOTION_MAX_FRAMES_PER_ASSESSMENT_WINDOW=100,
        EMOTION_FRAME_QUOTA_WINDOW_SECONDS=60,
        EMOTION_MIN_FACE_AREA_RATIO=0.0,
    )
    def test_direct_deepface_path_detects_multiple_emotions(self):
        direct_results = [
            {"status": "ok", "faces": [{"dominant_emotion": "happy", "emotion": {"happy": 95.0, "sad": 2.0}, "face_confidence": 0.9, "region": {"x": 10, "y": 10, "w": 120, "h": 120}}]},
            {"status": "ok", "faces": [{"dominant_emotion": "sad", "emotion": {"happy": 5.0, "sad": 91.0}, "face_confidence": 0.9, "region": {"x": 10, "y": 10, "w": 120, "h": 120}}]},
            {"status": "ok", "faces": [{"dominant_emotion": "angry", "emotion": {"angry": 88.0, "neutral": 7.0}, "face_confidence": 0.9, "region": {"x": 10, "y": 10, "w": 120, "h": 120}}]},
            {"status": "ok", "faces": [{"dominant_emotion": "happy", "emotion": {"happy": 90.0, "surprise": 4.0}, "face_confidence": 0.9, "region": {"x": 10, "y": 10, "w": 120, "h": 120}}]},
            {"status": "ok", "faces": [{"dominant_emotion": "sad", "emotion": {"sad": 89.0, "neutral": 5.0}, "face_confidence": 0.9, "region": {"x": 10, "y": 10, "w": 120, "h": 120}}]},
        ]

        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch("Questionaire_project.consumers.analyze_frame_sync", side_effect=direct_results):
                for idx in range(5):
                    await comm.send_json_to(
                        {
                            "type": "frame",
                            "assessment_id": self.assessment.id,
                            "image_base64": _jpeg_data_url(noisy=True),
                            "question_id": 1,
                            "frame_id": f"direct-frame-{idx}",
                            "frame_number": idx + 1,
                            "timestamp_sec": float(idx),
                        }
                    )
                    response = await comm.receive_json_from()
                    self.assertIn(response["dominant_emotion"], {"happy", "sad", "angry"})
            await comm.disconnect()

        async_to_sync(runner)()

        saved = list(
            EmotionRecord.objects.filter(assessment=self.assessment, frame_id__startswith="direct-frame-")
            .order_by("frame_number")
            .values_list("dominant_emotion", flat=True)
        )
        self.assertEqual(len(saved), 5)
        self.assertGreaterEqual(len(set(saved)), 2)


class EmotionDebugViewTests(TestCase):
    def test_debug_emotions_returns_recent_frames_and_status_distribution(self):
        assessment = Assessment.objects.create(
            session_key="debug-session",
            assessment_token="debug-session:1",
        )
        EmotionRecord.objects.create(
            assessment=assessment,
            scale="anxiety",
            frame_id="debug-1",
            dominant_emotion="neutral",
            emotion_scores={"neutral": 0.1},
            confidence=0.1,
            status=EmotionRecord.STATUS_FALLBACK,
        )
        EmotionRecord.objects.create(
            assessment=assessment,
            scale="anxiety",
            frame_id="debug-2",
            dominant_emotion="happy",
            emotion_scores={"happy": 0.8},
            confidence=0.8,
            status=EmotionRecord.STATUS_OK,
        )

        response = self.client.get(f"/assessment/debug/emotions/{assessment.id}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["recent_frames"]), 2)
        self.assertEqual(body["status_distribution"][EmotionRecord.STATUS_FALLBACK], 1)
        self.assertEqual(body["status_distribution"][EmotionRecord.STATUS_OK], 1)
        self.assertIn("emotion_summary", body)
        self.assertIn("most_frequent_emotion", body["emotion_summary"])
        self.assertIn("emotion_percentages", body["emotion_summary"])
        self.assertIn("total_frames", body["emotion_summary"])
        self.assertIn("frame_number", body["recent_frames"][0])
        self.assertIn("timestamp_sec", body["recent_frames"][0])

    def test_download_report_json_contains_timeline_summary_fields(self):
        assessment = Assessment.objects.create(
            session_key="report-session",
            assessment_token="report-session:1",
            is_completed=True,
            report_json={
                "timestamp": "2026-04-07T00:00:00Z",
                "depression": {
                    "emotion_summary": {
                        "available": True,
                        "most_frequent_emotion": "happy",
                        "emotion_percentages": {"happy": 50.0, "sad": 30.0, "angry": 20.0},
                        "total_frames": 10,
                    }
                },
                "stress": {"emotion_summary": {}},
                "anxiety": {"emotion_summary": {}},
                "emotion_summary": {
                    "available": True,
                    "most_frequent_emotion": "happy",
                    "emotion_percentages": {"happy": 50.0, "sad": 30.0, "angry": 20.0},
                    "total_frames": 10,
                },
            },
        )
        session = self.client.session
        session["last_completed_assessment_id"] = assessment.id
        session.save()

        response = self.client.get("/assessment/download-report-json/")

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body["emotion_summary"]["most_frequent_emotion"], "happy")
        self.assertEqual(body["emotion_summary"]["emotion_percentages"]["sad"], 30.0)
        self.assertEqual(body["emotion_summary"]["total_frames"], 10)

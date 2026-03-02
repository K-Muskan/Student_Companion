import asyncio
import base64
import json
import threading
import time
from unittest import mock

import cv2
import numpy as np
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings

from Questionaire_project.consumers import EmotionStreamConsumer
from Questionaire_project.emotion_worker import EmotionInferenceWorker
from Questionaire_project.models import Assessment, Question
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
        self.assertIn("type: 'ping'", html)
        self.assertIn("track.onended", html)
        self.assertIn("visibilitychange", html)
        self.assertIn("scheduleReconnect", html)


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
        self.assertFalse(c._passes_quality_gate(frame))

    def test_error_result_shape(self):
        c = self._build_consumer()
        result = c._error_result("timeout")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "timeout")


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

    async def _connect(self, assessment_id):
        comm = WebsocketCommunicator(
            application,
            f"/ws/emotion/{assessment_id}/",
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
        class FakeWorker:
            def submit(self, payload):
                return True

            def wait_for(self, request_id, timeout):
                return None

            def register_timeout(self, restart_threshold):
                return None

            def register_crash(self, restart_threshold):
                return None

        async def runner():
            comm, ok = await self._connect(self.assessment.id)
            self.assertTrue(ok)
            _ = await comm.receive_json_from()
            with mock.patch(
                "Questionaire_project.consumers.get_inference_worker",
                return_value=FakeWorker(),
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
                self.assertEqual(frame["status"], "error")
                self.assertEqual(frame.get("message"), "timeout")
            await comm.send_json_to({"type": "ping", "assessment_id": self.assessment.id, "ts": 1})
            pong = await comm.receive_json_from()
            self.assertEqual(pong["type"], "pong")
            await comm.disconnect()

        async_to_sync(runner)()

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

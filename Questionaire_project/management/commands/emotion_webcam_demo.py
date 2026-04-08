from collections import deque
from typing import Dict

import cv2
from django.conf import settings
from django.core.management.base import BaseCommand

from Questionaire_project.emotion_worker import analyze_frame_sync


def _normalize_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
    cleaned = {}
    for key, value in (raw_scores or {}).items():
        try:
            score = max(0.0, float(value))
        except (TypeError, ValueError):
            continue
        label = str(key or "").strip().lower()
        if label:
            cleaned[label] = score
    total = sum(cleaned.values())
    if total <= 1e-6:
        return {}
    return {emotion: round((score / total) * 100.0, 2) for emotion, score in cleaned.items()}


class Command(BaseCommand):
    help = "Run a small webcam demo for the DeepFace emotion pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--camera-index", type=int, default=0)
        parser.add_argument("--max-frames", type=int, default=0, help="Stop after N analyzed frames. 0 means run until q.")

    def handle(self, *args, **options):
        camera_index = options["camera_index"]
        max_frames = max(0, int(options["max_frames"]))
        uncertain_threshold = float(getattr(settings, "EMOTION_UNCERTAIN_THRESHOLD", 45.0))
        angry_threshold = float(getattr(settings, "EMOTION_ANGRY_SUPPRESSION_THRESHOLD", 60.0))
        smoothing_window = max(1, int(getattr(settings, "EMOTION_SMOOTHING_WINDOW", 5)))
        history = deque(maxlen=smoothing_window)

        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            self.stderr.write(self.style.ERROR("Could not open webcam."))
            return

        self.stdout.write("Press q to quit the demo window.")
        analyzed_frames = 0

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    self.stderr.write(self.style.WARNING("Skipping unreadable webcam frame."))
                    continue

                result = analyze_frame_sync(frame)
                faces = result.get("faces") or []
                label = "no_face"
                scores = {}

                if faces and isinstance(faces[0], dict):
                    scores = _normalize_scores(faces[0].get("emotion", {}) or {})
                    if scores:
                        history.append(scores)
                        aggregate = {}
                        for snapshot in history:
                            for emotion, score in snapshot.items():
                                aggregate[emotion] = aggregate.get(emotion, 0.0) + score
                        smoothed = {
                            emotion: round(total / len(history), 2)
                            for emotion, total in aggregate.items()
                        }
                        angry_score = smoothed.get("angry", 0.0)
                        if angry_score >= max(smoothed.values()) and angry_score < angry_threshold:
                            smoothed["angry"] = 0.0
                        smoothed = _normalize_scores(smoothed)
                        if smoothed:
                            top_emotion, top_score = max(smoothed.items(), key=lambda item: item[1])
                            label = top_emotion if top_score >= uncertain_threshold else "uncertain"
                            scores = smoothed

                analyzed_frames += 1
                top_three = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
                self.stdout.write(f"Frame {analyzed_frames}: {label} {top_three}")

                cv2.putText(frame, f"Emotion: {label}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.imshow("Emotion Demo", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                if max_frames and analyzed_frames >= max_frames:
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()

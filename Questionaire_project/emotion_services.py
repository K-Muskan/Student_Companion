from collections import Counter, defaultdict
from typing import Any, Dict, List

from .models import Assessment, EmotionRecord


DISTRESS_EMOTIONS = {"fear", "sad", "angry"}


def build_emotion_summary(assessment: Assessment) -> Dict[str, Any]:
    records = list(
        EmotionRecord.objects.filter(assessment=assessment, status=EmotionRecord.STATUS_OK)
        .select_related("question")
        .order_by("created_at")
    )

    if not records:
        return {
            "available": False,
            "sample_size": 0,
            "overall_dominant_emotion": None,
            "distribution_counts": {},
            "average_emotion_scores": {},
            "per_question_dominant": {},
            "distress_proxy": {
                "enabled": True,
                "flag": False,
                "ratio": 0.0,
                "threshold": 0.4,
                "note": "Soft indicator only; not a diagnosis.",
            },
        }

    dominant_list: List[str] = [r.dominant_emotion for r in records if r.dominant_emotion]
    dominant_counter = Counter(dominant_list)
    overall_dominant = dominant_counter.most_common(1)[0][0] if dominant_counter else None

    score_totals = defaultdict(float)
    score_counts = defaultdict(int)
    for record in records:
        for emotion, score in (record.emotion_scores or {}).items():
            score_totals[emotion] += float(score)
            score_counts[emotion] += 1

    average_scores = {}
    for emotion, total in score_totals.items():
        average_scores[emotion] = round(total / score_counts[emotion], 4)

    by_question = defaultdict(list)
    for record in records:
        if record.question_id and record.dominant_emotion:
            by_question[record.question_id].append(record.dominant_emotion)

    per_question_dominant = {}
    for question_id, emotions in by_question.items():
        per_question_dominant[str(question_id)] = Counter(emotions).most_common(1)[0][0]

    distress_count = sum(1 for e in dominant_list if e in DISTRESS_EMOTIONS)
    sample_size = len(dominant_list)
    distress_ratio = (distress_count / sample_size) if sample_size else 0.0
    distress_flag = sample_size >= 5 and distress_ratio >= 0.4

    return {
        "available": True,
        "sample_size": len(records),
        "overall_dominant_emotion": overall_dominant,
        "distribution_counts": dict(dominant_counter),
        "average_emotion_scores": average_scores,
        "per_question_dominant": per_question_dominant,
        "distress_proxy": {
            "enabled": True,
            "flag": distress_flag,
            "ratio": round(distress_ratio, 4),
            "threshold": 0.4,
            "note": "Soft indicator only; not a diagnosis.",
        },
    }

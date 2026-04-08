import math
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

from django.db.models import Count

from .models import Assessment, EmotionRecord, ScaleEmotionSession


DISTRESS_EMOTIONS = {"fear", "sad", "angry"}
DISTRESS_THRESHOLD = 0.4
MIN_VALID_FRAMES = 8
logger = logging.getLogger(__name__)


def empty_emotion_summary(*, scale: Optional[str] = None, raw_record_count: int = 0, status_counts: Optional[Dict[str, int]] = None, note: str = "") -> Dict[str, Any]:
    return {
        "available": False,
        "scale": scale,
        "frames_analyzed": 0,
        "sample_size": 0,
        "total_records": 0,
        "raw_record_count": raw_record_count,
        "status_counts": status_counts or {},
        "overall_dominant_emotion": None,
        "dominant_emotion": None,
        "distribution_counts": {},
        "average_emotion_scores": {},
        "per_question_dominant": {},
        "note": note or "No valid emotion frames available.",
        "distress_proxy": {
            "flag": False,
            "ratio": 0.0,
            "ratio_lower_bound": 0.0,
            "threshold": DISTRESS_THRESHOLD,
            "min_valid_frames": MIN_VALID_FRAMES,
        },
    }


def _summarize_records(records: Iterable[EmotionRecord]) -> Dict[str, Any]:
    ordered_records = list(records)
    if not ordered_records:
        return empty_emotion_summary()

    dominant_list: List[str] = [r.dominant_emotion for r in ordered_records if r.dominant_emotion]
    dominant_counter = Counter(dominant_list)
    overall_dominant = dominant_counter.most_common(1)[0][0] if dominant_counter else None

    score_totals = defaultdict(float)
    score_counts = defaultdict(int)
    weighted_total = 0.0
    weighted_distress = 0.0

    for record in ordered_records:
        for emotion, score in (record.emotion_scores or {}).items():
            try:
                score_totals[str(emotion)] += float(score)
                score_counts[str(emotion)] += 1
            except (TypeError, ValueError):
                continue

        if not record.dominant_emotion:
            continue
        weight = float(record.confidence) if record.confidence is not None else 0.5
        weight = min(max(weight, 0.05), 1.0)
        weighted_total += weight
        if record.dominant_emotion in DISTRESS_EMOTIONS:
            weighted_distress += weight

    average_scores = {
        emotion: round(total / score_counts[emotion], 4)
        for emotion, total in score_totals.items()
        if score_counts[emotion]
    }
    per_question = defaultdict(list)
    for record in ordered_records:
        if record.question_id and record.dominant_emotion:
            per_question[str(record.question_id)].append(record.dominant_emotion)
    per_question_dominant = {
        qid: Counter(emotions).most_common(1)[0][0]
        for qid, emotions in per_question.items()
        if emotions
    }

    frames_analyzed = len(dominant_list)
    distress_ratio = (weighted_distress / weighted_total) if weighted_total else 0.0
    margin = (
        1.96 * math.sqrt((distress_ratio * (1 - distress_ratio)) / max(frames_analyzed, 1))
        if frames_analyzed
        else 1.0
    )
    lower_bound = max(0.0, distress_ratio - margin)
    distress_flag = frames_analyzed >= MIN_VALID_FRAMES and lower_bound >= DISTRESS_THRESHOLD

    return {
        "available": True,
        "frames_analyzed": frames_analyzed,
        "sample_size": frames_analyzed,
        "total_records": len(ordered_records),
        "overall_dominant_emotion": overall_dominant,
        "dominant_emotion": overall_dominant,
        "distribution_counts": dict(dominant_counter),
        "average_emotion_scores": average_scores,
        "per_question_dominant": per_question_dominant,
        "distress_proxy": {
            "flag": distress_flag,
            "ratio": round(distress_ratio, 4),
            "ratio_lower_bound": round(lower_bound, 4),
            "threshold": DISTRESS_THRESHOLD,
            "min_valid_frames": MIN_VALID_FRAMES,
        },
    }


def build_emotion_summary(assessment: Assessment, scale: Optional[str] = None) -> Dict[str, Any]:
    raw_queryset = EmotionRecord.objects.filter(assessment=assessment)
    if scale:
        raw_queryset = raw_queryset.filter(scale=scale)

    status_counts = {
        row["status"]: row["total"]
        for row in raw_queryset.values("status").annotate(total=Count("id"))
    }
    raw_record_count = sum(status_counts.values())

    ok_queryset = raw_queryset.filter(
        status__in=[EmotionRecord.STATUS_OK, EmotionRecord.STATUS_FALLBACK]
    ).order_by("created_at")
    if not scale:
        ok_queryset = ok_queryset.select_related("question")

    summary = _summarize_records(ok_queryset)
    summary["scale"] = scale
    summary["raw_record_count"] = raw_record_count
    summary["status_counts"] = status_counts

    if summary.get("available"):
        summary["note"] = ""
        return summary

    if raw_record_count > 0:
        logger.warning(
            "emotion_summary_no_valid_ok_frames",
            extra={
                "assessment_id": assessment.id,
                "scale": scale,
                "raw_record_count": raw_record_count,
                "status_counts": status_counts,
            },
        )
        return empty_emotion_summary(
            scale=scale,
            raw_record_count=raw_record_count,
            status_counts=status_counts,
            note="Emotion frames were captured, but none passed validation as STATUS_OK.",
        )

    logger.info(
        "emotion_summary_no_frames_found",
        extra={"assessment_id": assessment.id, "scale": scale},
    )
    return empty_emotion_summary(
        scale=scale,
        raw_record_count=0,
        status_counts={},
        note="No emotion frames were captured for this assessment.",
    )


def build_scale_emotion_summary(assessment: Assessment, scale: str) -> Dict[str, Any]:
    return build_emotion_summary(assessment, scale=scale)


def build_emotion_timeline_summary(assessment: Assessment, scale: Optional[str] = None) -> Dict[str, Any]:
    queryset = EmotionRecord.objects.filter(assessment=assessment)
    if scale:
        queryset = queryset.filter(scale=scale)

    records = list(
        queryset.exclude(dominant_emotion="")
        .order_by("created_at")
    )
    total = len(records)
    if total == 0:
        return {
            "total_frames": 0,
            "most_frequent_emotion": None,
            "emotion_percentages": {},
        }

    counter = Counter(record.dominant_emotion for record in records if record.dominant_emotion)
    percentages = {
        emotion: round((count / total) * 100, 2)
        for emotion, count in counter.items()
    }
    most_frequent = counter.most_common(1)[0][0] if counter else None
    return {
        "total_frames": total,
        "most_frequent_emotion": most_frequent,
        "emotion_percentages": percentages,
    }


def finalize_scale_emotion_session(assessment: Assessment, scale: str) -> Optional[ScaleEmotionSession]:
    session = (
        ScaleEmotionSession.objects.filter(
            assessment=assessment,
            scale=scale,
            ended_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )
    if not session:
        return None

    summary = build_scale_emotion_summary(assessment, scale)
    session.total_frames = int(summary.get("frames_analyzed", 0))
    session.overall_dominant_emotion = summary.get("overall_dominant_emotion") or ""
    session.distress_ratio = summary.get("distress_proxy", {}).get("ratio")
    return session

"""
report_parser.py
================
Responsibility: Extract structured data from a completed assessment.

We do NOT parse HTML strings here. Instead, we work directly with
the structured `report_json` stored on the Assessment model — this is
cleaner, more reliable, and already contains everything we need.

Public API
----------
    parse_report(assessment) -> ParsedReport (dict)

ParsedReport keys
-----------------
    depression_level   : str  e.g. "low" | "moderate" | "severe"
    anxiety_level      : str
    stress_level       : str
    depression_score   : int
    anxiety_score      : int
    stress_score       : int
    dominant_emotion   : str  overall dominant emotion across all scales
    emotional_summary  : str  free-text summary from feeling_analysis
    emotion_labels     : list[str]  concern/feeling labels from open-ended analysis
    scale_emotions     : dict  per-scale dominant emotion  {"depression": "sad", ...}
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_str(value, fallback="unknown") -> str:
    """Return a lowercase string or the fallback if value is empty/None."""
    if value and isinstance(value, str):
        return value.strip().lower()
    return fallback


def _extract_scale_info(report_json: dict, scale: str) -> dict:
    """
    Pull risk_level and total_score out of a single scale block.

    report_json["depression"] looks like:
        {"risk_level": "moderate", "total_score": 22, ...}
    """
    block = report_json.get(scale, {})
    return {
        "level": _safe_str(block.get("risk_level"), fallback="unknown"),
        "score": block.get("total_score", 0),
    }


def _extract_dominant_emotion(report_json: dict) -> str:
    """
    Overall dominant emotion is stored under report_json["emotion_summary"]
    which is built by emotion_services.build_emotion_summary().
    Falls back to checking per-scale summaries.
    """
    # Primary: overall summary
    overall = report_json.get("emotion_summary", {})
    emotion = overall.get("most_frequent_emotion") or overall.get("overall_dominant_emotion")
    if emotion:
        return _safe_str(emotion)

    # Fallback: first non-empty per-scale dominant
    for scale in ("depression", "stress", "anxiety"):
        block = report_json.get(scale, {})
        scale_emotion_summary = block.get("emotion_summary", {})
        emotion = (
            scale_emotion_summary.get("most_frequent_emotion")
            or scale_emotion_summary.get("overall_dominant_emotion")
        )
        if emotion:
            return _safe_str(emotion)

    return "neutral"


def _extract_scale_emotions(report_json: dict) -> dict:
    """
    Return the dominant emotion recorded *during* each scale.
    e.g. {"depression": "sad", "stress": "angry", "anxiety": "fear"}
    """
    result = {}
    for scale in ("depression", "stress", "anxiety"):
        block = report_json.get(scale, {})
        emotion_summary = block.get("emotion_summary", {})
        emotion = (
            emotion_summary.get("most_frequent_emotion")
            or emotion_summary.get("overall_dominant_emotion")
            or "neutral"
        )
        result[scale] = _safe_str(emotion)
    return result


def _extract_feeling_analysis(report_json: dict) -> tuple[str, list]:
    """
    feeling_analysis comes from analyze_open_ended_text() and is stored as:
        {
            "summary": "Student mentioned loneliness ...",
            "concern_feeling_label": {"loneliness": 0.8, "academic_stress": 0.6}
        }

    Returns:
        emotional_summary : str
        emotion_labels    : list[str]  (just the label names, sorted by score desc)
    """
    feeling = report_json.get("feeling_analysis", {})

    summary = feeling.get("summary", "").strip()

    labels_raw = feeling.get("concern_feeling_label", {})
    if isinstance(labels_raw, dict):
        # Sort by score descending so the most prominent concern comes first
        sorted_labels = sorted(labels_raw.items(), key=lambda x: float(x[1]), reverse=True)
        emotion_labels = [label for label, _ in sorted_labels]
    elif isinstance(labels_raw, list):
        emotion_labels = [str(l) for l in labels_raw]
    else:
        emotion_labels = []

    return summary, emotion_labels


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_report(assessment) -> dict:
    """
    Extract all relevant fields from a completed Assessment instance.

    Parameters
    ----------
    assessment : Assessment model instance (must have report_json populated)

    Returns
    -------
    dict  — ParsedReport  (see module docstring for keys)
    """
    report_json = assessment.report_json or {}

    if not report_json:
        logger.warning(
            "parse_report: report_json is empty for assessment_id=%s",
            assessment.id,
        )

    # --- Scale levels & scores ---
    depression_info = _extract_scale_info(report_json, "depression")
    anxiety_info    = _extract_scale_info(report_json, "anxiety")
    stress_info     = _extract_scale_info(report_json, "stress")

    # --- Emotions ---
    dominant_emotion = _extract_dominant_emotion(report_json)
    scale_emotions   = _extract_scale_emotions(report_json)

    # --- Open-ended feeling analysis ---
    emotional_summary, emotion_labels = _extract_feeling_analysis(report_json)

    parsed = {
        # Severity levels
        "depression_level": depression_info["level"],
        "anxiety_level":    anxiety_info["level"],
        "stress_level":     stress_info["level"],

        # Raw numeric scores (useful for comparison)
        "depression_score": depression_info["score"],
        "anxiety_score":    anxiety_info["score"],
        "stress_score":     stress_info["score"],

        # Emotion data
        "dominant_emotion":  dominant_emotion,
        "scale_emotions":    scale_emotions,   # per-scale breakdown
        "emotional_summary": emotional_summary,
        "emotion_labels":    emotion_labels,
    }

    logger.info(
        "parse_report: parsed assessment_id=%s | dep=%s anx=%s str=%s emotion=%s",
        assessment.id,
        parsed["depression_level"],
        parsed["anxiety_level"],
        parsed["stress_level"],
        parsed["dominant_emotion"],
    )

    return parsed
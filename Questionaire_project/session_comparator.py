"""
session_comparator.py
=====================
Responsibility: Compare the current assessment with the student's last 2
completed assessments and describe what has changed (improved, worsened,
or stayed the same).

This module only does comparison logic — no API calls, no DB writes.

Public API
----------
    compare_with_past_sessions(current_assessment, user) -> ComparisonResult

    ComparisonResult (dict):
        past_sessions_found : int          (0, 1, or 2)
        comparisons         : list[dict]   one entry per past session
        overall_trend       : str          "improving" | "worsening" | "stable" | "mixed" | "no_data"
        summary             : str          human-readable description
"""

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk level ordering — higher number = more severe
# ---------------------------------------------------------------------------

SEVERITY_ORDER: dict[str, int] = {
    "normal":     0,
    "low":        0,
    "mild":       1,
    "borderline": 2,
    "moderate":   3,
    "high":       4,
    "severe":     4,
    "extreme":    5,
}


def _severity_rank(level: str) -> int:
    """Convert a risk level string to a numeric rank for comparison."""
    return SEVERITY_ORDER.get((level or "").strip().lower(), 0)


def _direction(current_rank: int, past_rank: int) -> str:
    """
    Determine whether a scale has improved, worsened, stayed stable (healthy),
    or shown no improvement (persisting at a concerning level).

    Returns: "improved" | "worsened" | "stable" | "no_improvement"

    Rules:
        - improved       : rank went down  (e.g. moderate → low)
        - worsened       : rank went up    (e.g. low → severe)
        - stable         : rank unchanged AND rank == 0  (low/normal — genuinely fine)
        - no_improvement : rank unchanged AND rank  > 0  (moderate/severe persisting)
    """
    if current_rank < past_rank:
        return "improved"
    elif current_rank > past_rank:
        return "worsened"
    else:
        if current_rank == 0:
            return "stable"         # low/normal holding steady → genuinely healthy
        else:
            return "no_improvement" # moderate/severe/high plateau → concerning


# ---------------------------------------------------------------------------
# Internal: fetch past sessions
# ---------------------------------------------------------------------------

def _fetch_past_sessions(current_assessment, user, limit: int = 2):
    """
    Retrieve the last `limit` completed assessments for the same user,
    excluding the current one, ordered most-recent-first.

    Works for both authenticated users and anonymous session users.
    """
    # Import here to avoid circular imports
    from .models import Assessment  # adjust import path if needed

    if user and user.is_authenticated:
        # Authenticated: look up by user account
        qs = (
            Assessment.objects
            .filter(user=user, is_completed=True)
            .exclude(id=current_assessment.id)
            .order_by("-finalized_at")
        )
    else:
        # Anonymous: look up by session key
        qs = (
            Assessment.objects
            .filter(
                session_key=current_assessment.session_key,
                is_completed=True,
            )
            .exclude(id=current_assessment.id)
            .order_by("-finalized_at")
        )

    past = list(qs[:limit])
    logger.info(
        "_fetch_past_sessions: found %d past session(s) for assessment_id=%s",
        len(past), current_assessment.id,
    )
    return past


# ---------------------------------------------------------------------------
# Internal: extract snapshot from a single assessment
# ---------------------------------------------------------------------------

def _extract_snapshot(assessment) -> dict:
    """
    Pull the key metrics we care about from an Assessment instance.

    Returns a flat dict so comparison logic stays simple.
    """
    report_json = assessment.report_json or {}
    feeling = report_json.get("feeling_analysis", {})
    labels_raw = feeling.get("concern_feeling_label", {})

    if isinstance(labels_raw, dict):
        emotion_labels = sorted(labels_raw.keys())
    elif isinstance(labels_raw, list):
        emotion_labels = [str(l) for l in labels_raw]
    else:
        emotion_labels = []

    return {
        "assessment_id":    assessment.id,
        "finalized_at":     assessment.finalized_at,
        "depression_level": (assessment.depression_risk_level or "unknown").lower(),
        "anxiety_level":    (assessment.anxiety_risk_level or "unknown").lower(),
        "stress_level":     (assessment.stress_risk_level or "unknown").lower(),
        "depression_score": assessment.depression_score or 0,
        "anxiety_score":    assessment.anxiety_score or 0,
        "stress_score":     assessment.stress_score or 0,
        "emotion_labels":   emotion_labels,
    }


# ---------------------------------------------------------------------------
# Internal: compare two snapshots
# ---------------------------------------------------------------------------

def _compare_snapshots(current: dict, past: dict) -> dict:
    """
    Compare the current session snapshot against one past session snapshot.

    Returns a detailed comparison dict.
    """
    scales = ["depression", "anxiety", "stress"]
    scale_comparisons = {}

    directions = []  # collect all directions to compute overall trend later

    for scale in scales:
        current_level = current[f"{scale}_level"]
        past_level    = past[f"{scale}_level"]
        current_rank  = _severity_rank(current_level)
        past_rank     = _severity_rank(past_level)
        direction     = _direction(current_rank, past_rank)

        # Score delta (negative = lower score = better for all three scales)
        score_delta = current[f"{scale}_score"] - past[f"{scale}_score"]

        scale_comparisons[scale] = {
            "current_level": current_level,
            "past_level":    past_level,
            "direction":     direction,        # "improved" | "worsened" | "stable"
            "score_delta":   score_delta,      # e.g. -5 means 5 points lower now
        }
        directions.append(direction)

    # --- Emotion label comparison ---
    current_labels = set(current["emotion_labels"])
    past_labels    = set(past["emotion_labels"])
    new_concerns   = list(current_labels - past_labels)   # appeared in current
    resolved       = list(past_labels - current_labels)   # gone in current
    persistent     = list(current_labels & past_labels)   # still present

    # --- Overall trend for this single comparison ---
    improved_count       = directions.count("improved")
    worsened_count       = directions.count("worsened")
    no_improvement_count = directions.count("no_improvement")
    stable_count         = directions.count("stable")

    if improved_count > worsened_count and improved_count >= 2:
        trend = "improving"
    elif worsened_count > improved_count and worsened_count >= 2:
        trend = "worsening"
    elif no_improvement_count >= 2:
        trend = "no_improvement"
    elif improved_count == worsened_count and improved_count > 0:
        trend = "mixed"
    else:
        trend = "stable"

    # --- Human-readable per-scale description (detailed, for therapist script) ---
    description_parts = []
    for scale, info in scale_comparisons.items():
        d = info["direction"]
        cur = info["current_level"]
        prev = info["past_level"]
        if d == "improved":
            description_parts.append(
                f"{scale.title()} has improved from {prev} to {cur}"
            )
        elif d == "worsened":
            description_parts.append(
                f"{scale.title()} has worsened from {prev} to {cur}"
            )
        elif d == "no_improvement":
            description_parts.append(
                f"{scale.title()} shows no improvement, remaining at {cur}"
            )
        else:  # stable
            description_parts.append(
                f"{scale.title()} is stable at {cur} (healthy range)"
            )


    if new_concerns:
        description_parts.append(
            f"New concerns identified: {', '.join(new_concerns)}"
        )
    if resolved:
        description_parts.append(
            f"Concerns no longer detected: {', '.join(resolved)}"
        )
    if persistent:
        description_parts.append(
            f"Ongoing concerns: {', '.join(persistent)}"
        )

    past_date = past["finalized_at"].strftime("%d %b %Y") if past["finalized_at"] else "previous session"

    return {
        "past_assessment_id": past["assessment_id"],
        "past_session_date":  past_date,
        "scale_comparisons":  scale_comparisons,
        "emotion_changes": {
            "new_concerns": new_concerns,
            "resolved":     resolved,
            "persistent":   persistent,
        },
        "trend":       trend,
        "description": ". ".join(description_parts) + ".",
    }


# ---------------------------------------------------------------------------
# Internal: compute overall trend across multiple comparisons
# ---------------------------------------------------------------------------

def _compute_overall_trend(comparisons: list[dict]) -> str:
    """
    Given a list of comparison results (one per past session compared),
    determine the single overall trend label.
    """
    if not comparisons:
        return "no_data"

    trends = [c["trend"] for c in comparisons]
    if all(t == "improving" for t in trends):
        return "improving"
    if all(t == "worsening" for t in trends):
        return "worsening"
    if all(t == "stable" for t in trends):
        return "stable"
    if all(t == "no_improvement" for t in trends):
        return "no_improvement"
    return "mixed"


def _build_overall_summary(overall_trend: str, comparisons: list[dict]) -> str:
    """
    Build a short, human-readable paragraph summarising the trend.
    """
    if not comparisons:
        return (
            "This appears to be your first assessment. We have no previous sessions "
            "to compare against, but your results have been recorded for future tracking."
        )

    trend_sentences = {
        "improving": (
            "Compared to your previous session(s), your mental health indicators show "
            "a positive trend. Your efforts are making a difference — keep going."
        ),
        "worsening": (
            "Compared to your previous session(s), some indicators have moved in a more "
            "concerning direction. Please take the recommendations seriously and consider "
            "reaching out to a counselor."
        ),
        "stable": (
            "Your mental health indicators have remained in a healthy range compared to "
            "previous session(s). Stability here is a good sign — continue building "
            "the habits that are working for you."
        ),
        "no_improvement": (
            "Compared to your previous session(s), your mental health indicators have not "
            "improved and remain at a concerning level. This pattern deserves attention — "
            "please consider speaking with a counselor or mental health professional."
        ),
        "mixed": (
            "Your results show a mixed picture compared to previous session(s) — some areas "
            "have improved while others need more attention. Focus on the areas that have "
            "worsened and celebrate progress where it has occurred."
        ),
    }

    base = trend_sentences.get(overall_trend, "Your results have been compared with previous sessions.")

    # Append a detailed per-scale breakdown from the most recent comparison
    if comparisons:
        most_recent = comparisons[0]
        scale_detail = most_recent["description"]   # e.g. "Depression has worsened from low to moderate. Anxiety shows no improvement, remaining at moderate. Stress is stable at low (healthy range)."
        base += f" Specifically, compared to your session on {most_recent['past_session_date']}: {scale_detail}"

    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_with_past_sessions(current_assessment, user) -> dict:
    """
    Compare the current completed assessment with the last 2 past sessions.

    Parameters
    ----------
    current_assessment : Assessment model instance (just completed)
    user               : request.user (may be AnonymousUser)

    Returns
    -------
    dict with keys:
        past_sessions_found : int
        comparisons         : list[dict]   (one entry per past session)
        overall_trend       : str
        summary             : str
    """
    current_snapshot = _extract_snapshot(current_assessment)
    past_assessments = _fetch_past_sessions(current_assessment, user, limit=2)

    if not past_assessments:
        return {
            "past_sessions_found": 0,
            "comparisons":         [],
            "overall_trend":       "no_data",
            "summary":             _build_overall_summary("no_data", []),
        }

    comparisons = []
    for past_assessment in past_assessments:
        past_snapshot = _extract_snapshot(past_assessment)
        comparison    = _compare_snapshots(current_snapshot, past_snapshot)
        comparisons.append(comparison)
        logger.info(
            "compare_with_past_sessions: compared assessment_id=%s vs past_id=%s trend=%s",
            current_assessment.id, past_assessment.id, comparison["trend"],
        )

    overall_trend = _compute_overall_trend(comparisons)
    summary       = _build_overall_summary(overall_trend, comparisons)

    return {
        "past_sessions_found": len(past_assessments),
        "comparisons":         comparisons,
        "overall_trend":       overall_trend,
        "summary":             summary,
    }
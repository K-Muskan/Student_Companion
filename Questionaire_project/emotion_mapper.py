"""
emotion_mapper.py
=================
Responsibility: Map a detected facial emotion to mental health condition(s).

The 7 possible emotions from DeepFace are:
    sad, fear, angry, disgust, surprise, neutral, happy

Each maps to zero or more of: depression, anxiety, stress

This data is taken directly from your recommendations.py config:
    "emotion_to_condition": { "sad": ["depression"], ... }

Public API
----------
    map_emotion_to_conditions(emotion: str) -> list[str]
        e.g. map_emotion_to_conditions("angry") -> ["stress", "depression"]

    get_facial_note(emotion: str) -> str
        Returns the human-readable note explaining the facial expression finding.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static mapping (mirrors your recommendations.py / JSON config)
# ---------------------------------------------------------------------------

EMOTION_TO_CONDITIONS: dict[str, list[str]] = {
    "sad":      ["depression"],
    "fear":     ["anxiety"],
    "angry":    ["stress", "depression"],
    "disgust":  ["stress", "depression"],
    "surprise": ["anxiety"],
    "neutral":  [],
    "happy":    [],
}

FACIAL_NOTES: dict[str, str] = {
    "sad":      (
        "Your facial expressions reflected sadness, which aligns with "
        "the depression indicators we detected."
    ),
    "fear":     (
        "Your facial expressions showed signs of fear and worry, consistent "
        "with the anxiety levels in your responses."
    ),
    "angry":    (
        "Your facial expressions reflected frustration and tension, which "
        "supports the stress and depression indicators."
    ),
    "disgust":  (
        "Your facial expressions showed discomfort, which is consistent "
        "with your stress levels."
    ),
    "surprise": (
        "Your facial expressions showed heightened alertness, which aligns "
        "with the anxiety detected."
    ),
    "neutral":  (
        "Your facial expressions appeared calm, though your responses indicate "
        "inner difficulty that deserves attention."
    ),
    "happy":    (
        "Your facial expressions showed positivity, which may reflect your "
        "resilience — or possibly a way of coping. Either way, your feelings "
        "inside matter most."
    ),
}

# Severity progression order
_SEVERITY_ORDER = ["low", "moderate", "severe"]

def bump_severity(level: str) -> str:
    """
    Increase a severity level by one step due to emotion-condition mapping.
    
    low      -> moderate
    moderate -> severe
    severe   -> severe  (already at maximum, no change)
    
    Parameters
    ----------
    level : str  one of "low", "moderate", "severe"

    Returns
    -------
    str  — the bumped level
    """
    key = (level or "").strip().lower()
    try:
        idx = _SEVERITY_ORDER.index(key)
    except ValueError:
        logger.warning("bump_severity: unrecognised level '%s', returning as-is", level)
        return level
    bumped = _SEVERITY_ORDER[min(idx + 1, len(_SEVERITY_ORDER) - 1)]
    logger.debug("bump_severity: '%s' -> '%s'", key, bumped)
    return bumped
    
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_emotion_to_conditions(emotion: str) -> list[str]:
    """
    Given a dominant facial emotion, return the list of mental health
    conditions it is associated with.

    Parameters
    ----------
    emotion : str
        One of: sad, fear, angry, disgust, surprise, neutral, happy
        (case-insensitive; unknown values default to empty list)

    Returns
    -------
    list[str]  e.g. ["stress", "depression"]  or  []
    """
    key = (emotion or "").strip().lower()
    conditions = EMOTION_TO_CONDITIONS.get(key, [])

    if key not in EMOTION_TO_CONDITIONS:
        logger.warning(
            "map_emotion_to_conditions: unrecognised emotion '%s', returning []", emotion
        )

    logger.debug(
        "map_emotion_to_conditions: emotion='%s' -> conditions=%s", key, conditions
    )
    return conditions


def get_facial_note(emotion: str) -> str:
    """
    Return the human-readable sentence describing what the facial expression
    result means in the context of the assessment.

    Parameters
    ----------
    emotion : str  (case-insensitive)

    Returns
    -------
    str  — the facial note, or a generic fallback.
    """
    key = (emotion or "").strip().lower()
    return FACIAL_NOTES.get(
        key,
        "Your facial expressions were noted during the assessment.",
    )
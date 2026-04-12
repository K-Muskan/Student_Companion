"""
recommendation_fetcher.py
=========================
Responsibility: Fetch the correct recommendations (tips + message + summary)
for each mental health scale based on severity level.

The recommendations data lives in your recommendations.py JSON config under
the "recommendations" key.  This module reads that config and returns
structured recommendation data for a given (scale, severity_level) pair.

Public API
----------
    fetch_recommendations(depression_level, anxiety_level, stress_level) -> dict

    Example return value:
    {
        "depression": {
            "level": "moderate",
            "summary": "You are experiencing moderate depression...",
            "tips": ["Follow a simple daily routine ...", ...],
            "message": "What you are feeling is real and valid..."
        },
        "anxiety": { ... },
        "stress": { ... },
    }
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedded recommendations data
# (Copied from your recommendations.py JSON so this module is self-contained.
#  If you ever move this to a DB or separate file, just update RECOMMENDATIONS.)
# ---------------------------------------------------------------------------

RECOMMENDATIONS: dict = {
    "depression": {
        "low": {
            "summary": (
                "You are experiencing mild depressive feelings. "
                "Small, consistent habits can make a real difference."
            ),
            "tips": [
                "Take a short walk outdoors daily — sunlight and movement naturally lift your mood",
                "Do one thing you enjoy each day, even briefly",
                "Write 3 things you are grateful for each evening",
                "Stay connected — reach out to a friend or family member regularly",
                "Maintain a consistent sleep schedule",
            ],
            "message": (
                "These feelings are temporary. With small steps and self-care, "
                "brighter days are ahead."
            ),
        },
        "moderate": {
            "summary": (
                "You are experiencing moderate depression that is affecting your daily life. "
                "Focused support can help you through this."
            ),
            "tips": [
                "Follow a simple daily routine to restore a sense of control",
                "Engage in physical activity, even a 15-minute walk",
                "Talk to someone you trust about how you are feeling",
                "Try mindfulness or breathing exercises for 10 minutes daily",
                "Consider speaking with a university counselor or therapist — CBT is very effective",
            ],
            "message": (
                "What you are feeling is real and valid. You do not have to carry this "
                "alone — reaching out is a sign of strength."
            ),
        },
        "severe": {
            "summary": (
                "You are experiencing severe depression. Please seek professional support "
                "— recovery is possible and you deserve help."
            ),
            "tips": [
                "Please speak with a mental health professional as soon as possible",
                "Tell a trusted person how you are feeling today",
                "Focus only on basic self-care: eating, sleeping, and hydrating",
                "Avoid making major decisions during this time",
                "If you are in crisis — Umang Helpline (Pakistan): 0317-4288665",
            ],
            "message": (
                "You are in real pain right now, and that pain matters. Please reach out "
                "— you are not alone and help is available."
            ),
        },
    },

    "anxiety": {
        "low": {
            "summary": (
                "Your anxiety is at a manageable level. "
                "Simple habits will keep it in a healthy range."
            ),
            "tips": [
                "Practice box breathing when you feel tense: inhale 4, hold 4, exhale 4",
                "Limit caffeine, especially in the evenings",
                "Spend time in nature or do light stretching daily",
                "Keep a worry journal — write concerns down, then close the notebook",
            ],
            "message": (
                "A little anxiety is natural. You are managing it well "
                "— keep up these healthy habits."
            ),
        },
        "moderate": {
            "summary": (
                "Your anxiety is noticeably affecting your daily life. "
                "Structured coping strategies can help you regain balance."
            ),
            "tips": [
                "Practice deep breathing or the 4-7-8 technique daily",
                "Challenge anxious thoughts: ask yourself 'Is this likely? Is this based on facts?'",
                "Engage in regular physical exercise — it directly reduces anxiety",
                "Reduce caffeine and limit news or social media intake",
                "Consider speaking with a counselor — CBT for anxiety is highly effective",
            ],
            "message": (
                "Anxiety tells you stories that are not always true. With the right tools "
                "and support, you can rewrite that narrative."
            ),
        },
        "severe": {
            "summary": (
                "You are experiencing severe anxiety. Please seek professional support "
                "— effective treatment is available."
            ),
            "tips": [
                "Please consult a mental health professional or doctor promptly",
                "Use grounding: focus on 5 things you can see, 4 you can touch, 3 you can hear",
                "Avoid making big decisions when anxiety is at its peak",
                "Do not isolate — stay close to people who make you feel safe",
                "If you are in crisis — Umang Helpline (Pakistan): 0317-4288665",
            ],
            "message": (
                "Living with severe anxiety is exhausting. But with the right support, "
                "things genuinely can get better — please reach out."
            ),
        },
    },

    "stress": {
        "low": {
            "summary": "Your stress levels are healthy. You are managing life's demands well.",
            "tips": [
                "Maintain your current routines and self-care habits",
                "Take short breaks every 90 minutes during study or work",
                "Stay physically active and keep social connections strong",
            ],
            "message": (
                "You are doing well. Keep investing in the habits that are working for you."
            ),
        },
        "moderate": {
            "summary": (
                "You are under noticeable stress that is affecting your wellbeing. "
                "Targeted changes can help restore balance."
            ),
            "tips": [
                "Identify your top stressors and write one action you can take for each",
                "Use a planner to reduce the feeling of overwhelm",
                "Learn to say no — protect your time and energy",
                "Take at least 30 minutes daily for something relaxing and enjoyable",
                "Talk to someone — a friend, mentor, or counselor",
            ],
            "message": (
                "Stress at this level is your mind asking for support. "
                "One small step today can shift things significantly."
            ),
        },
        "severe": {
            "summary": (
                "You are experiencing severe stress that is likely impacting your health. "
                "Immediate attention is needed."
            ),
            "tips": [
                "Prioritize sleep above everything else right now",
                "Reduce or delegate non-essential responsibilities where possible",
                "Speak with an academic advisor if studies are the primary source of stress",
                "Please consult a mental health professional — chronic high stress is serious",
                "If you are in crisis — Umang Helpline (Pakistan): 0317-4288665",
            ],
            "message": (
                "You have been carrying far too much for too long. "
                "It is okay to ask for help — that is wisdom, not weakness."
            ),
        },
    },
}

# ---------------------------------------------------------------------------
# Level normalisation
# Some analyzers return "normal" or "mild" — map those to our three buckets.
# ---------------------------------------------------------------------------

LEVEL_NORMALISATION: dict[str, str] = {
    "normal":     "low",
    "mild":       "low",
    "borderline": "moderate",
    "high":       "severe",
    "extreme":    "severe",
    # Already valid — kept for completeness
    "low":        "low",
    "moderate":   "moderate",
    "severe":     "severe",
}


def _normalise_level(level: str) -> str:
    """Convert any risk-level string to one of: low | moderate | severe."""
    key = (level or "low").strip().lower()
    normalised = LEVEL_NORMALISATION.get(key, "low")
    if key != normalised:
        logger.debug("_normalise_level: '%s' -> '%s'", key, normalised)
    return normalised


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_recommendations(
    depression_level: str,
    anxiety_level: str,
    stress_level: str,
) -> dict:
    """
    Fetch the recommendations block for each scale based on severity level.

    Parameters
    ----------
    depression_level : str  e.g. "moderate"
    anxiety_level    : str  e.g. "low"
    stress_level     : str  e.g. "severe"

    Returns
    -------
    dict with keys "depression", "anxiety", "stress".
    Each value is a dict with:
        level   : str       (normalised level used for lookup)
        summary : str
        tips    : list[str]
        message : str
    """
    results = {}

    for scale, raw_level in [
        ("depression", depression_level),
        ("anxiety",    anxiety_level),
        ("stress",     stress_level),
    ]:
        level = _normalise_level(raw_level)
        block = RECOMMENDATIONS.get(scale, {}).get(level)

        if block is None:
            # Should never happen, but guard defensively
            logger.warning(
                "fetch_recommendations: no data for scale='%s' level='%s'", scale, level
            )
            block = {
                "summary": f"No recommendations available for {scale} at level {level}.",
                "tips": [],
                "message": "Please speak with a mental health professional for guidance.",
            }

        results[scale] = {
            "level":   level,
            "summary": block["summary"],
            "tips":    block["tips"],
            "message": block["message"],
        }

        logger.debug(
            "fetch_recommendations: scale=%s level=%s tip_count=%d",
            scale, level, len(block["tips"]),
        )

    return results
"""
pipeline_orchestrator.py
========================
Responsibility: Coordinate the entire post-assessment analysis pipeline.

This is the ONLY file that views.py needs to call. It ties together:
    1. report_parser         — extract structured data from the assessment
    2. emotion_mapper        — map dominant emotion to mental health conditions
    3. recommendation_fetcher— get the right tips based on severity levels
    4. consoling_generator   — generate empathetic messages via Claude API
    5. session_comparator    — compare with the last 2 past sessions
    6. therapist_narrator    — generate AI therapist monologue via Gemini   ← NEW
    7. DB write              — save the combined result to AnalysisResult model

Public API
----------
    run_pipeline(assessment, user) -> AnalysisResult instance
        (or raises PipelineError on unrecoverable failure)
"""

import logging

from .report_parser          import parse_report
from .emotion_mapper import map_emotion_to_conditions, get_facial_note, bump_severity
from .recommendation_fetcher import fetch_recommendations
from .session_comparator     import compare_with_past_sessions
from .therapist_narrator     import generate_therapist_script          # ← NEW
from .models                 import AnalysisResult


logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when a critical step in the pipeline fails."""


# ---------------------------------------------------------------------------
# Internal: each step is its own function so it's easy to test independently
# ---------------------------------------------------------------------------

def _step_parse(assessment) -> dict:
    """
    Step 1: Parse the completed assessment into a structured dictionary.
    """
    logger.info("[Pipeline] Step 1 — Parsing report for assessment_id=%s", assessment.id)
    parsed = parse_report(assessment)
    logger.info(
        "[Pipeline] Parsed: dep=%s anx=%s str=%s emotion=%s",
        parsed["depression_level"], parsed["anxiety_level"],
        parsed["stress_level"], parsed["dominant_emotion"],
    )
    return parsed


def _step_map_emotion(parsed: dict) -> dict:
    """
    Step 2: Map the dominant emotion to mental health condition(s).
    Returns a dict with:
        conditions   : list[str]  e.g. ["stress", "depression"]
        facial_note  : str        human-readable note about the facial expression
    """
    logger.info("[Pipeline] Step 2 — Mapping emotion '%s'", parsed["dominant_emotion"])
    conditions  = map_emotion_to_conditions(parsed["dominant_emotion"])
    facial_note = get_facial_note(parsed["dominant_emotion"])
    return {
        "conditions":  conditions,
        "facial_note": facial_note,
    }


def _step_fetch_recommendations(parsed: dict) -> dict:
    """
    Step 3: Fetch recommendations based on depression/anxiety/stress levels.
    """
    logger.info(
        "[Pipeline] Step 3 — Fetching recommendations dep=%s anx=%s str=%s",
        parsed["depression_level"], parsed["anxiety_level"], parsed["stress_level"],
    )
    return fetch_recommendations(
        depression_level=parsed["depression_level"],
        anxiety_level=parsed["anxiety_level"],
        stress_level=parsed["stress_level"],
    )



def _step_compare_sessions(assessment, user) -> dict:
    """
    Step 5: Compare with the last 2 past sessions.
    """
    logger.info(
        "[Pipeline] Step 5 — Comparing with past sessions for assessment_id=%s",
        assessment.id,
    )
    return compare_with_past_sessions(assessment, user)


def _step_generate_therapist_script(instance: "AnalysisResult") -> str:
    logger.info(
        "[Pipeline] Step 6 — Generating therapist script for assessment_id=%s",
        instance.assessment_id,
    )
    try:
        result = generate_therapist_script(instance)
        # generate_therapist_script returns a dict — extract just the script text
        script = result.get("therapist_response", "") if isinstance(result, dict) else str(result)
        logger.info(
            "[Pipeline] Therapist script generated — %d chars for assessment_id=%s",
            len(script), instance.assessment_id,
        )
        return script
    except Exception as exc:
        logger.warning(
            "[Pipeline] Therapist script generation failed for assessment_id=%s: %s",
            instance.assessment_id, exc,
        )
        return ""


def _step_assemble_result(
    assessment,
    parsed: dict,
    emotion_mapping: dict,
    recommendations: dict,
    comparison: dict,
) -> dict:
    """
    Step 7: Assemble everything into a single result dict.

    If the dominant emotion maps to a condition, the corresponding severity
    level is bumped by one step (low→moderate, moderate→severe, severe stays).
    """
    depression_level = parsed["depression_level"]
    anxiety_level    = parsed["anxiety_level"]
    stress_level     = parsed["stress_level"]

    conditions = emotion_mapping["conditions"]   # e.g. ["stress", "depression"]

    if "depression" in conditions:
        original = depression_level
        depression_level = bump_severity(depression_level)
        logger.info(
            "[Pipeline] Depression level bumped by emotion mapping: %s -> %s",
            original, depression_level,
        )

    if "anxiety" in conditions:
        original = anxiety_level
        anxiety_level = bump_severity(anxiety_level)
        logger.info(
            "[Pipeline] Anxiety level bumped by emotion mapping: %s -> %s",
            original, anxiety_level,
        )

    if "stress" in conditions:
        original = stress_level
        stress_level = bump_severity(stress_level)
        logger.info(
            "[Pipeline] Stress level bumped by emotion mapping: %s -> %s",
            original, stress_level,
        )

    return {
        # --- Current session data (levels may be bumped) ---
        "depression_level": depression_level,
        "anxiety_level":    anxiety_level,
        "stress_level":     stress_level,
        "dominant_emotion": parsed["dominant_emotion"],
        "scale_emotions":   parsed["scale_emotions"],
        "emotional_summary":parsed["emotional_summary"],
        "emotion_labels":   parsed["emotion_labels"],

        # --- Emotion mapping ---
        "emotion_conditions": conditions,
        "facial_note":        emotion_mapping["facial_note"],

        # --- Recommendations ---
        "recommendations": recommendations,

        # --- Past session comparison ---
        "comparison": comparison,
    }


def _step_save_to_db(assessment, result_data: dict, therapist_script: str = "") -> "AnalysisResult":
    """
    Step 8 (was 7): Save (or update) the combined result to the AnalysisResult DB table.

    therapist_script is passed in separately because it is generated AFTER
    the first save (it needs the populated instance as input to Gemini).
    On the very first run, we do two saves:
        save #1 — all pipeline data (no script yet)
        save #2 — adds therapist_script
    On re-runs, update_or_create handles both in one shot because the script
    is already available from _step_generate_therapist_script.
    """
    logger.info(
        "[Pipeline] Step 8 — Saving AnalysisResult for assessment_id=%s", assessment.id
    )

    instance, created = AnalysisResult.objects.update_or_create(
        assessment=assessment,
        defaults={
            # Current levels
            "depression_level": result_data["depression_level"],
            "anxiety_level":    result_data["anxiety_level"],
            "stress_level":     result_data["stress_level"],

            # Emotion data
            "dominant_emotion":   result_data["dominant_emotion"],
            "scale_emotions":     result_data["scale_emotions"],
            "emotional_summary":  result_data["emotional_summary"],
            "emotion_labels":     result_data["emotion_labels"],
            "emotion_conditions": result_data["emotion_conditions"],
            "facial_note":        result_data["facial_note"],

            # Recommendations
            "recommendations_json": result_data["recommendations"],

            

            # Comparison
            "past_sessions_found": result_data["comparison"]["past_sessions_found"],
            "comparison_results":  result_data["comparison"]["comparisons"],
            "overall_trend":       result_data["comparison"]["overall_trend"],
            "comparison_summary":  result_data["comparison"]["summary"],

            # Therapist script                                              ← NEW
            "therapist_script": therapist_script,
        },
    )

    action = "created" if created else "updated"
    logger.info(
        "[Pipeline] AnalysisResult %s (id=%s) for assessment_id=%s",
        action, instance.id, assessment.id,
    )
    return instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(assessment, user) -> "AnalysisResult":
    """
    Run the full post-assessment analysis pipeline.

    Parameters
    ----------
    assessment : Assessment model instance (must have is_completed=True)
    user       : Django user (request.user — may be AnonymousUser)

    Returns
    -------
    AnalysisResult  — the saved DB instance containing all pipeline output.

    Raises
    ------
    PipelineError  — if a critical step fails unrecoverably.
    """
    logger.info(
        "=== [Pipeline] START for assessment_id=%s user=%s ===",
        assessment.id,
        getattr(user, "id", "anonymous"),
    )

    if not assessment.is_completed:
        raise PipelineError(
            f"Assessment {assessment.id} is not yet completed. Pipeline aborted."
        )

    try:
        # Step 1: Parse
        parsed = _step_parse(assessment)

        # Step 2: Emotion mapping
        emotion_mapping = _step_map_emotion(parsed)

        # Step 3: Recommendations
        recommendations = _step_fetch_recommendations(parsed)

        # Step 4: Consoling messages
       # consoling = _step_generate_consoling(parsed)

        # Step 5: Past session comparison
        comparison = _step_compare_sessions(assessment, user)

        # Step 6 (NEW): Therapist script
        # ─────────────────────────────────────────────────────────────────────
        # We need a populated AnalysisResult instance before calling Gemini,
        # because generate_therapist_script() reads fields like facial_note,
        # consoling_summary_response, consoling_label_responses, etc.
        # Strategy:
        #   a) Assemble result_data (no script yet)
        #   b) Do a preliminary save — gets us a real instance with all fields set
        #   c) Call Gemini with that instance → script string
        #   d) Patch the instance with the script (one extra UPDATE query)
        # ─────────────────────────────────────────────────────────────────────

        # Step 7: Assemble (without script — script needs the instance first)
        result_data = _step_assemble_result(
            assessment, parsed, emotion_mapping, recommendations, comparison
        )

        # Step 8a: Preliminary save (therapist_script="" placeholder)
        instance = _step_save_to_db(assessment, result_data, therapist_script="")

        # Step 6: Now generate the therapist script using the populated instance
        therapist_script = _step_generate_therapist_script(instance)

        # Step 8b: Patch the script onto the already-saved instance
        if therapist_script:
            instance.therapist_script = therapist_script
            instance.save(update_fields=["therapist_script"])
            logger.info(
                "[Pipeline] therapist_script patched onto AnalysisResult id=%s", instance.id
            )

        logger.info(
            "=== [Pipeline] COMPLETE for assessment_id=%s trend=%s has_script=%s ===",
            assessment.id,
            comparison["overall_trend"],
            bool(therapist_script),
        )
        return instance

    except PipelineError:
        raise  # re-raise our own errors as-is

    except Exception as exc:
        logger.exception(
            "[Pipeline] Unexpected failure for assessment_id=%s: %s",
            assessment.id, exc,
        )
        raise PipelineError(
            f"Pipeline failed for assessment {assessment.id}: {exc}"
        ) from exc
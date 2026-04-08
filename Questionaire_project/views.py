import json
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .emotion_services import (
    build_emotion_summary,
    build_emotion_timeline_summary,
    build_scale_emotion_summary,
    empty_emotion_summary,
)
from .models import Assessment, Answer, Question
from .depression_analyzer import analyze_depression
from .stress_analyzer import analyze_stress
from .anxiety_analyzer import analyze_anxiety
from .feeling_analyzer import analyze_open_ended_text

logger = logging.getLogger(__name__)

# ============================================================================
# SCALE DEFINITIONS
# ID scheme:
#   1        = Depression title screen
#   2–22     = BDI items 1–21
#   23       = Stress title screen
#   24–33    = PSS-10 items 1–10
#   34       = Anxiety title screen
#   35–55    = BAI items 1–21
#   56       = Final/loading screen
# ============================================================================

BDI_OPTIONS = [
    "Not at all / Does not apply",
    "Mild — occasionally",
    "Moderate — a good part of the time",
    "Severe — most of the time",
]

PSS_OPTIONS = [
    "Never",
    "Almost Never",
    "Sometimes",
    "Fairly Often",
    "Very Often",
]

BAI_OPTIONS = [
    "Not at all",
    "Mildly — it didn't bother me much",
    "Moderately — it wasn't pleasant at times",
    "Severely — it bothered me a lot",
]

PSS_REVERSE_ITEMS = {4, 5, 7, 8}

QUESTIONS = [
    # ── Depression Title Screen ──────────────────────────────────────────────
    {
        "id": 1,
        "scale": "title",
        "is_title_screen": True,
        "is_final": False,
        "title": "Depression Assessment",
        "subtitle": "Beck's Depression Inventory (BDI)",
        "description": (
            "The following 21 statements describe different feelings and attitudes. "
            "For each one, select the statement that best describes how you have been "
            "feeling over the past two weeks, including today."
        ),
        "item_count": 21,
        "scale_item_number": None,
        "max_score": 0,
        "is_reverse_scored": False,
        "options": [],
    },

    # ── BDI Items 1–21 (IDs 2–22) ────────────────────────────────────────────
    {"id": 2,  "scale": "depression", "scale_item_number": 1,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Sadness",               "options": ["I do not feel sad.", "I feel sad.", "I am sad all the time and I can't snap out of it.", "I am so sad and unhappy that I can't stand it."]},
    {"id": 3,  "scale": "depression", "scale_item_number": 2,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Pessimism",              "options": ["I am not particularly discouraged about the future.", "I feel discouraged about the future.", "I feel I have nothing to look forward to.", "I feel the future is hopeless and that things cannot improve."]},
    {"id": 4,  "scale": "depression", "scale_item_number": 3,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Past Failure",           "options": ["I do not feel like a failure.", "I feel I have failed more than the average person.", "As I look back on my life, all I can see is a lot of failures.", "I feel I am a complete failure as a person."]},
    {"id": 5,  "scale": "depression", "scale_item_number": 4,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Loss of Pleasure",      "options": ["I get as much satisfaction out of things as I used to.", "I don't enjoy things the way I used to.", "I don't get real satisfaction out of anything anymore.", "I am dissatisfied or bored with everything."]},
    {"id": 6,  "scale": "depression", "scale_item_number": 5,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Guilty Feelings",       "options": ["I don't feel particularly guilty.", "I feel guilty a good part of the time.", "I feel quite guilty most of the time.", "I feel guilty all of the time."]},
    {"id": 7,  "scale": "depression", "scale_item_number": 6,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Punishment Feelings",   "options": ["I don't feel I am being punished.", "I feel I may be punished.", "I expect to be punished.", "I feel I am being punished."]},
    {"id": 8,  "scale": "depression", "scale_item_number": 7,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Self-Dislike",          "options": ["I don't feel disappointed in myself.", "I am disappointed in myself.", "I am disgusted with myself.", "I hate myself."]},
    {"id": 9,  "scale": "depression", "scale_item_number": 8,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Self-Criticalness",     "options": ["I don't feel I am any worse than anybody else.", "I am critical of myself for my weaknesses or mistakes.", "I blame myself all the time for my faults.", "I blame myself for everything bad that happens."]},
    {"id": 10, "scale": "depression", "scale_item_number": 9,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Suicidal Thoughts",     "options": ["I don't have any thoughts of killing myself.", "I have thoughts of killing myself, but I would not carry them out.", "I would like to kill myself.", "I would kill myself if I had the chance."]},
    {"id": 11, "scale": "depression", "scale_item_number": 10, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Crying",                "options": ["I don't cry any more than usual.", "I cry more now than I used to.", "I cry all the time now.", "I used to be able to cry, but now I can't cry even though I want to."]},
    {"id": 12, "scale": "depression", "scale_item_number": 11, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Agitation",             "options": ["I am no more irritated than I ever was.", "I am slightly more irritated now than usual.", "I am quite annoyed or irritated a good deal of the time.", "I feel irritated all the time."]},
    {"id": 13, "scale": "depression", "scale_item_number": 12, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Loss of Interest",      "options": ["I have not lost interest in other people.", "I am less interested in other people than I used to be.", "I have lost most of my interest in other people.", "I have lost all of my interest in other people."]},
    {"id": 14, "scale": "depression", "scale_item_number": 13, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Indecisiveness",        "options": ["I make decisions about as well as I ever could.", "I put off making decisions more than I used to.", "I have greater difficulty in making decisions than I used to.", "I can't make decisions at all anymore."]},
    {"id": 15, "scale": "depression", "scale_item_number": 14, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Worthlessness",         "options": ["I don't feel that I look any worse than I used to.", "I am worried that I am looking old or unattractive.", "I feel there are permanent changes in my appearance that make me look unattractive.", "I believe that I look ugly."]},
    {"id": 16, "scale": "depression", "scale_item_number": 15, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Loss of Energy",        "options": ["I can work about as well as before.", "It takes an extra effort to get started at doing something.", "I have to push myself very hard to do anything.", "I can't do any work at all."]},
    {"id": 17, "scale": "depression", "scale_item_number": 16, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Sleep Changes",         "options": ["I can sleep as well as usual.", "I don't sleep as well as I used to.", "I wake up 1–2 hours earlier than usual and find it hard to get back to sleep.", "I wake up several hours earlier than I used to and cannot get back to sleep."]},
    {"id": 18, "scale": "depression", "scale_item_number": 17, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Irritability",          "options": ["I don't get more tired than usual.", "I get tired more easily than I used to.", "I get tired from doing almost anything.", "I am too tired to do anything."]},
    {"id": 19, "scale": "depression", "scale_item_number": 18, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Appetite Changes",      "options": ["My appetite is no worse than usual.", "My appetite is not as good as it used to be.", "My appetite is much worse now.", "I have no appetite at all anymore."]},
    {"id": 20, "scale": "depression", "scale_item_number": 19, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Weight Loss",           "options": ["I haven't lost much weight, if any, lately.", "I have lost more than five pounds.", "I have lost more than ten pounds.", "I have lost more than fifteen pounds."]},
    {"id": 21, "scale": "depression", "scale_item_number": 20, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Health Worry",          "options": ["I am no more worried about my health than usual.", "I am worried about physical problems like aches, pains, or upset stomach.", "I am very worried about physical problems and it's hard to think of much else.", "I am so worried about my physical problems that I cannot think of anything else."]},
    {"id": 22, "scale": "depression", "scale_item_number": 21, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Loss of Interest in Sex", "options": ["I have not noticed any recent change in my interest in sex.", "I am less interested in sex than I used to be.", "I have almost no interest in sex.", "I have lost interest in sex completely."]},

    # ── Stress Title Screen ──────────────────────────────────────────────────
    {
        "id": 23,
        "scale": "title",
        "is_title_screen": True,
        "is_final": False,
        "title": "Stress Assessment",
        "subtitle": "Perceived Stress Scale (PSS-10)",
        "description": (
            "The following questions ask about your feelings and thoughts during "
            "the last month. For each question, indicate how often you felt or "
            "thought a certain way."
        ),
        "item_count": 10,
        "scale_item_number": None,
        "max_score": 0,
        "is_reverse_scored": False,
        "options": [],
    },

    # ── PSS-10 Items 1–10 (IDs 24–33) ────────────────────────────────────────
    {"id": 24, "scale": "stress", "scale_item_number": 1,  "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you been upset because of something that happened unexpectedly?",                           "options": PSS_OPTIONS},
    {"id": 25, "scale": "stress", "scale_item_number": 2,  "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt that you were unable to control the important things in your life?",             "options": PSS_OPTIONS},
    {"id": 26, "scale": "stress", "scale_item_number": 3,  "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt nervous and 'stressed'?",                                                         "options": PSS_OPTIONS},
    {"id": 27, "scale": "stress", "scale_item_number": 4,  "max_score": 4, "is_reverse_scored": True,  "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt confident about your ability to handle your personal problems?",                   "options": PSS_OPTIONS},
    {"id": 28, "scale": "stress", "scale_item_number": 5,  "max_score": 4, "is_reverse_scored": True,  "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt that things were going your way?",                                                 "options": PSS_OPTIONS},
    {"id": 29, "scale": "stress", "scale_item_number": 6,  "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you found that you could not cope with all the things that you had to do?",                 "options": PSS_OPTIONS},
    {"id": 30, "scale": "stress", "scale_item_number": 7,  "max_score": 4, "is_reverse_scored": True,  "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you been able to control irritations in your life?",                                        "options": PSS_OPTIONS},
    {"id": 31, "scale": "stress", "scale_item_number": 8,  "max_score": 4, "is_reverse_scored": True,  "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt that you were on top of things?",                                                  "options": PSS_OPTIONS},
    {"id": 32, "scale": "stress", "scale_item_number": 9,  "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you been angered because of things that were outside of your control?",                     "options": PSS_OPTIONS},
    {"id": 33, "scale": "stress", "scale_item_number": 10, "max_score": 4, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "In the last month, how often have you felt difficulties were piling up so high that you could not overcome them?",           "options": PSS_OPTIONS},

    # ── Anxiety Title Screen ─────────────────────────────────────────────────
    {
        "id": 34,
        "scale": "title",
        "is_title_screen": True,
        "is_final": False,
        "title": "Anxiety Assessment",
        "subtitle": "Beck Anxiety Inventory (BAI)",
        "description": (
            "Below is a list of common symptoms of anxiety. "
            "Please carefully read each item in the list. "
            "Indicate how much you have been bothered by each symptom "
            "during the past month, including today."
        ),
        "item_count": 21,
        "scale_item_number": None,
        "max_score": 0,
        "is_reverse_scored": False,
        "options": [],
    },

    # ── BAI Items 1–21 (IDs 35–55) ───────────────────────────────────────────
    {"id": 35, "scale": "anxiety", "scale_item_number": 1,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Numbness or tingling",     "options": BAI_OPTIONS},
    {"id": 36, "scale": "anxiety", "scale_item_number": 2,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Feeling hot",               "options": BAI_OPTIONS},
    {"id": 37, "scale": "anxiety", "scale_item_number": 3,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Wobbliness in legs",        "options": BAI_OPTIONS},
    {"id": 38, "scale": "anxiety", "scale_item_number": 4,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Unable to relax",           "options": BAI_OPTIONS},
    {"id": 39, "scale": "anxiety", "scale_item_number": 5,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Fear of worst happening",  "options": BAI_OPTIONS},
    {"id": 40, "scale": "anxiety", "scale_item_number": 6,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Dizzy or lightheaded",      "options": BAI_OPTIONS},
    {"id": 41, "scale": "anxiety", "scale_item_number": 7,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Heart pounding or racing", "options": BAI_OPTIONS},
    {"id": 42, "scale": "anxiety", "scale_item_number": 8,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Unsteady",                  "options": BAI_OPTIONS},
    {"id": 43, "scale": "anxiety", "scale_item_number": 9,  "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Terrified or afraid",       "options": BAI_OPTIONS},
    {"id": 44, "scale": "anxiety", "scale_item_number": 10, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Nervous",                   "options": BAI_OPTIONS},
    {"id": 45, "scale": "anxiety", "scale_item_number": 11, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Feeling of choking",        "options": BAI_OPTIONS},
    {"id": 46, "scale": "anxiety", "scale_item_number": 12, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Hands trembling",           "options": BAI_OPTIONS},
    {"id": 47, "scale": "anxiety", "scale_item_number": 13, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Shaky or unsteady",         "options": BAI_OPTIONS},
    {"id": 48, "scale": "anxiety", "scale_item_number": 14, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Fear of losing control",   "options": BAI_OPTIONS},
    {"id": 49, "scale": "anxiety", "scale_item_number": 15, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Difficulty in breathing",  "options": BAI_OPTIONS},
    {"id": 50, "scale": "anxiety", "scale_item_number": 16, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Fear of dying",             "options": BAI_OPTIONS},
    {"id": 51, "scale": "anxiety", "scale_item_number": 17, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Scared",                    "options": BAI_OPTIONS},
    {"id": 52, "scale": "anxiety", "scale_item_number": 18, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Indigestion",               "options": BAI_OPTIONS},
    {"id": 53, "scale": "anxiety", "scale_item_number": 19, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Faint or lightheaded",      "options": BAI_OPTIONS},
    {"id": 54, "scale": "anxiety", "scale_item_number": 20, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Face flushed",              "options": BAI_OPTIONS},
    {"id": 55, "scale": "anxiety", "scale_item_number": 21, "max_score": 3, "is_reverse_scored": False, "is_title_screen": False, "is_final": False, "question_text": "Hot or cold sweats",        "options": BAI_OPTIONS},

    # ── Open-Ended Reflection Question ──────────────────────────────────────
    {
        "id": 56,
        "scale": "open_ended",
        "is_title_screen": False,
        "is_final": False,
        "is_open_ended": True,
        "question_text": "Is there something you want to discuss with us? Any story or experience you want to share with us?",
        "scale_item_number": None,
        "max_score": 0,
        "is_reverse_scored": False,
        "options": [],
    },

    # ── Final / Loading Screen ───────────────────────────────────────────────
    {
        "id": 57,
        "scale": "final",
        "is_title_screen": False,
        "is_final": True,
        "question_text": "",
        "scale_item_number": None,
        "max_score": 0,
        "is_reverse_scored": False,
        "options": [],
    },
]

QUESTIONS_BY_ID = {q["id"]: q for q in QUESTIONS}
TOTAL_QUESTIONS = len(QUESTIONS)
FIRST_QID = QUESTIONS[0]["id"]   # 1
LAST_QID  = QUESTIONS[-1]["id"]  # 57
EMOTION_STREAMABLE_SCALES = {
    Question.SCALE_DEPRESSION,
    Question.SCALE_STRESS,
    Question.SCALE_ANXIETY,
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _init_session(session):
    if 'answers' not in session:
        session['answers'] = {}
    if 'assessment_cycle' not in session:
        session['assessment_cycle'] = 1


def _correlation_id(request):
    cid = request.headers.get("X-Request-ID") or request.session.get("correlation_id")
    if not cid:
        cid = uuid.uuid4().hex
        request.session["correlation_id"] = cid
    return cid


def _get_answers(session):
    return session.get('answers', {})


def _set_answer(session, qid, score):
    if 'answers' not in session:
        session['answers'] = {}
    session['answers'][str(qid)] = score
    session.modified = True


def _is_valid_qid(qid):
    return qid in QUESTIONS_BY_ID


def _get_question(qid):
    return QUESTIONS_BY_ID.get(qid)


def _get_or_create_assessment(request):
    """
    Robust version from teammate: uses while-loop cycle to skip completed assessments.
    """
    if not request.session.session_key:
        request.session.save()

    assessment_id = request.session.get("assessment_id")
    if assessment_id:
        assessment = Assessment.objects.filter(id=assessment_id).first()
        if assessment and not assessment.is_completed:
            return assessment

    try:
        cycle = max(1, int(request.session.get("assessment_cycle", 1)))
    except (TypeError, ValueError):
        cycle = 1

    user = request.user if request.user.is_authenticated else None

    with transaction.atomic():
        while True:
            assessment_token = f"{request.session.session_key}:{cycle}"
            assessment, _ = Assessment.objects.get_or_create(
                assessment_token=assessment_token,
                defaults={
                    "user": user,
                    "session_key": request.session.session_key,
                },
            )
            if not assessment.is_completed:
                if assessment.session_key != request.session.session_key:
                    assessment.session_key = request.session.session_key
                    assessment.save(update_fields=["session_key"])
                if user and assessment.user_id != user.id:
                    assessment.user = user
                    assessment.save(update_fields=["user"])
                break
            cycle += 1

    request.session["assessment_id"] = assessment.id
    request.session["assessment_cycle"] = cycle
    request.session.modified = True
    return assessment


def _ensure_questions_in_db():
    """Seed all scale questions in to the DB if not already present."""
    try:
        existing_ids = set(Question.objects.values_list('id', flat=True))
        to_create = []
        for q in QUESTIONS:
            if q["id"] not in existing_ids:
                to_create.append(Question(
                    id=q["id"],
                    video_file="",
                    question_text=q.get("question_text", ""),
                    mse_category=q.get("scale", ""),
                    scale=q.get("scale", ""),
                    scale_item_number=q.get("scale_item_number"),
                    max_score=q.get("max_score", 3),
                    is_reverse_scored=q.get("is_reverse_scored", False),
                    is_title_screen=q.get("is_title_screen", False),
                    is_final=q.get("is_final", False),
                    is_active=True,
                ))
        if to_create:
            Question.objects.bulk_create(to_create, ignore_conflicts=True)
    except Exception:
        logger.exception("question_seed_failed")


def _get_or_seed_question(qid):
    """Get question row or seed it on demand as a fallback."""
    question = Question.objects.filter(id=qid).first()
    if question is not None:
        return question
    if not _is_valid_qid(int(qid)):
        return None
    q = _get_question(int(qid))
    if not q:
        return None
    try:
        question = Question.objects.create(
            id=q["id"],
            video_file="",
            question_text=q.get("question_text", ""),
            mse_category=q.get("scale", ""),
            scale=q.get("scale", ""),
            scale_item_number=q.get("scale_item_number"),
            max_score=q.get("max_score", 3),
            is_reverse_scored=q.get("is_reverse_scored", False),
            is_title_screen=q.get("is_title_screen", False),
            is_final=q.get("is_final", False),
            is_active=True,
        )
        logger.warning("question_seeded_on_demand", extra={"qid": qid})
    except Exception:
        question = Question.objects.filter(id=qid).first()
    return question


def _safe_error_response(message, status=500):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _derive_stream_scale(question, next_qid=None):
    if not question:
        return ""
    scale = question.get("scale", "")
    if scale in EMOTION_STREAMABLE_SCALES:
        return scale
    if question.get("is_title_screen") and next_qid:
        next_question = _get_question(next_qid)
        next_scale = (next_question or {}).get("scale", "")
        if next_scale in EMOTION_STREAMABLE_SCALES:
            return next_scale
    return ""


def _build_question_context(request, qid, assessment=None):
    question = _get_question(qid)
    assessment = assessment or _get_or_create_assessment(request)

    previous_score = _get_answers(request.session).get(str(qid), None)
    if previous_score is None:
        try:
            ans = Answer.objects.get(assessment=assessment, question_id=qid)
            previous_score = ans.answer_score
            if previous_score is not None:
                _set_answer(request.session, str(qid), previous_score)
        except Answer.DoesNotExist:
            pass

    scorable_ids = [
        q["id"] for q in QUESTIONS
        if not q.get("is_title_screen") and not q.get("is_final")
    ]
    answered_count = sum(
        1 for sid in scorable_ids
        if str(sid) in _get_answers(request.session)
    )
    total_scorable = len(scorable_ids)

    scale_questions = [
        q for q in QUESTIONS
        if q.get("scale") == question.get("scale")
        and not q.get("is_title_screen")
        and not q.get("is_final")
    ] if not question.get("is_title_screen") and not question.get("is_final") else []

    scale_position = 0
    scale_total = len(scale_questions)
    if scale_questions:
        for i, sq in enumerate(scale_questions, 1):
            if sq["id"] == qid:
                scale_position = i
                break

    current_index = next(
        (i for i, q in enumerate(QUESTIONS) if q["id"] == qid), 0
    )
    next_qid = QUESTIONS[current_index + 1]["id"] if current_index + 1 < TOTAL_QUESTIONS else None
    prev_qid = QUESTIONS[current_index - 1]["id"] if current_index > 0 else None

    stream_scale = _derive_stream_scale(question, next_qid=next_qid)
    next_scale = _derive_stream_scale(_get_question(next_qid), next_qid=QUESTIONS[current_index + 2]["id"] if next_qid and current_index + 2 < TOTAL_QUESTIONS else None) if next_qid else ""

    return {
        'question': question,
        'qid': qid,
        'is_final': question.get("is_final", False),
        'is_title_screen': question.get("is_title_screen", False),
        'next_qid': next_qid,
        'prev_qid': prev_qid,
        'previous_score': previous_score,
        'assessment_id': assessment.id,
        'answered_count': answered_count,
        'total_scorable': total_scorable,
        'scale_position': scale_position,
        'scale_total': scale_total,
        'progress_percent': round((answered_count / total_scorable) * 100) if total_scorable else 0,
        'stream_scale': stream_scale,
        'next_stream_scale': next_scale,
        'emotion_max_reconnect_attempts': int(getattr(settings, "EMOTION_MAX_RECONNECT_ATTEMPTS", 5)),
        'emotion_heartbeat_interval_seconds': int(getattr(settings, "EMOTION_HEARTBEAT_INTERVAL_SECONDS", 15)),
        'emotion_heartbeat_grace_seconds': int(getattr(settings, "EMOTION_HEARTBEAT_GRACE_SECONDS", 90)),
        'emotion_client_max_frame_width': int(getattr(settings, "EMOTION_CLIENT_MAX_FRAME_WIDTH", 640)),
        'emotion_client_max_encoded_bytes': int(getattr(settings, "EMOTION_CLIENT_MAX_ENCODED_BYTES", 900000)),
    }


def _extract_scale_scores(answers_dict):
    depression_scores = {}
    stress_scores = {}
    anxiety_scores = {}

    for qid_str, score in answers_dict.items():
        try:
            qid = int(qid_str)
            score = int(score)
        except (ValueError, TypeError):
            continue

        q = QUESTIONS_BY_ID.get(qid)
        #if not q or q.get("is_title_screen") or q.get("is_final "):
        if not q or q.get("is_title_screen") or q.get("is_final"):
            continue

        item_num = q.get("scale_item_number")
        if item_num is None:
            continue

        scale = q.get("scale")
        if scale == "depression":
            depression_scores[item_num] = score
        elif scale == "stress":
            stress_scores[item_num] = score
        elif scale == "anxiety":
            anxiety_scores[str(item_num)] = score

    return depression_scores, stress_scores, anxiety_scores


def _apply_emotion_text_incongruence(report_json, emotion_summary):
    """
    From teammate: flag emotion/text incongruence in report if DeepFace
    detects sustained distress but scale scores suggest otherwise.
    Adapted for new scale-based report structure.
    """
    if not emotion_summary.get("available"):
        return report_json
    distress = emotion_summary.get("distress_proxy", {})
    if not distress.get("flag"):
        return report_json

    depression = report_json.get("depression", {})
    risk_level = depression.get("risk_level", "normal")
    if risk_level in {"normal", "mild"}:
        report_json.setdefault("incongruence_flags", []).append(
            "Emotion-text incongruence: DeepFace detected sustained distress "
            "despite low depression score. Clinician review recommended."
        )
    return report_json


def _apply_scale_emotion_incongruence(report_json):
    scale_thresholds = {
        "depression": {"normal", "mild"},
        "stress": {"low", "normal"},
        "anxiety": {"low", "mild", "normal"},
    }
    for scale, low_risk_levels in scale_thresholds.items():
        scale_result = report_json.get(scale, {})
        summary = scale_result.get("emotion_summary", {})
        if not summary.get("available"):
            continue
        distress = summary.get("distress_proxy", {})
        if not distress.get("flag"):
            continue
        if scale_result.get("risk_level", "normal") in low_risk_levels:
            report_json.setdefault("incongruence_flags", []).append(
                f"{scale.title()} incongruence: facial distress remained elevated despite a low {scale} score."
            )
    return report_json


def _inject_scale_emotion_summaries(report_json, assessment):
    scale_emotion_summaries = {
        "depression": build_scale_emotion_summary(assessment, "depression"),
        "stress": build_scale_emotion_summary(assessment, "stress"),
        "anxiety": build_scale_emotion_summary(assessment, "anxiety"),
    }
    for scale, summary in scale_emotion_summaries.items():
        timeline_summary = build_emotion_timeline_summary(assessment, scale)
        summary["most_frequent_emotion"] = timeline_summary.get("most_frequent_emotion")
        summary["emotion_percentages"] = timeline_summary.get("emotion_percentages", {})
        summary["total_frames"] = timeline_summary.get("total_frames", summary.get("frames_analyzed", 0))
        report_json.setdefault(scale, {})
        report_json[scale]["emotion_summary"] = summary
    overall_summary = build_emotion_summary(assessment)
    overall_timeline = build_emotion_timeline_summary(assessment)
    overall_summary["most_frequent_emotion"] = overall_timeline.get("most_frequent_emotion")
    overall_summary["emotion_percentages"] = overall_timeline.get("emotion_percentages", {})
    overall_summary["total_frames"] = overall_timeline.get("total_frames", overall_summary.get("frames_analyzed", 0))
    report_json["emotion_summary"] = overall_summary
    return report_json, scale_emotion_summaries


def _question_state_payload(context):
    question = context["question"]
    return {
        "question": question,
        "qid": context["qid"],
        "is_final": context["is_final"],
        "is_title_screen": context["is_title_screen"],
        "next_qid": context["next_qid"],
        "prev_qid": context["prev_qid"],
        "previous_score": context["previous_score"],
        "assessment_id": context["assessment_id"],
        "answered_count": context["answered_count"],
        "total_scorable": context["total_scorable"],
        "scale_position": context["scale_position"],
        "scale_total": context["scale_total"],
        "progress_percent": context["progress_percent"],
        "stream_scale": context["stream_scale"],
        "next_stream_scale": context["next_stream_scale"],
        "emotion": {
            "max_reconnect_attempts": context["emotion_max_reconnect_attempts"],
            "heartbeat_interval_seconds": context["emotion_heartbeat_interval_seconds"],
            "heartbeat_grace_seconds": context["emotion_heartbeat_grace_seconds"],
            "client_max_frame_width": context["emotion_client_max_frame_width"],
            "client_max_encoded_bytes": context["emotion_client_max_encoded_bytes"],
            "client_frame_interval_ms": int(getattr(settings, "EMOTION_CLIENT_FRAME_INTERVAL_MS", 250)),
            "client_max_frames_per_question": int(getattr(settings, "EMOTION_CLIENT_MAX_FRAMES_PER_QUESTION", 12)),
            "frame_jpeg_quality": float(getattr(settings, "EMOTION_FRAME_JPEG_QUALITY", 0.85)),
        },
    }


def _get_report_assessment(request):
    completed_id = request.session.get("last_completed_assessment_id")
    if completed_id:
        assessment = Assessment.objects.filter(id=completed_id, is_completed=True).first()
        if assessment:
            return assessment
    if request.user.is_authenticated:
        return (
            Assessment.objects.filter(user=request.user, is_completed=True)
            .order_by("-finalized_at", "-created_at")
            .first()
        )
    if request.session.session_key:
        return (
            Assessment.objects.filter(
                session_key=request.session.session_key, is_completed=True
            )
            .order_by("-finalized_at", "-created_at")
            .first()
        )
    return None


# ============================================================================
# VIEW HANDLERS
# ============================================================================

@ensure_csrf_cookie
def index(request):
    _init_session(request.session)
    _ensure_questions_in_db()
    return render(request, 'Questionaire_project/index.html', {})


@ensure_csrf_cookie
def question_page(request, qid):
    if not _is_valid_qid(qid):
        return redirect('questionnaire:index')

    _ensure_questions_in_db()
    assessment = _get_or_create_assessment(request)
    context = _build_question_context(request, qid, assessment=assessment)
    context["question_state"] = _question_state_payload(context)
    if request.headers.get("X-Question-Partial") == "1":
        return JsonResponse(context["question_state"])
    return render(request, 'Questionaire_project/question.html', context)


@require_http_methods(["POST"])
def save_answer(request):   
    cid = _correlation_id(request)
    try:
        data = json.loads(request.body)
        qid = data.get('qid')
        score = data.get('score')   # integer 0–4
        payload_assessment_id = data.get("assessment_id")

        if qid is None or score is None:
            return _safe_error_response('qid and score are required', status=400)

        try:
            qid_int = int(qid)
            score_int = int(score)
        except (TypeError, ValueError):
            return _safe_error_response('Invalid qid or score', status=400)

        if not _is_valid_qid(qid_int):
            return _safe_error_response('Invalid question ID', status=400)

        q = _get_question(qid_int)
        max_score = q.get("max_score", 3)

        if not (0 <= score_int <= max_score):
            return _safe_error_response(
                f'Score must be 0–{max_score} for this question', status=400
            )

        _set_answer(request.session, str(qid_int), score_int)

        with transaction.atomic():
            _ensure_questions_in_db()
            assessment = _get_or_create_assessment(request)

            # Validate payload assessment ID matches session (from teammate)
            if payload_assessment_id is not None:
                try:
                    payload_assessment_id = int(payload_assessment_id)
                except (TypeError, ValueError):
                    return _safe_error_response("Invalid assessment ID", status=400)
                if payload_assessment_id != assessment.id:
                    logger.warning(
                        "save_answer_assessment_mismatch",
                        extra={
                            "correlation_id": cid,
                            "session_assessment_id": assessment.id,
                            "payload_assessment_id": payload_assessment_id,
                            "qid": qid_int,
                        },
                    )

            if assessment.is_completed:
                logger.warning(
                    "write_rejected_completed_assessment",
                    extra={"correlation_id": cid, "assessment_id": assessment.id, "qid": qid_int},
                )
                return _safe_error_response('Assessment already finalized', status=409)

            question_obj = _get_or_seed_question(qid_int)
            if question_obj is None:
                logger.error("question_catalog_unavailable", extra={"correlation_id": cid, "qid": qid_int})
                return JsonResponse({
                    "status": "success",
                    "message": "Answer saved in session. Question catalog will sync shortly.",
                    "assessment_id": assessment.id,
                })

            Answer.objects.update_or_create(
                assessment=assessment,
                question=question_obj,
                defaults={
                    "answer_text": str(score_int),
                    "answer_score": score_int,
                },
            )

        logger.info(
            "answer_saved",
            extra={"correlation_id": cid, "assessment_id": assessment.id, "qid": qid_int},
        )
        return JsonResponse({
            'status': 'success',
            'message': 'Score saved',
            'assessment_id': assessment.id,
        })

    except json.JSONDecodeError:
        return _safe_error_response('Invalid JSON', status=400)
    except Exception:
        logger.exception("save_answer_failed", extra={"correlation_id": cid})
        return _safe_error_response('Unable to save answer', status=500)

@require_http_methods(["POST"])
def save_text_answer(request):
    """Save the open-ended reflection answer (Q56) to the Assessment model."""
    cid = _correlation_id(request)
    try:
        data = json.loads(request.body)
        text_answer = data.get("text_answer", "").strip()
        payload_assessment_id = data.get("assessment_id")

        with transaction.atomic():
            assessment = _get_or_create_assessment(request)

            if payload_assessment_id is not None:
                try:
                    payload_assessment_id = int(payload_assessment_id)
                except (TypeError, ValueError):
                    return _safe_error_response("Invalid assessment ID", status=400)
                if payload_assessment_id != assessment.id:
                    logger.warning(
                        "save_text_answer_assessment_mismatch",
                        extra={"correlation_id": cid, "session_id": assessment.id,
                               "payload_id": payload_assessment_id},
                    )

            if assessment.is_completed:
                return _safe_error_response("Assessment already finalized", status=409)

            assessment.questionnaire_project_final_answer = text_answer
            assessment.save(update_fields=["questionnaire_project_final_answer"])

        logger.info("text_answer_saved", extra={"correlation_id": cid, "assessment_id": assessment.id})
        return JsonResponse({"status": "success", "assessment_id": assessment.id})

    except json.JSONDecodeError:
        return _safe_error_response("Invalid JSON", status=400)
    except Exception:
        logger.exception("save_text_answer_failed", extra={"correlation_id": cid})
        return _safe_error_response("Unable to save answer", status=500)

@require_http_methods(["POST"])
def finalize_assessment(request):
    """
    Handles the final open-ended question submission, calls Gemini, 
    and saves results to the database.
    """
    try:
        data = json.loads(request.body)
        user_text = data.get("text", "")
        assessment = _get_or_create_assessment(request)

        # 1. Save the student's raw answer
        assessment.questionnaire_project_final_answer = user_text
        
        # 2. Analyze with Gemini
        # analyze_open_ended_text is your feeling_analyzer function
        analysis = analyze_open_ended_text(user_text)
        
        # 3. Store results in the new fields
        assessment.questionnaire_project_final_score = analysis.get("concern_feeling_label", {})
        assessment.questionnaire_project_summary = analysis.get("summary", "")
        
        assessment.is_completed = True
        assessment.save()
        
        return JsonResponse({"status": "success"})
    except Exception as e:
        logger.exception("finalize_assessment_failed")
        return _safe_error_response("Processing failed.")

@ensure_csrf_cookie
def complete(request):
    cid = _correlation_id(request)
    _ensure_questions_in_db()

    session_answers = _get_answers(request.session)
    assessment_id = request.session.get("assessment_id")
    db_answers = {}

    if assessment_id:
        try:
            assessment = Assessment.objects.get(id=assessment_id)
            for ans in Answer.objects.filter(assessment=assessment).select_related('question'):
                if ans.answer_score is not None:
                    db_answers[str(ans.question_id)] = ans.answer_score
        except Assessment.DoesNotExist:
            pass

    answers = {**session_answers, **db_answers}

    if not answers:
        return redirect('questionnaire:index')

    try:
        with transaction.atomic():
            if assessment_id:
                assessment = Assessment.objects.select_for_update().get(id=assessment_id)
            else:
                assessment = (
                    Assessment.objects.select_for_update()
                    .filter(session_key=request.session.session_key, is_completed=False)
                    .order_by("-created_at")
                    .first()
                )
                if assessment is None:
                    raise Assessment.DoesNotExist()

            if assessment.is_completed and assessment.report_json:
                report_json = assessment.report_json

                # Re-run feeling analysis if missing from stored report
                if not report_json.get("feeling_analysis"):
                    final_answer = assessment.questionnaire_project_final_answer or ""
                    feeling_result = analyze_open_ended_text(final_answer)
                    report_json["feeling_analysis"] = feeling_result
                    if not assessment.questionnaire_project_final_score:
                        assessment.questionnaire_project_final_score = feeling_result.get("concern_feeling_label", {})
                    if not assessment.questionnaire_project_summary:
                        assessment.questionnaire_project_summary = feeling_result.get("summary", "")
                    assessment.save(update_fields=[
                        "report_json",
                        "questionnaire_project_final_score",
                        "questionnaire_project_summary",
                    ])

                report_json, scale_emotion_summaries = _inject_scale_emotion_summaries(report_json, assessment)

            else:
                depression_scores, stress_scores, anxiety_scores = _extract_scale_scores(answers)

                depression_result = analyze_depression(depression_scores)
                stress_result     = analyze_stress(stress_scores)
                anxiety_result    = analyze_anxiety(anxiety_scores)

                # ── Open-ended feeling analysis ──────────────────────────────
                final_answer = assessment.questionnaire_project_final_answer or ""
                feeling_result = analyze_open_ended_text(final_answer)
                feeling_score  = feeling_result.get("concern_feeling_label", {})
                feeling_summary = feeling_result.get("summary", "")

                report_json = {
                    'timestamp': timezone.now().isoformat(),
                    'depression': depression_result,
                    'stress':     stress_result,
                    'anxiety':    anxiety_result,
                    'feeling_analysis': feeling_result,
                }
                report_json, scale_emotion_summaries = _inject_scale_emotion_summaries(report_json, assessment)
                emotion_summary = report_json.get("emotion_summary", empty_emotion_summary())

                logger.info(
                    "assessment_emotion_summary_counts",
                    extra={
                        "assessment_id": assessment.id,
                        "depression_raw": scale_emotion_summaries["depression"].get("raw_record_count", 0),
                        "depression_ok": scale_emotion_summaries["depression"].get("frames_analyzed", 0),
                        "stress_raw": scale_emotion_summaries["stress"].get("raw_record_count", 0),
                        "stress_ok": scale_emotion_summaries["stress"].get("frames_analyzed", 0),
                        "anxiety_raw": scale_emotion_summaries["anxiety"].get("raw_record_count", 0),
                        "anxiety_ok": scale_emotion_summaries["anxiety"].get("frames_analyzed", 0),
                    },
                )

                report_json = _apply_emotion_text_incongruence(report_json, emotion_summary)
                report_json = _apply_scale_emotion_incongruence(report_json)
                logger.info("assessment_report_json_ready", extra={"assessment_id": assessment.id, "report_json_keys": list(report_json.keys())})

                now = timezone.now()
                assessment.is_completed           = True
                assessment.finalized_at           = now
                assessment.report_generated_at    = now
                assessment.report_json            = report_json

                assessment.depression_score       = depression_result.get('total_score')
                assessment.depression_risk_level  = depression_result.get('risk_level', '')
                assessment.depression_result_json = depression_result

                assessment.stress_score           = stress_result.get('total_score')
                assessment.stress_risk_level      = stress_result.get('risk_level', '')
                assessment.stress_result_json     = stress_result

                assessment.anxiety_score          = anxiety_result.get('total_score')
                assessment.anxiety_risk_level     = anxiety_result.get('risk_level', '')
                assessment.anxiety_result_json    = anxiety_result
                
                assessment.questionnaire_project_final_score  = feeling_score
                assessment.questionnaire_project_summary      = feeling_summary

                assessment.save(update_fields=[
                    "is_completed", "finalized_at", "report_generated_at",
                    "report_json",
                    "depression_score", "depression_risk_level", "depression_result_json",
                    "stress_score", "stress_risk_level", "stress_result_json",
                    "anxiety_score", "anxiety_risk_level", "anxiety_result_json",
                    "questionnaire_project_final_score", "questionnaire_project_summary",
                ])

        request.session["last_completed_assessment_id"] = assessment.id
        request.session["assessment_cycle"] = int(
            request.session.get("assessment_cycle", 1)
        ) + 1
        request.session.pop('answers', None)
        request.session.pop('assessment_id', None)
        request.session.modified = True

        risk_order = {'normal': 0, 'low': 0, 'mild': 1, 'borderline': 2,
                      'moderate': 3, 'severe': 4, 'extreme': 5, 'high': 4}
        overall_risk = max(
            report_json['depression'].get('risk_level', 'normal'),
            report_json['stress'].get('risk_level', 'low'),
            report_json['anxiety'].get('risk_level', 'low'),
            key=lambda r: risk_order.get(r, 0)
        )
        immediate = any([
            report_json['depression'].get('immediate_intervention_needed', False),
            report_json['stress'].get('immediate_intervention_needed', False),
            report_json['anxiety'].get('immediate_intervention_needed', False),
        ])

        context = {
            'analysis': report_json,
            'depression': report_json['depression'],
            'stress':     report_json['stress'],
            'anxiety':    report_json['anxiety'],
            'emotion_summary': emotion_summary,
            'scale_emotion_summaries': scale_emotion_summaries,
            'overall_risk': overall_risk,
            'immediate_intervention': immediate,
            'timestamp': report_json['timestamp'],
            'feeling_analysis': report_json.get('feeling_analysis', {}),  # ADD THIS
        }
        return render(request, 'Questionaire_project/complete.html', context)

    except Exception:
        logger.exception("complete_failed", extra={"correlation_id": cid})
        return render(request, 'Questionaire_project/error.html', {
            'error': 'Error generating report. Please try again.'
        })


@ensure_csrf_cookie
def download_report_json(request):
    try:
        assessment = _get_report_assessment(request)
        data = assessment.report_json if assessment else {}
        response = HttpResponse(
            json.dumps(data, indent=2), content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename=\"assessment_report.json\"'
        return response
    except Exception:
        logger.exception("download_report_json_failed")
        return JsonResponse({'error': 'Error generating report'}, status=500)


@ensure_csrf_cookie
def download_report_text(request):
    try:
        assessment = _get_report_assessment(request)
        if not assessment:
            return HttpResponse('No assessment data found', status=404)

        d = assessment.depression_result_json or {}
        s = assessment.stress_result_json or {}
        a = assessment.anxiety_result_json or {}

        report_json = assessment.report_json or {}
        feeling = report_json.get('feeling_analysis', {})
        feeling_summary = (
            feeling.get('summary')
            or assessment.questionnaire_project_summary
            or ''
        )
        feeling_scores = (
            feeling.get('concern_feeling_label')
            or assessment.questionnaire_project_final_score
            or {}
        )

        lines = [
            "STUDENT COMPANION — MENTAL HEALTH ASSESSMENT REPORT",
            f"Generated: {assessment.finalized_at}",
            "=" * 60,
            "",
            f"DEPRESSION (BDI)  Score: {d.get('total_score','N/A')}/63  Risk: {d.get('risk_level','N/A').upper()}",
            d.get('interpretation', ''),
            f"Emotion: {(d.get('emotion_summary') or {}).get('overall_dominant_emotion', 'N/A')}",
            "",
            f"STRESS (PSS-10)   Score: {s.get('total_score','N/A')}/40  Risk: {s.get('risk_level','N/A').upper()}",
            s.get('interpretation', ''),
            f"Emotion: {(s.get('emotion_summary') or {}).get('overall_dominant_emotion', 'N/A')}",
            "",
            f"ANXIETY (BAI)     Score: {a.get('total_score','N/A')}/63  Risk: {a.get('risk_level','N/A').upper()}",
            a.get('interpretation', ''),
            f"Emotion: {(a.get('emotion_summary') or {}).get('overall_dominant_emotion', 'N/A')}",
            "",
            "RECOMMENDATIONS",
            "-" * 40,
        ]
        for rec in d.get('recommendations', []):
            lines.append(f"[Depression] {rec}")
        for rec in s.get('recommendations', []):
            lines.append(f"[Stress]     {rec}")
        for rec in a.get('recommendations', []):
            lines.append(f"[Anxiety]    {rec}")

        if feeling_summary or feeling_scores:
            lines += [
                "",
                "=" * 60,
                "EMOTIONAL REFLECTION ANALYSIS",
                "-" * 40,
            ]
            if feeling_summary:
                lines += [feeling_summary, ""]
            if feeling_scores:
                lines.append("Feeling Scores (0.00 – 1.00):")
                for label, score in feeling_scores.items():
                    try:
                        lines.append(f"  {label:<28} {float(score):.2f}")
                    except (TypeError, ValueError):
                        lines.append(f"  {label:<28} {score}")
        response = HttpResponse(''.join(lines), content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename=\"assessment_report.txt\"'
        return response
    except Exception:
        logger.exception("download_report_text_failed")
        return HttpResponse('Error generating report', status=500)


@require_http_methods(["GET"])
def debug_emotions(request, assessment_id: int):
    cid = _correlation_id(request)
    try:
        assessment = Assessment.objects.filter(id=assessment_id).first()
        if not assessment:
            return JsonResponse({"status": "fail", "reason": "assessment_not_found"}, status=404)

        recent_records = list(
            assessment.emotion_records.order_by("-created_at")[:20].values(
                "id",
                "frame_id",
                "frame_number",
                "timestamp_sec",
                "scale",
                "dominant_emotion",
                "status",
                "confidence",
                "created_at",
                "emotion_scores",
            )
        )
        status_distribution = {
            row["status"]: row["total"]
            for row in assessment.emotion_records.values("status").annotate(total=Count("id")).order_by("status")
        }
        payload = {
            "status": "ok",
            "assessment_id": assessment.id,
            "debug_enabled": bool(getattr(settings, "EMOTION_DEBUG", False)),
            "recent_frames": recent_records,
            "status_distribution": status_distribution,
            "emotion_summary": build_emotion_timeline_summary(assessment),
        }
        logger.info(
            "emotion_debug_view_accessed",
            extra={
                "correlation_id": cid,
                "assessment_id": assessment.id,
                "frame_id": None,
            },
        )
        return JsonResponse(payload)
    except Exception:
        logger.exception(
            "emotion_debug_view_failed",
            extra={"correlation_id": cid, "assessment_id": assessment_id, "frame_id": None},
        )
        return JsonResponse({"status": "fail", "reason": "debug_view_failed"}, status=500)


# ============================================================================
# LEGACY STUBS — kept so any old bookmarks/links don't 500
# These routes are no longer in urls.py but kept here as safety nets
# ============================================================================

@ensure_csrf_cookie
def generate_mse_report(request):
    """Deprecated: MSE system replaced by structured scales. Redirect to index."""
    logger.info("generate_mse_report_deprecated_called")
    return redirect('questionnaire:index')


@ensure_csrf_cookie
def view_risk_summary(request):
    """Deprecated: replaced by complete.html three-scale results. Redirect to index."""
    logger.info("view_risk_summary_deprecated_called ")
    return redirect('questionnaire:index')

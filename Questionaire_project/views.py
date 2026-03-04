import json
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .emotion_services import build_emotion_summary
from .models import Assessment, Answer, Question
from .mse_analyzer import analyze_patient_responses, append_emotion_summary_to_report

logger = logging.getLogger(__name__)

# ============================================================================
# DATA STORE - VIDEOS WITH CORRECT FILE NAMES
# ============================================================================

VIDEOS = [
    {
        "id": 1,
        "file": "question1.mp4",
        "question": "Can you tell me about your mood over the past few weeks? Describe your predominant mood in your own words.",
        "type": "text",
        "mse_category": "mood"
    },
    {
        "id": 2,
        "file": "question2.mp4",
        "question": "Does what you show to others match how you actually feel inside? And do you notice your emotions changing throughout the day?",
        "type": "text",
        "mse_category": "affect"
    },
    {
        "id": 3,
        "file": "question3pt1.mp4",
        "question": "Have you been feeling anxious, nervous, or worried a lot lately? If so, what kinds of things tend to trigger these feelings?",
        "type": "text",
        "mse_category": "anxiety"
    },
    {
        "id": 4,
        "file": "question3pt3.mp4",
        "question": "Do you ever have panic attacks? If yes: How often would you say these happen?",
        "type": "text",
        "mse_category": "anxiety"
    },
    {
        "id": 5,
        "file": "question4.mp4",
        "question": "Do you experience any difficulties with your sleep? If so, please describe the problems in detail. Also let me know if you are currently using anything to help you sleep, such as medications or supplements.",
        "type": "text",
        "mse_category": "sleep"
    },
    {
        "id": 6,
        "file": "question5.mp4",
        "question": "Do your thoughts feel like they're completely your own and under your control?, or have you ever felt as if someone else was putting thoughts into your mind?",
        "type": "text",
        "mse_category": "thought_control"
    },
    {
        "id": 7,
        "file": "question6.mp4",
        "question": "Have you had thoughts about death, wishing you were dead, or a specific plan to actively end your life? Have you hurt yourself on purpose in any way like cutting, burning, or other ways of causing yourself pain?",
        "type": "text",
        "mse_category": "suicidal_ideation"
    },
    {
        "id": 8,
        "file": "question7.mp4",
        "question": "Have you had thoughts about hurting or harming anyone else? If yes, is there a specific person, or do you have any kind of plan?",
        "type": "text",
        "mse_category": "homicidal_ideation"
    },
    {
        "id": 9,
        "file": "question8.mp4",
        "question": "Some people have unusual experiences with their senses. Have you heard voices when no one was there, seen things that others didn't see, or felt strange sensations on your skin-like crawling or tingling-that others don't seem to notice?",
        "type": "text",
        "mse_category": "hallucinations"
    },
    {
        "id": 10,
        "file": "question9.mp4",
        "question": "Do you have any beliefs that others seem to have trouble understanding or accepting? Do you ever feel like certain people, events, or things have a special meaning meant just for you?",
        "type": "text",
        "mse_category": "delusions"
    },
    {
        "id": 11,
        "file": "question13.mp4",
        "question": "I want to understand your use of alcohol, drugs, or any medications you take that weren't prescribed to you. Do you use any of these? If so, what do you use, how often, and how much?",
        "type": "text",
        "mse_category": "substance_use"
    },
    {
        "id": 12,
        "file": "question10.mp4",
        "question": "Let's talk about how you make decisions. Do you tend to act on urges without thinking of the consequences, and do you believe your recent choices in life have been reasonable and appropriate?",
        "type": "text",
        "mse_category": "judgment"
    },
    {
        "id": 13,
        "file": "question11.mp4",
        "question": "Do you believe you're currently experiencing any mental health or emotional difficulties? and are you willing to accept professional help or treatment?",
        "type": "text",
        "mse_category": "insight"
    },
    {
        "id": 14,
        "file": "question14.mp4",
        "question": "Before we conclude, do you have any questions for me or is there anything else that you'd like to discuss that we haven't covered?",
        "type": "text",
        "mse_category": "additional"
    },
    {
        "id": 15,
        "file": "finalvideo.mp4",
        "question": "",
        "type": "final",
        "is_final": True
    }
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _init_session(session):
    """Initialize session with empty answers dictionary"""
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
    """Get all answers from session"""
    return session.get('answers', {})


def _set_answer(session, qid, answer):
    """Save an answer to the session"""
    if 'answers' not in session:
        session['answers'] = {}
    answers = session['answers']
    answers[str(qid)] = answer
    session['answers'] = answers
    session.modified = True


def _is_valid_qid(qid):
    """Check if question ID is valid"""
    return 1 <= qid <= len(VIDEOS)


def _get_video(qid):
    """Get video data for a specific question ID"""
    return VIDEOS[qid - 1]


def _get_or_create_assessment(request):
    """
    Ensure we have an Assessment tied to this session.
    Creates DB record while maintaining session flow.
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
        # Reuse active token if present, but roll forward if the token points to
        # a completed attempt to avoid write conflicts.
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
    """Ensure all questions from VIDEOS are in the database"""
    try:
        ids = [int(video["id"]) for video in VIDEOS if "id" in video]
        existing_ids = set(Question.objects.filter(id__in=ids).values_list("id", flat=True))
        missing = []
        for video in VIDEOS:
            qid = int(video["id"])
            if qid in existing_ids:
                continue
            missing.append(
                Question(
                    id=qid,
                    video_file=video.get("file", ""),
                    question_text=video.get("question", ""),
                    mse_category=video.get("mse_category", ""),
                    is_final=video.get("is_final", False),
                    is_active=True,
                )
            )
        if missing:
            Question.objects.bulk_create(missing, ignore_conflicts=True)
    except Exception:
        logger.exception("question_seed_failed")


def _get_or_seed_question(qid):
    """Get question row or seed it from VIDEOS as a fallback."""
    question = Question.objects.filter(id=qid).first()
    if question is not None:
        return question
    if not _is_valid_qid(int(qid)):
        return None
    video = _get_video(int(qid))
    try:
        question = Question.objects.create(
            id=int(video["id"]),
            video_file=video.get("file", ""),
            question_text=video.get("question", ""),
            mse_category=video.get("mse_category", ""),
            is_final=video.get("is_final", False),
            is_active=True,
        )
        logger.warning("question_seeded_on_demand", extra={"qid": int(qid)})
    except Exception:
        question = Question.objects.filter(id=qid).first()
    return question


def _snapshot_answers(assessment, session_answers):
    db_answers = {
        str(answer.question_id): answer.answer_text
        for answer in Answer.objects.filter(assessment=assessment).select_related("question")
    }
    return {**session_answers, **db_answers}


def _persist_session_answers(assessment, session_answers):
    for qid, text in session_answers.items():
        if not str(qid).isdigit():
            continue
        qid_int = int(qid)
        if not _is_valid_qid(qid_int):
            continue
        question = _get_or_seed_question(qid_int)
        if question is None:
            continue
        Answer.objects.update_or_create(
            assessment=assessment,
            question=question,
            defaults={"answer_text": text},
        )


def _safe_error_response(message, status=500):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _apply_emotion_text_incongruence(structured_analysis, emotion_summary):
    if not emotion_summary.get("available"):
        return structured_analysis
    distress = emotion_summary.get("distress_proxy", {})
    if not distress.get("flag"):
        return structured_analysis

    mood = structured_analysis.get("mood_affect", {})
    risk = structured_analysis.get("risk_assessment", {})
    mood_label = mood.get("mood_category", "unknown")
    sentiment = mood.get("sentiment_score", 0.0)
    if mood_label in {"euthymic", "elevated"} or sentiment > 0.2:
        incongruence_note = "Emotion-text incongruence detected: reported stable mood with sustained distress signals."
        risk.setdefault("risk_factors", []).append(incongruence_note)
        risk.setdefault("incongruence_flags", []).append("emotion_text_incongruence")
        structured_analysis.setdefault("clinical_impressions", []).append(
            "Needs clinician review: emotion stream indicates sustained distress despite reassuring text."
        )
    return structured_analysis


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
            Assessment.objects.filter(session_key=request.session.session_key, is_completed=True)
            .order_by("-finalized_at", "-created_at")
            .first()
        )
    return None


# ============================================================================
# VIEW HANDLERS
# ============================================================================

@ensure_csrf_cookie
def index(request):
    """Landing page with intro video - serves index.html"""
    _init_session(request.session)
    _ensure_questions_in_db()
    context = {}
    return render(request, 'Questionaire_project/index.html', context)


@ensure_csrf_cookie
def question_page(request, qid):
    """Display a question video and answer form"""
    _ensure_questions_in_db()

    if not _is_valid_qid(qid):
        return redirect('questionnaire:index')

    video = _get_video(qid)
    assessment = _get_or_create_assessment(request)

    previous_answer = _get_answers(request.session).get(str(qid), '')

    if not previous_answer:
        try:
            answer_obj = Answer.objects.get(assessment=assessment, question_id=qid)
            previous_answer = answer_obj.answer_text
            _set_answer(request.session, str(qid), previous_answer)
        except Answer.DoesNotExist:
            pass

    total_questions = len(VIDEOS)
    is_final = video.get('is_final', False)
    is_last = (qid == total_questions - 1)

    context = {
        'video': video,
        'is_final': is_final,
        'is_last': is_last,
        'total_questions': total_questions,
        'previous_answer': previous_answer,
        'assessment_id': assessment.id,
        'emotion_max_reconnect_attempts': int(getattr(settings, "EMOTION_MAX_RECONNECT_ATTEMPTS", 5)),
        'emotion_heartbeat_interval_seconds': int(getattr(settings, "EMOTION_HEARTBEAT_INTERVAL_SECONDS", 15)),
        'emotion_heartbeat_grace_seconds': int(getattr(settings, "EMOTION_HEARTBEAT_GRACE_SECONDS", 90)),
        'emotion_client_max_frame_width': int(getattr(settings, "EMOTION_CLIENT_MAX_FRAME_WIDTH", 640)),
        'emotion_client_max_encoded_bytes': int(getattr(settings, "EMOTION_CLIENT_MAX_ENCODED_BYTES", 900000)),
    }

    return render(request, 'Questionaire_project/question.html', context)


@require_http_methods(["POST"])
def save_answer(request):
    """API endpoint to save an answer to both session and database"""
    cid = _correlation_id(request)
    try:
        data = json.loads(request.body)
        qid = data.get('qid')
        answer = data.get('answer', '')
        max_chars = int(getattr(settings, "ASSESSMENT_MAX_ANSWER_CHARS", 5000))
        payload_assessment_id = data.get("assessment_id")

        if not qid:
            return JsonResponse({'status': 'error', 'message': 'Question ID is required'}, status=400)

        try:
            qid_int = int(qid)
        except (TypeError, ValueError):
            return _safe_error_response("Invalid question ID", status=400)

        if not _is_valid_qid(qid_int):
            return _safe_error_response("Invalid question ID", status=400)
        if not isinstance(answer, str):
            return _safe_error_response("Invalid answer payload", status=400)
        if len(answer) > max_chars:
            return _safe_error_response(f"Answer too long (max {max_chars} chars)", status=400)

        _set_answer(request.session, str(qid), answer)

        with transaction.atomic():
            _ensure_questions_in_db()
            assessment = _get_or_create_assessment(request)
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
                return _safe_error_response("Assessment is already finalized", status=409)

            question = _get_or_seed_question(qid_int)
            if question is None:
                # Keep session answer even if DB catalog temporarily unavailable.
                logger.error("question_catalog_unavailable", extra={"correlation_id": cid, "qid": qid_int})
                return JsonResponse(
                    {
                        "status": "success",
                        "message": "Answer saved in session. Question catalog will sync shortly.",
                        "assessment_id": assessment.id,
                    }
                )

            Answer.objects.update_or_create(
                assessment=assessment,
                question=question,
                defaults={"answer_text": answer}
            )
        logger.info(
            "answer_saved",
            extra={"correlation_id": cid, "assessment_id": assessment.id, "qid": qid_int},
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Answer saved successfully',
            'assessment_id': assessment.id
        })

    except json.JSONDecodeError:
        return _safe_error_response('Invalid JSON data', status=400)
    except Exception as e:
        logger.exception("save_answer_failed", extra={"correlation_id": cid})
        return _safe_error_response('Unable to save answer at this time.', status=500)


@ensure_csrf_cookie
def complete(request):
    """Completion page showing MSE analysis report"""
    cid = _correlation_id(request)
    _ensure_questions_in_db()
    session_answers = _get_answers(request.session)

    assessment_id = request.session.get("assessment_id")
    db_answers = {}

    if assessment_id:
        try:
            assessment = Assessment.objects.get(id=assessment_id)
            for answer in Answer.objects.filter(assessment=assessment).select_related('question'):
                db_answers[str(answer.question.id)] = answer.answer_text
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
            if assessment.is_completed and assessment.report_text and assessment.report_json:
                structured_analysis = assessment.report_json
                formatted_report = assessment.report_text
                emotion_summary = structured_analysis.get("emotion_summary", {"available": False})
            else:
                _persist_session_answers(assessment, session_answers)
                answers = _snapshot_answers(assessment, session_answers)
                structured_analysis, formatted_report = analyze_patient_responses(answers)
                emotion_summary = build_emotion_summary(assessment)
                structured_analysis["emotion_summary"] = emotion_summary
                structured_analysis = _apply_emotion_text_incongruence(structured_analysis, emotion_summary)
                formatted_report = append_emotion_summary_to_report(formatted_report, emotion_summary)
                now = timezone.now()
                assessment.is_completed = True
                assessment.finalized_at = now
                assessment.report_generated_at = now
                assessment.report_text = formatted_report
                assessment.report_json = structured_analysis
                assessment.save(
                    update_fields=[
                        "is_completed",
                        "finalized_at",
                        "report_generated_at",
                        "report_text",
                        "report_json",
                    ]
                )

        request.session['mse_analysis'] = structured_analysis
        request.session.modified = True
        request.session["last_completed_assessment_id"] = assessment.id
        request.session["assessment_cycle"] = int(request.session.get("assessment_cycle", 1)) + 1

        if 'answers' in request.session:
            del request.session['answers']
        if 'assessment_id' in request.session:
            del request.session['assessment_id']
        request.session.modified = True

        context = {
            'report': formatted_report,
            'analysis': structured_analysis,
            'timestamp': structured_analysis['timestamp'],
            'risk_level': structured_analysis['risk_assessment']['overall_risk'],
            'immediate_intervention': structured_analysis['risk_assessment']['immediate_intervention_needed'],
            'emotion_summary': emotion_summary,
        }

        return render(request, 'Questionaire_project/complete.html', context)

    except Exception as e:
        logger.exception("complete_failed", extra={"correlation_id": cid, "assessment_id": assessment_id})
        return render(request, 'Questionaire_project/error.html', {
            'error': 'Error generating report. Please try again.'
        })


@ensure_csrf_cookie
def generate_mse_report(request):
    """Generate AI-analyzed Mental Status Exam report"""
    _ensure_questions_in_db()
    session_answers = _get_answers(request.session)

    assessment_id = request.session.get("assessment_id")
    db_answers = {}

    if assessment_id:
        try:
            assessment = Assessment.objects.get(id=assessment_id)
            for answer in Answer.objects.filter(assessment=assessment).select_related('question'):
                db_answers[str(answer.question.id)] = answer.answer_text
        except Assessment.DoesNotExist:
            pass

    answers = {**session_answers, **db_answers}

    if not answers:
        return render(request, 'Questionaire_project/error.html', {
            'error': 'No assessment data found. Please complete the assessment first.'
        })

    try:
        assessment = Assessment.objects.filter(id=assessment_id).first() if assessment_id else None
        if assessment and assessment.is_completed and assessment.report_json and assessment.report_text:
            structured_analysis = assessment.report_json
            formatted_report = assessment.report_text
            emotion_summary = structured_analysis.get("emotion_summary", {"available": False})
        else:
            structured_analysis, formatted_report = analyze_patient_responses(answers)
            emotion_summary = {"available": False}
            if assessment_id:
                try:
                    assessment = Assessment.objects.get(id=assessment_id)
                    emotion_summary = build_emotion_summary(assessment)
                    structured_analysis["emotion_summary"] = emotion_summary
                    structured_analysis = _apply_emotion_text_incongruence(structured_analysis, emotion_summary)
                    formatted_report = append_emotion_summary_to_report(formatted_report, emotion_summary)
                except Assessment.DoesNotExist:
                    pass

        request.session['mse_analysis'] = structured_analysis

        context = {
            'report': formatted_report,
            'analysis': structured_analysis,
            'timestamp': structured_analysis['timestamp'],
            'risk_level': structured_analysis['risk_assessment']['overall_risk'],
            'immediate_intervention': structured_analysis['risk_assessment']['immediate_intervention_needed'],
            'emotion_summary': emotion_summary,
        }

        return render(request, 'Questionaire_project/mse_report.html', context)

    except Exception as e:
        logger.exception("generate_mse_report_failed")
        return render(request, 'Questionaire_project/error.html', {
            'error': 'Error generating report. Please try again.'
        })


@ensure_csrf_cookie
def download_report_text(request):
    """Download MSE report as text file"""
    try:
        assessment = _get_report_assessment(request)
        if assessment and assessment.report_text:
            formatted_report = assessment.report_text
        else:
            answers = _get_answers(request.session)
            if not answers:
                return HttpResponse('No assessment data found', status=404)
            _, formatted_report = analyze_patient_responses(answers)
        response = HttpResponse(formatted_report, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="mse_report.txt"'
        return response

    except Exception as e:
        logger.exception("download_report_text_failed")
        return HttpResponse('Error generating report', status=500)


@ensure_csrf_cookie
def download_report_json(request):
    """Download structured MSE analysis as JSON"""
    try:
        assessment = _get_report_assessment(request)
        if assessment and assessment.report_json:
            structured_analysis = assessment.report_json
        else:
            answers = _get_answers(request.session)
            if not answers:
                return JsonResponse({'error': 'No assessment data found'}, status=404)
            structured_analysis, _ = analyze_patient_responses(answers)
        response = HttpResponse(
            json.dumps(structured_analysis, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="mse_analysis.json"'
        return response

    except Exception as e:
        logger.exception("download_report_json_failed")
        return JsonResponse({'error': 'Error generating report'}, status=500)


@ensure_csrf_cookie
def view_risk_summary(request):
    """View quick risk summary page"""
    answers = _get_answers(request.session)

    if not answers:
        return redirect('questionnaire:index')

    try:
        structured_analysis, _ = analyze_patient_responses(answers)
        risk = structured_analysis['risk_assessment']

        context = {
            'risk': risk,
            'clinical_impressions': structured_analysis['clinical_impressions'],
            'recommendations': structured_analysis['recommendations'][:5]
        }

        return render(request, 'Questionaire_project/risk_summary.html', context)

    except Exception as e:
        logger.exception("risk_summary_failed")
        return render(request, 'Questionaire_project/error.html', {
            'error': 'Error generating risk summary.'
        })

from django.conf import settings
from django.db import models
from django.db.models import Q


class Question(models.Model):
    SCALE_DEPRESSION = 'depression'
    SCALE_STRESS = 'stress'
    SCALE_ANXIETY = 'anxiety'
    SCALE_TITLE = 'title'      # title screen between scales
    SCALE_FINAL = 'final'
    SCALE_OPEN_ENDED = 'open_ended'

    SCALE_CHOICES = [
        (SCALE_DEPRESSION, 'Depression (BDI)'),
        (SCALE_STRESS, 'Stress (PSS-10)'),
        (SCALE_ANXIETY, 'Anxiety (BAI)'),
        (SCALE_TITLE, 'Title Screen'),
        (SCALE_FINAL, 'Final Screen'),
        ('open_ended', 'Open Ended Reflection'), 
    ]

    id = models.PositiveIntegerField(primary_key=True)
    video_file = models.CharField(max_length=255, blank=True)
    question_text = models.TextField(blank=True)
    mse_category = models.CharField(max_length=100, blank=True)
    scale = models.CharField(
        max_length=20, choices=SCALE_CHOICES, blank=True, default=''
    )
    scale_item_number = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Item number within its scale (1-21 for BDI/BAI, 1-10 for PSS)"
    )
    max_score = models.PositiveSmallIntegerField(
        default=3,
        help_text="Max score for this item: 3 for BDI/BAI, 4 for PSS"
    )
    is_reverse_scored = models.BooleanField(
        default=False,
        help_text="True for PSS items 4,5,7,8"
    )
    is_title_screen = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Q{self.id} [{self.scale}]"


class Assessment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
    )
    session_key = models.CharField(max_length=64, db_index=True)
    assessment_token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    report_generated_at = models.DateTimeField(null=True, blank=True)
    report_text = models.TextField(blank=True)
    report_json = models.JSONField(default=dict, blank=True)

    # --- New: individual scale results stored separately ---
    depression_score = models.PositiveSmallIntegerField(null=True, blank=True)
    depression_risk_level = models.CharField(max_length=20, blank=True)
    depression_result_json = models.JSONField(default=dict, blank=True)

    stress_score = models.PositiveSmallIntegerField(null=True, blank=True)
    stress_risk_level = models.CharField(max_length=20, blank=True)
    stress_result_json = models.JSONField(default=dict, blank=True)

    anxiety_score = models.PositiveSmallIntegerField(null=True, blank=True)
    anxiety_risk_level = models.CharField(max_length=20, blank=True)
    anxiety_result_json = models.JSONField(default=dict, blank=True)

    questionnaire_project_final_answer = models.TextField(blank=True, default="")
    questionnaire_project_final_score  = models.JSONField(default=dict, blank=True)
    questionnaire_project_summary      = models.TextField(blank=True, default="")


    def __str__(self):
        return f"Assessment {self.pk}"


class Answer(models.Model):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="answers"
    )
    answer_text = models.TextField(blank=True)
    # New: integer score for structured scale items
    answer_score = models.SmallIntegerField(
        null=True, blank=True,
        help_text="Numeric score (0-4) for scale questions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "question"],
                name="uq_assessment_question"
            )
        ]

    def __str__(self):
        return f"A{self.assessment_id}-Q{self.question_id} score={self.answer_score}"

class MSEReport(models.Model):
    assessment = models.OneToOneField(
        Assessment, on_delete=models.CASCADE, related_name="mse_report"
    )
    report_html = models.TextField(blank=True)   # stores rendered HTML
    report_pdf  = models.BinaryField(null=True, blank=True)  # optional PDF bytes
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"MSEReport for Assessment {self.assessment_id}"

class AnalysisResult(models.Model):
    """
    Stores the complete output of the post-assessment analysis pipeline
    for one completed Assessment.

    This table is written once by pipeline_orchestrator.run_pipeline()
    and can be re-generated safely (update_or_create is used).
    """

    # ── Link to Assessment ───────────────────────────────────────────────────
    assessment = models.OneToOneField(
        "Assessment",          # string reference avoids circular import issues
        on_delete=models.CASCADE,
        related_name="analysis_result",
        help_text="The completed assessment this result belongs to.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Extracted Levels (from report_parser) ────────────────────────────────
    depression_level = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Severity level: low | moderate | severe",
    )
    anxiety_level = models.CharField(
        max_length=20, blank=True, default="",
    )
    stress_level = models.CharField(
        max_length=20, blank=True, default="",
    )

    # ── Emotion Data (from report_parser + emotion_mapper) ───────────────────
    dominant_emotion = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Overall dominant emotion: sad | fear | angry | disgust | surprise | neutral | happy",
    )
    scale_emotions = models.JSONField(
        default=dict, blank=True,
        help_text='Per-scale dominant emotion. e.g. {"depression": "sad", "stress": "angry"}',
    )
    emotional_summary = models.TextField(
        blank=True, default="",
        help_text="Free-text summary from the student's open-ended reflection (feeling_analysis).",
    )
    emotion_labels = models.JSONField(
        default=list, blank=True,
        help_text='Concern labels from feeling_analysis. e.g. ["loneliness", "academic_stress"]',
    )
    emotion_conditions = models.JSONField(
        default=list, blank=True,
        help_text="Mental health conditions mapped from the dominant emotion.",
    )
    facial_note = models.TextField(
        blank=True, default="",
        help_text="Human-readable note explaining what the facial expression result means.",
    )

    # ── Recommendations (from recommendation_fetcher) ────────────────────────
    recommendations_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Full recommendations block for all three scales. "
            "e.g. {'depression': {'level': 'moderate', 'tips': [...], 'message': '...'}, ...}"
        ),
    )


    # ── Past Session Comparison (from session_comparator) ────────────────────
    past_sessions_found = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of past completed sessions found (0, 1, or 2).",
    )
    comparison_results = models.JSONField(
        default=list, blank=True,
        help_text="List of comparison dicts, one per past session.",
    )
    overall_trend = models.CharField(
        max_length=20, blank=True, default="no_data",
        help_text="Trend across sessions: improving | worsening | stable | mixed | no_data",
    )
    comparison_summary = models.TextField(
        blank=True, default="",
        help_text="Human-readable paragraph summarising the trend across past sessions.",
    )
    therapist_script = models.TextField(
        blank=True, default="",
        help_text="AI-generated conversational therapist monologue based on full analysis.",
    )

    class Meta:
        verbose_name = "Analysis Result"
        verbose_name_plural = "Analysis Results"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"AnalysisResult(assessment_id={self.assessment_id}, "
            f"dep={self.depression_level}, anx={self.anxiety_level}, "
            f"str={self.stress_level}, trend={self.overall_trend})"
        )

    # ── Convenience properties ───────────────────────────────────────────────

    @property
    def depression_recommendations(self) -> dict:
        """Quick access to just the depression recommendation block."""
        return self.recommendations_json.get("depression", {})

    @property
    def anxiety_recommendations(self) -> dict:
        return self.recommendations_json.get("anxiety", {})

    @property
    def stress_recommendations(self) -> dict:
        return self.recommendations_json.get("stress", {})

    @property
    def all_tips(self) -> list:
        """Return all tips from all three scales as a flat list."""
        tips = []
        for scale in ("depression", "anxiety", "stress"):
            tips.extend(
                self.recommendations_json.get(scale, {}).get("tips", [])
            )
        return tips


class EmotionRecord(models.Model):
    STATUS_OK = "ok"
    STATUS_NO_FACE = "no_face"
    STATUS_ERROR = "error"
    STATUS_QUALITY_LOW = "quality_low"
    STATUS_RATE_LIMITED = "rate_limited"
    STATUS_FALLBACK = "fallback"
    STATUS_REPAIRED = "repaired"
    STATUS_UNCERTAIN = "uncertain"

    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_NO_FACE, "No Face"),
        (STATUS_ERROR, "Error"),
        (STATUS_QUALITY_LOW, "Quality Low"),
        (STATUS_RATE_LIMITED, "Rate Limited"),
        (STATUS_FALLBACK, "Fallback"),
        (STATUS_REPAIRED, "Repaired"),
        (STATUS_UNCERTAIN, "Uncertain"),
    ]

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="emotion_records",
    )
    scale = models.CharField(
        max_length=20, choices=Question.SCALE_CHOICES, blank=True, db_index=True
    )
    question = models.ForeignKey(
        Question, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="emotion_records",
    )
    frame_id = models.CharField(max_length=64, blank=True, db_index=True)
    frame_number = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    timestamp_sec = models.FloatField(null=True, blank=True)
    dominant_emotion = models.CharField(max_length=32, blank=True)
    emotion_scores = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_OK
    )
    client_ts = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["assessment", "created_at"]),
            models.Index(fields=["assessment", "scale", "created_at"]),
            models.Index(fields=["question", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["assessment", "scale", "frame_number"]),
        ]

    def __str__(self):
        return (
            f"EmotionRecord(assessment={self.assessment_id}, "
            f"status={self.status}, emotion={self.dominant_emotion})"
        )


class ScaleEmotionSession(models.Model):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="scale_emotion_sessions"
    )
    scale = models.CharField(
        max_length=20, choices=Question.SCALE_CHOICES, db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    total_frames = models.PositiveIntegerField(default=0)
    overall_dominant_emotion = models.CharField(max_length=32, blank=True)
    distress_ratio = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["assessment", "scale", "started_at"]),
        ]

    def __str__(self):
        return f"ScaleEmotionSession(assessment={self.assessment_id}, scale={self.scale})"

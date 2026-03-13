from django.conf import settings
from django.db import models
from django.db.models import Q


class Question(models.Model):
    SCALE_DEPRESSION = 'depression'
    SCALE_STRESS = 'stress'
    SCALE_ANXIETY = 'anxiety'
    SCALE_TITLE = 'title'      # title screen between scales
    SCALE_FINAL = 'final'

    SCALE_CHOICES = [
        (SCALE_DEPRESSION, 'Depression (BDI)'),
        (SCALE_STRESS, 'Stress (PSS-10)'),
        (SCALE_ANXIETY, 'Anxiety (BAI)'),
        (SCALE_TITLE, 'Title Screen'),
        (SCALE_FINAL, 'Final Screen'),
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


class EmotionRecord(models.Model):
    STATUS_OK = "ok"
    STATUS_NO_FACE = "no_face"
    STATUS_ERROR = "error"
    STATUS_QUALITY_LOW = "quality_low"
    STATUS_RATE_LIMITED = "rate_limited"

    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_NO_FACE, "No Face"),
        (STATUS_ERROR, "Error"),
        (STATUS_QUALITY_LOW, "Quality Low"),
        (STATUS_RATE_LIMITED, "Rate Limited"),
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
    dominant_emotion = models.CharField(max_length=32, blank=True)
    emotion_scores = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_OK
    )
    client_ts = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "scale", "frame_id"],
                condition=~Q(frame_id=""),
                name="uq_emotionrecord_assessment_scale_frame",
            )
        ]
        indexes = [
            models.Index(fields=["assessment", "created_at"]),
            models.Index(fields=["assessment", "scale", "created_at"]),
            models.Index(fields=["question", "created_at"]),
            models.Index(fields=["status"]),
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

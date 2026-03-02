from django.conf import settings
from django.db import models


class Question(models.Model):
    """
    Optional but recommended:
    id same rakha hai (1..15) as your VIDEOS list.
    """

    id = models.PositiveIntegerField(primary_key=True)
    video_file = models.CharField(max_length=255)
    question_text = models.TextField(blank=True)
    mse_category = models.CharField(max_length=100, blank=True)
    is_final = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Q{self.id}"


class Assessment(models.Model):
    """
    One assessment attempt per session (flow change nahi hota).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
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

    def __str__(self):
        return f"Assessment {self.pk}"


class Answer(models.Model):
    """
    One answer per (assessment, question)
    """

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    answer_text = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "question"], name="uq_assessment_question")
        ]

    def __str__(self):
        return f"A{self.assessment_id}-Q{self.question_id}"


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
        Assessment,
        on_delete=models.CASCADE,
        related_name="emotion_records",
    )
    question = models.ForeignKey(
        Question,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emotion_records",
    )
    dominant_emotion = models.CharField(max_length=32, blank=True)
    emotion_scores = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OK)
    client_ts = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["assessment", "created_at"]),
            models.Index(fields=["question", "created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            f"EmotionRecord(assessment={self.assessment_id}, status={self.status}, "
            f"emotion={self.dominant_emotion})"
        )

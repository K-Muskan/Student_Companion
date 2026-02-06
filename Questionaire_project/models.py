from django.db import models
from django.conf import settings


class Question(models.Model):
    """
    Optional but recommended:
    id same rakha hai (1..15) as your VIDEOS list.
    """
    id = models.PositiveIntegerField(primary_key=True)  # 1..15
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
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments"
    )
    session_key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
from django.contrib import admin

from .models import Answer, Assessment, EmotionRecord, Question


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "mse_category", "is_final", "is_active")
    list_filter = ("is_final", "is_active", "mse_category")
    search_fields = ("question_text", "video_file")


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "is_completed", "created_at")
    list_filter = ("is_completed", "created_at")
    search_fields = ("session_key", "user__email", "user__username")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "question", "updated_at")
    list_filter = ("question", "created_at")
    search_fields = ("answer_text",)


@admin.register(EmotionRecord)
class EmotionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "assessment",
        "question",
        "status",
        "dominant_emotion",
        "confidence",
        "created_at",
    )
    list_filter = ("status", "dominant_emotion", "created_at")
    search_fields = ("assessment__id", "question__id")

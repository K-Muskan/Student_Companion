from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Questionaire_project", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="is_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="EmotionRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dominant_emotion", models.CharField(blank=True, max_length=32)),
                ("emotion_scores", models.JSONField(blank=True, default=dict)),
                ("confidence", models.FloatField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("ok", "OK"), ("no_face", "No Face"), ("error", "Error")],
                        default="ok",
                        max_length=16,
                    ),
                ),
                ("client_ts", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assessment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="emotion_records",
                        to="Questionaire_project.assessment",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="emotion_records",
                        to="Questionaire_project.question",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["assessment", "created_at"], name="Questionair_assessm_62dc28_idx"),
                    models.Index(fields=["question", "created_at"], name="Questionair_question_5ab645_idx"),
                    models.Index(fields=["status"], name="Questionair_status_b3c58a_idx"),
                ],
            },
        ),
    ]

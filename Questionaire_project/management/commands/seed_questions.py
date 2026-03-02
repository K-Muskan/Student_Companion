from django.core.management.base import BaseCommand

from Questionaire_project.models import Question
from Questionaire_project.views import VIDEOS


class Command(BaseCommand):
    help = "Seed question catalog from static video/question map."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for video in VIDEOS:
            question, was_created = Question.objects.get_or_create(
                id=video["id"],
                defaults={
                    "video_file": video.get("file", ""),
                    "question_text": video.get("question", ""),
                    "mse_category": video.get("mse_category", ""),
                    "is_final": video.get("is_final", False),
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
                continue

            dirty = False
            for field, value in {
                "video_file": video.get("file", ""),
                "question_text": video.get("question", ""),
                "mse_category": video.get("mse_category", ""),
                "is_final": video.get("is_final", False),
                "is_active": True,
            }.items():
                if getattr(question, field) != value:
                    setattr(question, field, value)
                    dirty = True
            if dirty:
                question.save(update_fields=["video_file", "question_text", "mse_category", "is_final", "is_active"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Question seed complete. created={created} updated={updated}"))

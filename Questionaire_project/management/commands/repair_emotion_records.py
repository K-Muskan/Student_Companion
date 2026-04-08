from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from Questionaire_project.models import EmotionRecord


class Command(BaseCommand):
    help = "Repairs EmotionRecord rows with empty emotion payloads or null confidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Scan and report repairs without writing changes.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        repair_filter = (
            Q(dominant_emotion="") |
            Q(emotion_scores={}) |
            Q(confidence__isnull=True)
        )

        queryset = EmotionRecord.objects.filter(repair_filter).order_by("id")
        total_scanned = EmotionRecord.objects.count()
        total_repaired = queryset.count()

        with transaction.atomic():
            if not dry_run and total_repaired:
                queryset.update(
                    dominant_emotion="neutral",
                    emotion_scores={"neutral": 0.1},
                    confidence=0.1,
                    status=EmotionRecord.STATUS_REPAIRED,
                )
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(f"total_scanned: {total_scanned}")
        self.stdout.write(f"total_repaired: {total_repaired}")
        self.stdout.write(f"dry_run: {str(dry_run).lower()}")

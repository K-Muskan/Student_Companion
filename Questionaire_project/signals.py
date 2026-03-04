import logging

from django.db.models.signals import post_migrate
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_migrate)
def seed_question_catalog(sender, app_config=None, **kwargs):
    # Only run seeding for this app's migrations.
    if app_config is None or app_config.name != "Questionaire_project":
        return
    try:
        from .views import _ensure_questions_in_db

        _ensure_questions_in_db()
    except Exception:
        logger.exception("question_seed_post_migrate_failed")

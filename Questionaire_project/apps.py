from django.apps import AppConfig


class QuestionaireProjectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Questionaire_project'

    def ready(self):
        # Register signal handlers only. Do not query DB during app initialization.
        from . import signals  # noqa: F401

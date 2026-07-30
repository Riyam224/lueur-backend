from django.apps import AppConfig
from django.conf import settings


class TherapistConfig(AppConfig):
    name = 'therapist'
    verbose_name = 'Companion'

    def ready(self):
        # Refuse to boot in production/staging if a Luna prompt or the
        # Arabic crisis keyword list is still unshipped placeholder text —
        # see therapist/luna_prompts.py and therapist/crisis_ar.py.
        if settings.DEBUG or settings.TESTING:
            return
        from .crisis_ar import assert_no_placeholder_keywords
        from .luna_prompts import assert_no_placeholder_prompts

        assert_no_placeholder_prompts()
        assert_no_placeholder_keywords()

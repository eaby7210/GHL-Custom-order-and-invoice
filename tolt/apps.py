from django.apps import AppConfig


class ToltConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tolt'


    def ready(self):
        import tolt.signals  
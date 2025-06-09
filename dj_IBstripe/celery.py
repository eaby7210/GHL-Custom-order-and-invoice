from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dj_IBstripe.settings')

app = Celery('dj_IBstripe')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# Namespace 'CELERY' means all celery-related configs must start with 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# print("Loaded CELERY_BEAT_SCHEDULE:", settings.CELERY_BEAT_SCHEDULE)

app.conf.beat_schedule = settings.CELERY_BEAT_SCHEDULE
app.conf.update(timezone=settings.CELERY_TIMEZONE)
import os
from celery import Celery
from decouple import config

CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'linkreport.settings')

app = Celery('linkreport')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


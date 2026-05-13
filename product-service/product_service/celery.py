import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product_service.settings')

app = Celery('product_service')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Periodic tasks from the original recommendations app
app.conf.beat_schedule = {
    'compute-similarities-daily': {
        'task': 'recommendations.tasks.compute_product_similarities',
        'schedule': crontab(hour=2, minute=0),
    },
    'clear-expired-cache-hourly': {
        'task': 'recommendations.tasks.clear_expired_recommendation_cache',
        'schedule': crontab(minute=0),
    },
}

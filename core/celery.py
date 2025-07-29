import os
from celery import Celery

# تنظیم Django برای Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# تنظیمات Celery را از Django settings.py می‌خواند
app.config_from_object('django.conf:settings', namespace='CELERY')

# کشف خودکار تسک‌ها در تمام اپ‌های جنگو
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
import os
from celery import Celery
from celery.schedules import crontab

# مسیر تنظیمات Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# لود تنظیمات با پیشوند CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# شناسایی خودکار تسک‌ها
app.autodiscover_tasks()

# زمان‌بندی تسک‌ها
app.conf.beat_schedule = {
    # بررسی کمپین‌ها و ساخت پست‌ها هر روز ساعت 8 صبح
    'check_and_generate_due_posts_daily': {
        'task': 'accounts.tasks.check_and_generate_due_posts',
        'schedule': crontab(hour=8, minute=0),
    },
    # پاک کردن کمپین‌های منقضی هر روز ساعت 1 بامداد
    'cleanup_expired_campaigns_daily': {
        'task': 'accounts.tasks.cleanup_expired_campaigns',
        'schedule': crontab(hour=1, minute=0),
    },
    # ارسال ایمیل یادآوری هر 6 ساعت
    'send_campaign_reminder_emails': {
        'task': 'accounts.tasks.send_campaign_reminder_emails',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    # پاک‌سازی Assetهای بدون استفاده هر هفته یک‌بار
    'cleanup_unused_assets_weekly': {
        'task': 'accounts.tasks.cleanup_unused_assets',
        'schedule': crontab(hour=3, minute=0, day_of_week='sunday'),
    },
    # آپدیت وضعیت کمپین‌ها هر نیمه‌شب
    'update_campaign_status_midnight': {
        'task': 'accounts.tasks.update_campaign_status',
        'schedule': crontab(hour=0, minute=0),
    },
    # چک سلامت سیستم هر ساعت
    'health_check_hourly': {
        'task': 'accounts.tasks.health_check_task',
        'schedule': crontab(minute=0, hour='*'),
    },
}
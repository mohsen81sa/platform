import json
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from .models import Campaign, CampaignSchedule
from .tasks import schedule_campaign_posts
from django.utils import timezone


@receiver(post_save, sender=Campaign)
def create_initial_campaign_schedule(sender, instance, created, **kwargs):
    if created:
        first_run = instance.start_date or timezone.now()
        CampaignSchedule.objects.get_or_create(
            campaign=instance,
            defaults={
                'start_date': instance.start_date,
                'end_date': instance.end_date,
                'next_run_at': first_run,
                'is_enabled': True
            }
        )
        print(f"✅ Initial CampaignSchedule created for campaign {instance.id} with next_run_at={first_run}")

@receiver(post_save, sender=CampaignSchedule)
def update_next_run_on_schedule_save(sender, instance, created, **kwargs):
    if created or instance.next_run_at is None:
        next_run = instance.start_date or timezone.now()
        instance.next_run_at = next_run
        instance.is_enabled = True
        instance.save(update_fields=['next_run_at', 'is_enabled'])
        print(f"✅ next_run_at for CampaignSchedule {instance.id} set to {next_run}")

@receiver(post_save, sender=Campaign)
def campaign_created_handler(sender, instance, created, **kwargs):
    """
    وقتی کمپین جدید ساخته می‌شود:
    - اجرای فوری تسک schedule_campaign_posts
    - ثبت برنامه زمان‌بندی در Celery Beat بر اساس execution_period کمپین
    """
    if created:
        print(f"🚀 New campaign created: {instance.id} - {instance.title}")

        # اجرای فوری تسک برای ساخت پست‌های اولیه
        schedule_campaign_posts.delay()

        # -----------------------------
        # ساخت زمان‌بندی بر اساس execution_period
        # -----------------------------
        # اگر execution_period به روز باشد (مثلاً 3 یعنی هر سه روز)
        try:
            period_days = int(instance.execution_period)
        except (ValueError, TypeError):
            period_days = 1  # پیش‌فرض روزانه

        if period_days <= 0:
            period_days = 1

        # ساخت الگوی کرون برای اجرای هر N روز
        # کرون استاندارد پشتیبانی مستقیم از "هر N روز" ندارد، پس از day_of_month یا day_of_week استفاده می‌کنیم
        # اگر کمتر از 7 روز → تکرار در week-based pattern
        if period_days < 7:
            # هر چند روز یک‌بار بر اساس day_of_week
            day_of_week_pattern = ",".join(str(i) for i in range(0, 7, period_days))
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute='0',
                hour='10',
                day_of_week=day_of_week_pattern,
                day_of_month='*',
                month_of_year='*',
                timezone='Asia/Tehran'
            )
        else:
            # اگر بزرگتر مساوی یک هفته → از day_of_month استفاده می‌کنیم
            day_of_month_pattern = ",".join(str(i) for i in range(1, 32, period_days))
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute='0',
                hour='10',
                day_of_week='*',
                day_of_month=day_of_month_pattern,
                month_of_year='*',
                timezone='Asia/Tehran'
            )

        # ثبت در Celery Beat
        PeriodicTask.objects.create(
            crontab=schedule,
            name=f"Auto schedule posts for campaign {instance.id}",
            task='campaigns.tasks.schedule_campaign_posts',
            args=json.dumps([]),  # بدون پارامتر چون تسک خودش همه کمپین‌ها رو پیدا می‌کند
            start_time=instance.start_date,
            expires=instance.end_date
        )

        print(f"📅 Celery Beat periodic task created for campaign {instance.id} with execution_period={period_days} days")


@receiver(post_save, sender=CampaignSchedule)
def campaign_schedule_created_handler(sender, instance, created, **kwargs):
    """
    وقتی یک CampaignSchedule ساخته میشه:
    - یک periodic task با الگوی کرون‌تب مشخص در Celery Beat ثبت می‌کنه
    """
    if created and instance.is_enabled:
        # اگر crontab_schedule تعریف نشده بود، یک الگوی پیش‌فرض استفاده می‌کنیم
        crontab = getattr(instance, 'crontab_schedule', '0 10 * * 1')  # دوشنبه ساعت 10

        try:
            minute, hour, day_of_month, month_of_year, day_of_week = crontab.split()
        except ValueError:
            # اگر مقدار crontab نادرست بود، از پیش‌فرض استفاده کن
            minute, hour, day_of_month, month_of_year, day_of_week = '0', '10', '*', '*', '1'

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
            timezone='Asia/Tehran'
        )

        PeriodicTask.objects.create(
            crontab=schedule,
            name=f"Custom schedule for campaign {instance.campaign.id}",
            task='accounts.tasks.schedule_campaign_posts',
            args=json.dumps([instance.campaign.id]),
            start_time=instance.start_date,
            expires=instance.end_date
        )
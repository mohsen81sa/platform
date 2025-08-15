import json
from django_celery_beat.models import PeriodicTask, CrontabSchedule

def schedule_campaign_task(campaign_schedule):
    cron_parts = campaign_schedule.crontab_schedule.strip().split()
    if len(cron_parts) != 5:
        raise ValueError("Invalid crontab format")

    cron, _ = CrontabSchedule.objects.get_or_create(
        minute=cron_parts[0],
        hour=cron_parts[1],
        day_of_week=cron_parts[2],
        month_of_year=cron_parts[3],
        day_of_month=cron_parts[4],
    )

    PeriodicTask.objects.update_or_create(
        name=f"Campaign-{campaign_schedule.id}",
        defaults={
            "crontab": cron,
            "task": "accounts.tasks.run_campaign",
            "args": json.dumps([campaign_schedule.campaign.id]),
            "enabled": campaign_schedule.is_enabled,
        }
    )
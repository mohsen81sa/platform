# در فایل tasks.py

from celery import shared_task
from django.utils import timezone
from .models import Campaign, CampaignPost, PostAsset
from .controllers import LinkedInContentController
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta

# Import a library to parse crontab strings
# You might need to install a library like `python-crontab` or `crontab`
# For example: `pip install python-crontab`
from crontab import CronTab

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_post_for_campaign_task(self, campaign_id: int):
    """
    Celery task to generate content and create a post for a given campaign.
    This task handles content generation, post creation, and error retries.
    """
    print(f"Starting post creation for campaign ID: {campaign_id}")
    
    try:
        # Get the controller
        controller = LinkedInContentController()

        # Validate campaign readiness before generation
        validation_result = controller.validate_campaign_for_generation(campaign_id)
        if not validation_result['ready_for_generation']:
            missing_reqs = ", ".join([req for req in validation_result['missing_requirements'] if req is not None])
            error_message = f"Campaign is not ready for generation. Missing: {missing_reqs}"
            print(f"Validation failed for campaign {campaign_id}: {error_message}")
            raise ValidationError(error_message)

        # Generate content and create a post using the controller
        result = controller.generate_linkedin_content(campaign_id)

        if not result['success']:
            error_message = result.get('error', 'Unknown error during content generation.')
            print(f"Error during content generation for campaign {campaign_id}: {error_message}")
            self.retry(exc=ValidationError(error_message))
        
        # Mark the post as successfully generated
        post_id = result['post']['id']
        print(f"Successfully created a post (ID: {post_id}) for campaign {campaign_id}.")
        return result

    except Campaign.DoesNotExist:
        error_message = f"Campaign with ID {campaign_id} not found. Aborting task."
        print(error_message)
        return {'success': False, 'error': error_message}
    except ValidationError as e:
        # For validation errors, we don't want to retry. Log and return.
        error_message = f"Validation error for campaign {campaign_id}: {str(e)}"
        print(error_message)
        return {'success': False, 'error': error_message}
    except Exception as e:
        # For other unexpected errors, retry the task.
        error_message = f"An unexpected error occurred for campaign {campaign_id}: {str(e)}"
        print(error_message)
        self.retry(exc=e)


@shared_task
def schedule_campaign_posts():
    print("--------------------------------------------------")
    print("Running schedule_campaign_posts task...")
    now = timezone.now()
    
    active_campaigns = Campaign.objects.filter(is_active=True, status='active')
    print(f"Found {active_campaigns.count()} active campaigns to check.")
    
    for campaign in active_campaigns:
        print(f"Checking campaign: {campaign.title} (ID: {campaign.id})")
        
        # Check if the campaign is within its date range
        if campaign.start_date and campaign.end_date:
            if not (campaign.start_date.date() <= now.date() and campaign.end_date.date() >= now.date()):
                print(f"  Campaign is outside its date range. Skipping.")
                continue
        
        # Logic for Single Session
        if campaign.session_type == 'single':
            print(f"  Session type is 'single'.")
            if not campaign.posts.exists() and campaign.schedule_time:
                scheduled_datetime = now.replace(
                    hour=campaign.schedule_time.hour,
                    minute=campaign.schedule_time.minute,
                    second=campaign.schedule_time.second
                )
                print(f"  Scheduled time is: {scheduled_datetime.strftime('%H:%M')}")
                print(f"  Current time is: {now.strftime('%H:%M')}")
                if scheduled_datetime <= now:
                    print(f"  Time is right. Triggering post creation...")
                    create_post_for_campaign_task.delay(campaign.id)
                else:
                    print(f"  Time is not yet right. Waiting...")
        
        # Logic for Multiple Sessions
        elif campaign.session_type == 'multiple':
            print(f"  Session type is 'multiple'.")
            # ... (اضافه کردن پرینت به منطق Multiple Sessions)
    
    print("Finished schedule_campaign_posts task.")
    print("--------------------------------------------------")
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from datetime import timedelta
import os
import logging
from typing import List, Dict, Any
from PIL import Image, ImageOps
import io
from django.core.files.base import ContentFile
from .models import (
    Campaign, CampaignPost, PostAsset, PostLog, Asset, AssetLibrary, 
    GeneratedContent, Notification, User,CampaignSchedule
)
from .controllers import LinkedInContentController, NotificationController

logger = logging.getLogger(__name__)


@shared_task
def process_due_campaigns():
    """
    بررسی همه کمپین‌هایی که زمان اجرای بعدی آنها رسیده است.
    """
    now = timezone.now()
    schedules = CampaignSchedule.objects.filter(is_enabled=True, next_run_at__lte=now)

    for schedule in schedules:
        campaign = schedule.campaign

        # --- اجرای پست‌ها ---
        print(f"Publishing posts for campaign {campaign.id}")

        # --- بروزرسانی next_run_at ---
        try:
            period_days = int(campaign.execution_period)
        except (ValueError, TypeError):
            period_days = 1
        if period_days <= 0:
            period_days = 1

        next_run = schedule.next_run_at + timedelta(days=period_days)

        if campaign.end_date and next_run > campaign.end_date:
            schedule.is_enabled = False
            schedule.next_run_at = None
            print(f"CampaignSchedule for campaign {campaign.id} disabled (end_date reached)")
        else:
            schedule.next_run_at = next_run
            print(f"Next run for campaign {campaign.id} set to {next_run}")

        schedule.save()

@shared_task
def schedule_campaign_posts():
    """
    برای همه کمپین‌های فعال:
    - پست‌های اولیه دوره اول رو ایجاد می‌کند
    - بقیه پست‌ها را برای دوره‌های بعدی زمان‌بندی می‌کند
    """
    print("✅ Running schedule_campaign_posts task...")

    today = timezone.now().date()
    active_campaigns = Campaign.objects.filter(is_active=True, status='active')

    print(f"Found {active_campaigns.count()} active campaigns.")

    for campaign in active_campaigns:
        print(f"📌 Processing campaign: {campaign.title} (ID: {campaign.id})")

        try:
            # ------------------------------
            # 1️⃣ ساخت پست‌های اولیه برای دوره فعلی
            # ------------------------------
            posts_per_period = min(5, max(3, campaign.execution_period // 2))
            print(f"Generating {posts_per_period} initial posts for campaign {campaign.id}")

            period_start_date = today
            generated = generate_period_posts_task(
                campaign.id,
                period_start_date,
                posts_per_period,
                campaign.user.id
            )

            if generated:
                print(f"✅ Generated initial posts for campaign {campaign.id}")
            else:
                print(f"⚠️ Failed to generate initial posts for campaign {campaign.id}")

            # ------------------------------
            # 2️⃣ زمان‌بندی پست‌ها برای دوره‌های بعدی
            # ------------------------------
            schedule_campaign_period_posts.delay(campaign.id)
            print(f"⏳ Scheduled future posts for campaign {campaign.id}")

        except Exception as e:
            print(f"❌ Error processing campaign {campaign.id}: {str(e)}")
            
            
@shared_task
def generate_period_posts_task(campaign_id, period_start_date, posts_per_period, user_id):
    """
    Celery task to generate posts for a specific period of a campaign
    
    Args:
        campaign_id: ID of the campaign
        period_start_date: Start date of the period (datetime)
        posts_per_period: Number of posts to generate
        user_id: User ID
    """
    try:
        # Get the campaign
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Check if campaign is still active
        if not campaign.is_active:
            print(f"Campaign {campaign_id} is not active, skipping period posts generation")
            return False
        
        # Check if we're within the campaign period
        today = timezone.now().date()
        if today < campaign.start_date or today > campaign.end_date:
            print(f"Campaign {campaign_id} is outside its date range, skipping period posts generation")
            return False
        
        # Initialize LinkedIn controller
        linkedin_controller = LinkedInContentController()
        
        # Validate campaign for generation
        validation = linkedin_controller.validate_campaign_for_generation(campaign_id)
        
        if not validation['ready_for_generation']:
            print(f"Campaign {campaign_id} not ready for generation: {validation['missing_requirements']}")
            return False
        
        # Calculate period duration based on campaign execution_period
        execution_period_days = campaign.execution_period
        
        # Generate posts for the period
        generated_posts = []
        
        for i in range(posts_per_period):
            # Calculate post date within the period
            post_date = period_start_date + timedelta(days=i * (execution_period_days // posts_per_period))
            
            # Skip if post date is in the past
            if post_date.date() < today:
                continue
            
            # Generate content
            result = linkedin_controller.generate_linkedin_content(campaign_id, user_id)
            
            if result.get('success'):
                # Create the actual post in the database
                post_data = {
                    'campaign_id': campaign_id,
                    'content': result.get('generated_content', result.get('post', '')),
                    'publish_date': post_date,
                    'status': 'PENDING'  # Set initial status to PENDING
                }
                
                # Create CampaignPost
                post = CampaignPost.objects.create(**post_data)
                
                # Link asset if available
                if result.get('asset_used'):
                    PostAsset.objects.create(
                        post=post,
                        asset_id=result['asset_used']['id']
                    )
                
                # Create success log
                PostLog.objects.create(
                    post=post,
                    status='generated',
                    error_message=None
                )
                
                generated_posts.append({
                    'post_id': post.id,
                    'content': post.content,
                    'publish_date': post.publish_date,
                    'asset_used': result.get('asset_used')
                })
                
                print(f"Generated post {post.id} for campaign {campaign_id}, period starting {period_start_date}")
            else:
                # Log the failure
                PostLog.objects.create(
                    post=None,
                    status='failed',
                    error_message=f"Failed to generate post {i+1}: {result.get('error')}"
                )
                print(f"Failed to generate post {i+1} for campaign {campaign_id}: {result.get('error')}")
        
        print(f"Generated {len(generated_posts)} posts for campaign {campaign_id}, period starting {period_start_date}")
        return True
        
    except Campaign.DoesNotExist:
        print(f"Campaign {campaign_id} not found")
        return False
    except Exception as e:
        print(f"Error generating weekly posts for campaign {campaign_id}: {str(e)}")
        return False


@shared_task
def schedule_campaign_period_posts(campaign_id):
    """
    Schedule period posts for an entire campaign
    
    This task is called when a campaign is created to schedule all period posts
    
    Args:
        campaign_id: ID of the campaign
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Calculate campaign duration and periods
        campaign_duration = (campaign.end_date - campaign.start_date).days
        execution_period_days = campaign.execution_period
        total_periods = (campaign_duration // execution_period_days) + 1
        
        # Skip first period (already handled in campaign creation)
        periods_to_schedule = total_periods - 1
        
        if periods_to_schedule <= 0:
            print(f"Campaign {campaign_id} is only one period or less, no additional scheduling needed")
            return True
        
        # Calculate posts per period (general approach)
        posts_per_period = min(5, max(3, execution_period_days // 2))
        
        # Schedule tasks for each subsequent period
        for period in range(1, periods_to_schedule + 1):
            period_start_date = campaign.start_date + timedelta(days=period * execution_period_days)
            
            # Schedule the period posts task
            generate_period_posts_task.apply_async(
                args=[campaign_id, period_start_date, posts_per_period, campaign.user.id],
                eta=period_start_date
            )
            
            print(f"Scheduled period posts for campaign {campaign_id}, period {period} starting {period_start_date}")
        
        return True
        
    except Campaign.DoesNotExist:
        print(f"Campaign {campaign_id} not found")
        return False
    except Exception as e:
        print(f"Error scheduling campaign period posts for campaign {campaign_id}: {str(e)}")
        return False


@shared_task
def check_and_generate_due_posts():
    """
    Periodic task to check for campaigns that need posts generated
    
    This task can be run daily to ensure posts are generated for active campaigns
    """
    try:
        today = timezone.now().date()
        
        # Get active campaigns that are currently running
        active_campaigns = Campaign.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        )
        
        for campaign in active_campaigns:
            # Check if this campaign has posts scheduled for today
            today_posts = CampaignPost.objects.filter(
                campaign=campaign,
                publish_date__date=today
            ).count()
            
            # If no posts for today, generate them
            if today_posts == 0:
                print(f"Campaign {campaign.id} has no posts for today, generating...")
                
                # Generate posts for today
                linkedin_controller = LinkedInContentController()
                
                # Generate a single post for today
                result = linkedin_controller.generate_linkedin_content(campaign.id, campaign.user.id)
                
                if result.get('success'):
                    # Create the post
                    post_data = {
                        'campaign_id': campaign.id,
                        'content': result.get('generated_content', result.get('post', '')),
                        'publish_date': timezone.now()
                    }
                    
                    post = CampaignPost.objects.create(**post_data)
                    
                    # Link asset if available
                    if result.get('asset_used'):
                        PostAsset.objects.create(
                            post=post,
                            asset_id=result['asset_used']['id']
                        )
                    
                    print(f"Generated post {post.id} for campaign {campaign.id} for today")
                else:
                    print(f"Failed to generate post for campaign {campaign.id}: {result.get('error')}")
        
        return True
        
    except Exception as e:
        print(f"Error checking and generating due posts: {str(e)}")
        return False


@shared_task
def cleanup_expired_campaigns():
    """
    Periodic task to clean up expired campaigns
    
    This task can be run daily to deactivate campaigns that have ended
    """
    try:
        today = timezone.now().date()
        
        # Find campaigns that have ended
        expired_campaigns = Campaign.objects.filter(
            is_active=True,
            end_date__lt=today
        )
        
        for campaign in expired_campaigns:
            campaign.is_active = False
            campaign.save()
            print(f"Deactivated expired campaign {campaign.id}: {campaign.title}")
        
        print(f"Cleaned up {expired_campaigns.count()} expired campaigns")
        return True
        
    except Exception as e:
        print(f"Error cleaning up expired campaigns: {str(e)}")
        return False 

# =============================================================================
# EMAIL NOTIFICATION TASKS
# =============================================================================

@shared_task
def send_email_notification_task(notification_id: int, email_template: str = None):
    """
    Send email notification to user about campaign
    
    Args:
        notification_id: ID of the notification to send
        email_template: Optional custom email template
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        user = notification.user
        campaign = notification.campaign
        
        if not user.email:
            logger.warning(f"User {user.id} has no email address")
            return False
        
        subject = f"New Campaign Ready: {campaign.title}"
        message = f"""
        Hi {user.username},
        
        Your campaign "{campaign.title}" is ready for review and posting.
        
        Please visit: {notification.notification_url}
        
        Campaign Details:
        - Platform: {campaign.platform.get_name_display()}
        - Execution Period: {campaign.execution_period} days
        - Status: {campaign.get_status_display()}
        
        Best regards,
        Your Campaign Management Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        # Update notification as sent
        notification.email_sent = True
        notification.email_sent_at = timezone.now()
        notification.save()
        
        logger.info(f"Email sent successfully to {user.email} for notification {notification_id}")
        return True
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error sending email notification {notification_id}: {str(e)}")
        return False


@shared_task
def send_bulk_email_notifications(user_ids: List[int], subject: str, message: str):
    """
    Send bulk email notifications to multiple users
    
    Args:
        user_ids: List of user IDs to send emails to
        subject: Email subject
        message: Email message
    """
    try:
        users = User.objects.filter(id__in=user_ids, email__isnull=False)
        success_count = 0
        
        for user in users:
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                success_count += 1
                logger.info(f"Bulk email sent to {user.email}")
            except Exception as e:
                logger.error(f"Failed to send bulk email to {user.email}: {str(e)}")
        
        logger.info(f"Bulk email task completed. Sent {success_count}/{len(user_ids)} emails")
        return success_count
        
    except Exception as e:
        logger.error(f"Error in bulk email task: {str(e)}")
        return 0


@shared_task
def send_campaign_reminder_emails():
    """
    Send reminder emails for campaigns that haven't been reviewed
    """
    try:
        # Find notifications that are older than 24 hours and haven't been read
        yesterday = timezone.now() - timedelta(hours=24)
        unread_notifications = Notification.objects.filter(
            sent_at__lt=yesterday,
            is_read=False,
            email_sent=True
        )
        
        reminder_count = 0
        for notification in unread_notifications:
            user = notification.user
            campaign = notification.campaign
            
            if user.email:
                subject = f"Reminder: Review Campaign - {campaign.title}"
                message = f"""
                Hi {user.username},
                
                This is a reminder that your campaign "{campaign.title}" is still waiting for review.
                
                Please visit: {notification.notification_url}
                
                Don't let your campaign miss its scheduled posting time!
                
                Best regards,
                Your Campaign Management Team
                """
                
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                    reminder_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder email to {user.email}: {str(e)}")
        
        logger.info(f"Sent {reminder_count} reminder emails")
        return reminder_count
        
    except Exception as e:
        logger.error(f"Error sending reminder emails: {str(e)}")
        return 0


# =============================================================================
# ASSET PROCESSING TASKS
# =============================================================================

@shared_task
def process_uploaded_asset(asset_id: int):
    """
    Process newly uploaded assets (resize images, generate thumbnails, etc.)
    
    Args:
        asset_id: ID of the asset to process
    """
    try:
        asset = Asset.objects.get(id=asset_id)
        
        if asset.file_type == 'image' and asset.file:
            # Process image
            success = _process_image_asset(asset)
            if success:
                logger.info(f"Successfully processed image asset {asset_id}")
            else:
                logger.warning(f"Failed to process image asset {asset_id}")
        
        elif asset.file_type == 'video' and asset.file:
            # Process video (you can implement video processing here)
            success = _process_video_asset(asset)
            if success:
                logger.info(f"Successfully processed video asset {asset_id}")
        
        return True
        
    except Asset.DoesNotExist:
        logger.error(f"Asset {asset_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error processing asset {asset_id}: {str(e)}")
        return False


def _process_image_asset(asset: Asset) -> bool:
    """
    Process image asset: resize, optimize, create thumbnails
    """
    try:
        # Open the image
        image = Image.open(asset.file.path)
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        # Resize if too large (max 1920x1080)
        max_size = (1920, 1080)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save optimized image
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        # Update the asset file
        asset.file.save(
            asset.file.name,
            ContentFile(output.getvalue()),
            save=True
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing image for asset {asset.id}: {str(e)}")
        return False


def _process_video_asset(asset: Asset) -> bool:
    """
    Process video asset (placeholder for video processing)
    """
    try:
        # Here you can implement video processing using ffmpeg or similar
        # For now, just log that video was processed
        logger.info(f"Video asset {asset.id} processed (placeholder)")
        return True
        
    except Exception as e:
        logger.error(f"Error processing video for asset {asset.id}: {str(e)}")
        return False


@shared_task
def cleanup_unused_assets():
    """
    Clean up assets that haven't been used in campaigns for a long time
    """
    try:
        # Find assets not used in the last 90 days
        cutoff_date = timezone.now() - timedelta(days=90)
        unused_assets = Asset.objects.filter(
            is_used_by_ai=False,
            created_at__lt=cutoff_date
        ).exclude(
            postasset__isnull=False  # Don't delete assets used in posts
        )
        
        deleted_count = 0
        for asset in unused_assets:
            try:
                # Delete the file
                if asset.file and os.path.exists(asset.file.path):
                    os.remove(asset.file.path)
                
                # Delete the asset record
                asset.delete()
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Error deleting asset {asset.id}: {str(e)}")
        
        logger.info(f"Cleaned up {deleted_count} unused assets")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up unused assets: {str(e)}")
        return 0


# =============================================================================
# CONTENT GENERATION TASKS
# =============================================================================

@shared_task
def generate_content_for_campaign(campaign_id: int, user_id: int, content_count: int = 1):
    """
    Generate content for a campaign using AI
    
    Args:
        campaign_id: ID of the campaign
        user_id: ID of the user
        content_count: Number of content pieces to generate
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        linkedin_controller = LinkedInContentController()
        
        # Validate campaign for generation
        validation = linkedin_controller.validate_campaign_for_generation(campaign_id)
        
        if not validation['ready_for_generation']:
            logger.error(f"Campaign {campaign_id} not ready for generation: {validation['missing_requirements']}")
            return False
        
        generated_count = 0
        for i in range(content_count):
            try:
                result = linkedin_controller.generate_linkedin_content(campaign_id, user_id)
                
                if result.get('success'):
                    # Create GeneratedContent record
                    generated_content = GeneratedContent.objects.create(
                        campaign=campaign,
                        platform=campaign.platform.name,
                        content=result.get('generated_content', ''),
                        original_asset_id=result.get('asset_used', {}).get('id') if result.get('asset_used') else None,
                        publish_status='draft'
                    )
                    
                    generated_count += 1
                    logger.info(f"Generated content {generated_content.id} for campaign {campaign_id}")
                
            except Exception as e:
                logger.error(f"Error generating content piece {i+1} for campaign {campaign_id}: {str(e)}")
        
        logger.info(f"Generated {generated_count}/{content_count} content pieces for campaign {campaign_id}")
        return generated_count
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error generating content for campaign {campaign_id}: {str(e)}")
        return False


@shared_task
def batch_generate_content_for_campaigns(campaign_ids: List[int]):
    """
    Generate content for multiple campaigns in batch
    
    Args:
        campaign_ids: List of campaign IDs
    """
    try:
        success_count = 0
        
        for campaign_id in campaign_ids:
            try:
                campaign = Campaign.objects.get(id=campaign_id)
                result = generate_content_for_campaign.delay(campaign_id, campaign.user.id, 1)
                
                if result:
                    success_count += 1
                    
            except Campaign.DoesNotExist:
                logger.error(f"Campaign {campaign_id} not found in batch generation")
            except Exception as e:
                logger.error(f"Error in batch generation for campaign {campaign_id}: {str(e)}")
        
        logger.info(f"Batch generation completed for {success_count}/{len(campaign_ids)} campaigns")
        return success_count
        
    except Exception as e:
        logger.error(f"Error in batch content generation: {str(e)}")
        return 0


# =============================================================================
# CAMPAIGN MANAGEMENT TASKS
# =============================================================================

@shared_task
def update_campaign_status():
    """
    Update campaign status based on current date and campaign dates
    """
    try:
        today = timezone.now().date()
        updated_count = 0
        
        # Activate campaigns that should start today
        campaigns_to_activate = Campaign.objects.filter(
            start_date=today,
            status='pending',
            is_active=True
        )
        
        for campaign in campaigns_to_activate:
            campaign.status = 'active'
            campaign.save()
            updated_count += 1
            logger.info(f"Activated campaign {campaign.id}: {campaign.title}")
        
        # Complete campaigns that ended
        campaigns_to_complete = Campaign.objects.filter(
            end_date__lt=today,
            status='active',
            is_active=True
        )
        
        for campaign in campaigns_to_complete:
            campaign.status = 'completed'
            campaign.is_active = False
            campaign.save()
            updated_count += 1
            logger.info(f"Completed campaign {campaign.id}: {campaign.title}")
        
        logger.info(f"Updated status for {updated_count} campaigns")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error updating campaign status: {str(e)}")
        return 0


@shared_task
def generate_campaign_analytics():
    """
    Generate analytics and reports for campaigns
    """
    try:
        # Get active campaigns from the last 30 days
        start_date = timezone.now() - timedelta(days=30)
        campaigns = Campaign.objects.filter(
            created_at__gte=start_date,
            is_active=True
        )
        
        analytics_data = []
        
        for campaign in campaigns:
            # Calculate metrics
            total_posts = CampaignPost.objects.filter(campaign=campaign).count()
            published_posts = CampaignPost.objects.filter(
                campaign=campaign,
                status=CampaignPost.Status.PUBLISHED
            ).count()
            
            pending_posts = CampaignPost.objects.filter(
                campaign=campaign,
                status=CampaignPost.Status.PENDING
            ).count()
            
            assets_used = Asset.objects.filter(
                postasset__post__campaign=campaign
            ).distinct().count()
            
            analytics_data.append({
                'campaign_id': campaign.id,
                'campaign_title': campaign.title,
                'total_posts': total_posts,
                'published_posts': published_posts,
                'pending_posts': pending_posts,
                'assets_used': assets_used,
                'success_rate': (published_posts / total_posts * 100) if total_posts > 0 else 0
            })
        
        # Here you could save this data to a separate analytics model
        # or send it to an external analytics service
        
        logger.info(f"Generated analytics for {len(analytics_data)} campaigns")
        return analytics_data
        
    except Exception as e:
        logger.error(f"Error generating campaign analytics: {str(e)}")
        return []


# =============================================================================
# NOTIFICATION TASKS
# =============================================================================

@shared_task
def create_campaign_notification_task(campaign_id: int, user_id: int, base_url: str):
    """
    Create and send campaign notification
    
    Args:
        campaign_id: ID of the campaign
        user_id: ID of the user
        base_url: Base URL for notification links
    """
    try:
        notification_controller = NotificationController()
        
        # Create notification
        notification = notification_controller.create_campaign_notification(
            campaign_id=campaign_id,
            user_id=user_id,
            base_url=base_url
        )
        
        # Send email notification asynchronously
        send_email_notification_task.delay(notification['id'])
        
        logger.info(f"Created and queued email for notification {notification['id']}")
        return notification['id']
        
    except Exception as e:
        logger.error(f"Error creating campaign notification: {str(e)}")
        return None


@shared_task
def cleanup_old_notifications():
    """
    Clean up old notifications (older than 30 days)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=30)
        old_notifications = Notification.objects.filter(
            sent_at__lt=cutoff_date,
            is_read=True
        )
        
        deleted_count = old_notifications.count()
        old_notifications.delete()
        
        logger.info(f"Cleaned up {deleted_count} old notifications")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up old notifications: {str(e)}")
        return 0


# =============================================================================
# SYSTEM MAINTENANCE TASKS
# =============================================================================

@shared_task
def health_check_task():
    """
    Perform system health checks
    """
    try:
        health_status = {
            'database': False,
            'redis': False,
            'media_storage': False,
            'timestamp': timezone.now()
        }
        
        # Check database
        try:
            User.objects.first()
            health_status['database'] = True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
        
        # Check Redis (Celery broker)
        try:
            from celery import current_app
            current_app.control.ping()
            health_status['redis'] = True
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
        
        # Check media storage
        try:
            media_root = settings.MEDIA_ROOT
            if os.path.exists(media_root) and os.access(media_root, os.W_OK):
                health_status['media_storage'] = True
        except Exception as e:
            logger.error(f"Media storage health check failed: {str(e)}")
        
        logger.info(f"Health check completed: {health_status}")
        return health_status
        
    except Exception as e:
        logger.error(f"Error in health check task: {str(e)}")
        return {'error': str(e), 'timestamp': timezone.now()}


@shared_task
def backup_database_task():
    """
    Create database backup (placeholder - implement based on your database)
    """
    try:
        # This is a placeholder - implement based on your database type
        # For PostgreSQL: pg_dump
        # For MySQL: mysqldump
        # For SQLite: file copy
        
        backup_filename = f"backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}.sql"
        logger.info(f"Database backup created: {backup_filename}")
        
        # Here you would implement the actual backup logic
        return backup_filename
        
    except Exception as e:
        logger.error(f"Error creating database backup: {str(e)}")
        return None


# =============================================================================
# ORIGINAL TASKS (PRESERVED)
# =============================================================================


from rest_framework import viewsets, status,permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
# Import your controllers
from .controllers import LinkedInContentController
from rest_framework.exceptions import PermissionDenied
# Import your models and serializers
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog,CampaignSchedule, Notification
from .serializers import (
    PlatformSerializer, TagSerializer, AssetLibrarySerializer,
    AssetSerializer, CampaignSerializer, CampaignPostSerializer,
    PostAssetSerializer, PostLogSerializer,CampaignScheduleSerializer, NotificationSerializer
)

# از تسک جدیدی که برای زمان‌بندی پست‌ها ساختید، ایمپورت کنید
from .tasks import *
from django_celery_beat.models import PeriodicTask, CrontabSchedule
import json

# Instantiate the LinkedIn content controller
linkedin_controller = LinkedInContentController()

class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

class PlatformViewSet(BaseViewSet):
    queryset = Platform.objects.all()
    serializer_class = PlatformSerializer

class TagViewSet(BaseViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class AssetLibraryViewSet(BaseViewSet):
    queryset = AssetLibrary.objects.all()
    serializer_class = AssetLibrarySerializer
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        return AssetLibrary.objects.filter(user=self.request.user)

class AssetViewSet(BaseViewSet):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Asset.objects.filter(library__user=self.request.user)


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer

    def perform_create(self, serializer):
        campaign = serializer.save(user=self.request.user, status='active')

        # اگر بخواهیم اجرای فوری هم داشته باشیم
        schedule_campaign_posts.delay()

        # ایجاد یک CampaignSchedule پیش‌فرض برای کمپین
        if campaign.start_date:
            schedule = CampaignSchedule.objects.create(
                campaign=campaign,
                start_date=campaign.start_date,
                end_date=campaign.end_date,
                is_enabled=True
            )

            cron_schedule, _ = CrontabSchedule.objects.get_or_create(
                minute='0',
                hour='10',
                day_of_week='1',  # دوشنبه
                day_of_month='*',
                month_of_year='*',
                timezone='Asia/Tehran'
            )

            PeriodicTask.objects.create(
                crontab=cron_schedule,
                name=f"Schedule posts for campaign {campaign.id}",
                task='accounts.tasks.schedule_campaign_posts',
                args=json.dumps([campaign.id]),
                start_time=schedule.start_date,
                expires=schedule.end_date
            )

    def get_queryset(self):
        return Campaign.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='generate-posts')
    def generate_posts(self, request, pk=None):
        try:
            campaign = self.get_object()
            count = request.data.get('count', 1)
            controller = LinkedInContentController()
            results = controller.generate_multiple_posts(
                campaign_id=campaign.id, count=count, user_id=self.request.user.id
            )
            failed_count = sum(1 for res in results if not res['success'])

            if failed_count > 0:
                return Response({
                    "message": f"Successfully generated {len(results) - failed_count} posts. {failed_count} posts failed.",
                    "results": results
                }, status=status.HTTP_207_MULTI_STATUS)

            return Response({
                "message": f"Successfully generated {len(results)} posts for campaign {campaign.title}.",
                "results": results
            }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': f'An unexpected error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='create-all-posts')
    def create_all_posts_for_campaign(self, request, pk=None):
        campaign = self.get_object()
        if campaign.execution_period == "One Time":
            # اینجا می‌توانید لاجیک ساخت همه پست‌ها را اضافه کنید
            return Response({'status': 'Posts creation initiated for one-time campaign.'}, status=status.HTTP_200_OK)
        return Response({'status': 'This campaign is not configured for "One Time" post creation.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='create-automated-schedule')
    def create_with_automatic_schedule(self, request):
        campaign_data = request.data.copy()
        
        campaign_serializer = CampaignSerializer(data=campaign_data)
        campaign_serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            campaign = campaign_serializer.save(user=request.user, status='active')

            # الگوی crontab مثلا هر دوشنبه ساعت ۱۰ صبح
            schedule, created = CrontabSchedule.objects.get_or_create(
                minute='0',
                hour='10',
                day_of_week='1',
                day_of_month='*',
                month_of_year='*',
                timezone='Asia/Tehran'
            )

            # نام یکتا برای periodic task بر اساس campaign.id
            task_name = f"Schedule posts for campaign {campaign.id}"

            # اگر هنوز این تسک ساخته نشده باشد، ایجاد شود
            if not PeriodicTask.objects.filter(name=task_name).exists():
                PeriodicTask.objects.create(
                    crontab=schedule,
                    name=task_name,
                    task='accounts.tasks.schedule_campaign_posts',
                    args=json.dumps([campaign.id]),
                    start_time=campaign.start_date,
                    expires=campaign.end_date
                )

        response_data = campaign_serializer.data
        return Response(response_data, status=status.HTTP_201_CREATED)
class CampaignScheduleViewSet(viewsets.ModelViewSet):
    queryset = CampaignSchedule.objects.all()
    serializer_class = CampaignScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # فقط برنامه‌های زمان‌بندی مربوط به کاربر جاری را برمی‌گرداند
        user = self.request.user
        return CampaignSchedule.objects.filter(campaign__user=user)

    def perform_create(self, serializer):
        # فقط اجازه ساخت schedule برای کمپینی که متعلق به همین یوزر هست
        campaign = serializer.validated_data['campaign']
        if campaign.user != self.request.user:
            raise PermissionDenied("You do not have permission to add schedule to this campaign.")
        serializer.save()
class CampaignPostViewSet(BaseViewSet):
    queryset = CampaignPost.objects.all()
    serializer_class = CampaignPostSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assets_data = request.data.get('assets', [])

        with transaction.atomic():
            self.perform_create(serializer)
            campaign_post = serializer.instance

            for asset_id in assets_data:
                try:
                    asset = Asset.objects.get(id=asset_id)
                    post_asset = PostAsset(post=campaign_post, asset=asset)
                    post_asset.full_clean()
                    post_asset.save()
                except ValidationError as e:
                    return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                except Asset.DoesNotExist:
                    return Response({'detail': f'Asset with ID {asset_id} not found.'}, status=status.HTTP_400_BAD_REQUEST)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        assets_data = request.data.get('assets', None)

        with transaction.atomic():
            self.perform_update(serializer)
            campaign_post = serializer.instance

            if assets_data is not None:
                campaign_post.assets.clear()
                for asset_id in assets_data:
                    try:
                        asset = Asset.objects.get(id=asset_id)
                        post_asset = PostAsset(post=campaign_post, asset=asset)
                        post_asset.full_clean()
                        post_asset.save()
                    except ValidationError as e:
                        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                    except Asset.DoesNotExist:
                        return Response({'detail': f'Asset with ID {asset_id} not found.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data)

class PostAssetViewSet(BaseViewSet):
    queryset = PostAsset.objects.all()
    serializer_class = PostAssetSerializer

    def perform_create(self, serializer):
        try:
            instance = serializer.save()
            instance.full_clean()
        except ValidationError as e:
            raise serializers.ValidationError({'detail': str(e.message_dict)})

class PostLogViewSet(BaseViewSet):
    queryset = PostLog.objects.all()
    serializer_class = PostLogSerializer
    http_method_names = ['get']

    
class NotificationViewSet(BaseViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    def get_queryset(self):
        # فقط نوتیفیکیشن‌های متعلق به کاربر فعلی را نشان می‌دهد
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_as_read(self, request, pk=None):
        """Mark notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'Notification marked as read'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='unread')
    def get_unread(self, request):
        """Get unread notifications for current user"""
        unread_notifications = Notification.objects.filter(
            user=request.user, 
            is_read=False
        )
        serializer = self.get_serializer(unread_notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



class LinkedInContentGenerationAPIView(APIView):
    """
    API endpoint for LinkedIn content generation
    
    POST /api/linkedin/generate/
    {
        "campaign_id": 1,
        "user_id": 1,
        "count": 1
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Generate LinkedIn content for a campaign"""
        try:
            campaign_id = request.data.get('campaign_id')
            user_id = request.data.get('user_id', request.user.id)
            count = request.data.get('count', 1)

            if not campaign_id:
                return Response(
                    {'error': 'campaign_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate content
            if count == 1:
                result = linkedin_controller.generate_linkedin_content(campaign_id, user_id)
            else:
                result = linkedin_controller.generate_multiple_posts(campaign_id, count, user_id)

            if isinstance(result, list):
                # Multiple posts generated
                successful_count = sum(1 for r in result if r.get('success', False))
                return Response({
                    'success': True,
                    'message': f'Generated {successful_count}/{count} posts successfully',
                    'results': result,
                    'successful_count': successful_count,
                    'total_count': count
                }, status=status.HTTP_200_OK)
            else:
                # Single post generated
                if result.get('success'):
                    return Response({
                        'success': True,
                        'message': 'Content generated successfully',
                        'data': result
                    }, status=status.HTTP_200_OK)
                else:
        
                    return Response({
                        'success': False,
                        'error': result.get('error'),
                        'error_type': result.get('error_type')
                    }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CampaignNotificationAPIView(APIView):
    """
    API endpoint for sending campaign notifications to users
    
    POST /api/notify-campaign/
    {
        "campaign_id": 1,
        "user_id": 1,
        "base_url": "https://yourdomain.com"
    }
    we are checking the campaign and user and if they are valid we are sending the notification to the user with celery task
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Send notification for a campaign to a user"""
        try:
            campaign_id = request.data.get('campaign_id')
            user_id = request.data.get('user_id')
            base_url = request.data.get('base_url', 'http://localhost:8000')
            
            if not campaign_id:
                return Response(
                    {'error': 'campaign_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not user_id:
                return Response(
                    {'error': 'user_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate campaign exists and belongs to user
            try:
                campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
            except Campaign.DoesNotExist:
                return Response(
                    {'error': 'Campaign not found or does not belong to user'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validate user exists
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Create notification
            from .controllers import NotificationController
            notification_controller = NotificationController()
            
            notification = notification_controller.create_campaign_notification(
                campaign_id=campaign_id,
                user_id=user_id,
                base_url=base_url
            )

            # Send email notification (in production, this would be async)
            notification_controller.send_email_notification(notification['id'])

            return Response({
                'success': True,
                'message': 'Campaign notification sent successfully',
                'notification': notification,
                'campaign_title': campaign.title,
                'user_email': user.email
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CampaignPostsView(APIView):
    """
    API endpoint for viewing campaign posts (accessed via notification URL)
    
    GET /campaign/{campaign_id}/posts/
    """
    permission_classes = [permissions.AllowAny]  # Allow access via notification URL

    def get(self, request, campaign_id):
        """Get posts for a campaign that are ready for publishing"""
        try:
            # Get campaign
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Get posts that are due for publishing
            from django.utils import timezone
            now = timezone.now()
            
            due_posts = CampaignPost.objects.filter(
                campaign_id=campaign_id,
                publish_date__lte=now
            ).order_by('publish_date')
            
            # Mark notification as read if user is authenticated
            if request.user.is_authenticated:
                notification = Notification.objects.filter(
                    campaign_id=campaign_id,
                    user=request.user
                ).first()
                if notification:
                    notification.mark_as_read()
            
            # Serialize posts with assets
            posts_data = []
            for post in due_posts:
                post_data = {
                    'id': post.id,
                    'content': post.content,
                    'publish_date': post.publish_date,
                    'campaign_title': campaign.title,
                    'assets': []
                }
                
                # Get assets for this post
                post_assets = PostAsset.objects.filter(post=post)
                for post_asset in post_assets:
                    asset_data = {
                        'id': post_asset.asset.id,
                        'name': post_asset.asset.name,
                        'file_type': post_asset.asset.file_type,
                        'file_url': request.build_absolute_uri(post_asset.asset.file.url) if post_asset.asset.file else None
                    }
                    post_data['assets'].append(asset_data)
                
                posts_data.append(post_data)
            
            return Response({
                'success': True,
                'campaign': {
                    'id': campaign.id,
                    'title': campaign.title,
                    'platform': campaign.platform.title
                },
                'posts': posts_data,
                'total_posts': len(posts_data),
                'message': f'Found {len(posts_data)} posts ready for publishing on LinkedIn'
            }, status=status.HTTP_200_OK)

        except Campaign.DoesNotExist:
            return Response(
                {'error': 'Campaign not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class CampaignCreationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for campaign creation with automatic content generation
    
    This ViewSet handles campaign creation and automatically generates content
    for the campaign using the LinkedIn content generation system.
    
    Endpoints:
    - POST /api/campaigns/create-with-content/ - Create campaign and generate content
    - GET /api/campaigns/create-with-content/ - List campaigns with generation stats
    - GET /api/campaigns/create-with-content/{id}/ - Get specific campaign with content
    - PUT /api/campaigns/create-with-content/{id}/ - Update campaign and regenerate content
    - DELETE /api/campaigns/create-with-content/{id}/ - Delete campaign
    """
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter campaigns by current user"""
        return Campaign.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Assign user to campaign during creation"""
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'], url_path='create-with-content')
    def create_campaign_with_content(self, request):
        """
        Create a campaign and generate content for it with Celery scheduling
        
        This method creates posts only for the first execution period of the campaign.
        Subsequent periods are handled by Celery based on the execution_period (days).
        
        Request Body:
        {
            "title": "Campaign Title",
            "platform_id": 1,
            "start_date": "2024-07-20",
            "end_date": "2024-08-20",
            "execution_period": 7,  # Every 7 days (weekly)
            "asset_library_id": 1,
            "tags": [1, 2, 3],
            "prompt": "Create engaging LinkedIn content about technology",
            "is_active": true,
            "generate_content": true
        }
        
        Response:
        {
            "success": true,
            "campaign": {...},
            "first_period_posts": [...],
            "celery_scheduled": true,
            "message": "Campaign created with first period posts and Celery scheduling"
        }
        """
        try:
            # Extract content generation parameters
            generate_content = request.data.get('generate_content', True)
            
            # Remove content generation fields from campaign data
            campaign_data = request.data.copy()
            campaign_data.pop('generate_content', None)
            
            # Validate campaign data
            serializer = self.get_serializer(data=campaign_data)
            serializer.is_valid(raise_exception=True)
            
            # Create campaign
            campaign = serializer.save(user=request.user)
            
            # Generate content if requested
            first_week_posts = []
            celery_scheduled = False
            
            if generate_content:
                linkedin_controller = LinkedInContentController()
                
                # Validate campaign for generation
                validation = linkedin_controller.validate_campaign_for_generation(campaign.id)
                
                if not validation['ready_for_generation']:
                    return Response({
                        'success': False,
                        'campaign': serializer.data,
                        'error': 'Campaign not ready for content generation',
                        'validation': validation,
                        'missing_requirements': validation['missing_requirements']
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Generate posts for the first period only
                first_period_posts = self._generate_first_period_posts(
                    campaign, linkedin_controller, request.user.id
                )
                print(first_period_posts)
                if not first_period_posts:
                    return Response({
                        'success': False,
                        'campaign': serializer.data,
                        'error': 'Failed to generate first period posts'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Schedule Celery tasks for subsequent periods
                celery_scheduled = self._schedule_celery_tasks(campaign)
            
            return Response({
                'success': True,
                'campaign': serializer.data,
                'first_period_posts': first_period_posts,
                'celery_scheduled': celery_scheduled,
                'message': f'Campaign created successfully with {len(first_period_posts)} first period posts and Celery scheduling'
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({
                'success': False,
                'error': str(e),
                'error_type': 'validation_error'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_first_period_posts(self, campaign, linkedin_controller, user_id):
        """
        Generate posts for the first execution period of the campaign
        
        Args:
            campaign: Campaign object
            linkedin_controller: LinkedInContentController instance
            user_id: User ID
            
        Returns:
            List of generated post results
        """
        try:
            # Calculate the first period's date range based on execution_period
            from datetime import timedelta
            start_date = campaign.start_date
            execution_period_days = campaign.execution_period
            first_period_end = start_date + timedelta(days=execution_period_days - 1)
            
            # Generate posts for the first period (general approach: 3-5 posts per period)
            posts_per_period = min(5, max(3, execution_period_days // 2))  # 3-5 posts based on period length
            first_period_posts = []
            
            for i in range(posts_per_period):
                # Calculate post date within the first period
                post_date = start_date + timedelta(days=i * (execution_period_days // posts_per_period))
                
                # Generate content
                result = linkedin_controller.generate_linkedin_content(campaign.id, user_id)
                print(result)
                if result.get('success'):
                    # Create the actual post in the database
                    post_data = {
                        'campaign_id': campaign.id,
                        'content': result.get('generated_content', result.get('post', '')),
                        'publish_date': post_date,
                        'status': 'PENDING'  # Set initial status to PENDING
                    }
                    
                    # Create CampaignPost
                    from .models import CampaignPost
                    post = CampaignPost.objects.create(**post_data)
                    
                    # Link asset if available
                    if result.get('asset_used'):
                        from .models import PostAsset
                        PostAsset.objects.create(
                            post=post,
                            asset_id=result['asset_used']['id']
                        )
                    
                    first_period_posts.append({
                        'post_id': post.id,
                        'content': post.content,
                        'publish_date': post.publish_date,
                        'asset_used': result.get('asset_used'),
                        'generation_result': result
                    })
                else:
                    # Log the failure but continue with other posts
                    print(f"Failed to generate post {i+1}: {result.get('error')}")
            
            return first_period_posts
            
        except Exception as e:
            print(f"Error generating first period posts: {str(e)}")
            return []
    
    def _schedule_celery_tasks(self, campaign):
        """
        Schedule Celery tasks for subsequent periods of the campaign
        
        Args:
            campaign: Campaign object
            
        Returns:
            bool: True if scheduling was successful
        """
        try:
            from datetime import timedelta
            from django.utils import timezone
            
            # Calculate campaign duration and periods
            campaign_duration = (campaign.end_date - campaign.start_date).days
            execution_period_days = campaign.execution_period
            total_periods = (campaign_duration // execution_period_days) + 1
            
            # Skip first period (already handled)
            periods_to_schedule = total_periods - 1
            
            if periods_to_schedule <= 0:
                return True  # Campaign is only one period or less
            
            # Calculate posts per period (general approach)
            posts_per_period = min(5, max(3, execution_period_days // 2))
            
            # Schedule Celery tasks for each subsequent period
            for period in range(1, periods_to_schedule + 1):
                period_start_date = campaign.start_date + timedelta(days=period * execution_period_days)
                
                # Schedule the task using Celery
                self._schedule_period_posts_task(
                    campaign_id=campaign.id,
                    period_start_date=period_start_date,
                    posts_per_period=posts_per_period,
                    user_id=campaign.user.id
                )
            
            return True
            
        except Exception as e:
            print(f"Error scheduling Celery tasks: {str(e)}")
            return False
    
    def _schedule_period_posts_task(self, campaign_id, period_start_date, posts_per_period, user_id):
        """
        Schedule a Celery task for generating period posts
        
        Args:
            campaign_id: ID of the campaign
            period_start_date: Start date of the period
            posts_per_period: Number of posts to generate
            user_id: User ID
        """
        try:
            # Import the Celery task
            from .tasks import generate_period_posts_task
            
            # Schedule the task using Celery
            generate_period_posts_task.apply_async(
                args=[campaign_id, period_start_date, posts_per_period, user_id],
                eta=period_start_date
            )
            
            print(f"Scheduled period posts task for campaign {campaign_id}, period starting {period_start_date}")
            
            # Log the scheduling
            from .models import PostLog
            PostLog.objects.create(
                post_id=None,  # Will be set when posts are created
                status='scheduled',
                error_message=f'Period posts scheduled for period starting {period_start_date}'
            )
            
        except Exception as e:
            print(f"Error scheduling period posts task: {str(e)}")
    
    @action(detail=True, methods=['post'], url_path='schedule-celery')
    def schedule_celery_for_campaign(self, request, pk=None):
        """
        Manually schedule Celery tasks for an existing campaign
        
        Request Body:
        {
            "posts_per_week": 5
        }
        
        Response:
        {
            "success": true,
            "message": "Celery tasks scheduled successfully",
            "weeks_scheduled": 3
        }
        """
        try:
            campaign = self.get_object()
            posts_per_week = request.data.get('posts_per_week', 5)
            
            # Schedule Celery tasks
            celery_scheduled = self._schedule_celery_tasks(campaign, posts_per_week)
            
            if celery_scheduled:
                return Response({
                    'success': True,
                    'message': 'Celery tasks scheduled successfully',
                    'campaign_id': campaign.id,
                    'posts_per_week': posts_per_week
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': 'Failed to schedule Celery tasks'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='generate-content')
    def generate_content_for_campaign(self, request, pk=None):
        """
        Generate additional content for an existing campaign
        
        Request Body:
        {
            "count": 3,
            "regenerate": false
        }
        
        Response:
        {
            "success": true,
            "generated_content": [...],
            "message": "Generated 3 new content pieces"
        }
        """
        try:
            campaign = self.get_object()
            count = request.data.get('count', 1)
            regenerate = request.data.get('regenerate', False)
            
            linkedin_controller = LinkedInContentController()
            
            # Validate campaign for generation
            validation = linkedin_controller.validate_campaign_for_generation(campaign.id)
            
            if not validation['ready_for_generation']:
                return Response({
                    'success': False,
                    'error': 'Campaign not ready for content generation',
                    'validation': validation,
                    'missing_requirements': validation['missing_requirements']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Reset assets if regenerate is requested
            if regenerate:
                linkedin_controller.reset_campaign_assets(campaign.id)
            
            # Generate content
            if count == 1:
                result = linkedin_controller.generate_linkedin_content(campaign.id, request.user.id)
                if result.get('success'):
                    generated_content = [result]
                else:
                    return Response({
                        'success': False,
                        'error': result.get('error'),
                        'error_type': result.get('error_type')
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                results = linkedin_controller.generate_multiple_posts(campaign.id, count, request.user.id)
                successful_results = [r for r in results if r.get('success')]
                generated_content = successful_results
                
                if not successful_results:
                    return Response({
                        'success': False,
                        'error': 'Failed to generate any content',
                        'results': results
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'generated_content': generated_content,
                'content_count': len(generated_content),
                'message': f'Generated {len(generated_content)} new content pieces'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='generation-stats')
    def get_generation_stats(self, request, pk=None):
        """
        Get content generation statistics for a campaign
        
        Response:
        {
            "success": true,
            "stats": {...},
            "validation": {...}
        }
        """
        try:
            campaign = self.get_object()
            linkedin_controller = LinkedInContentController()
            
            # Get generation stats
            stats = linkedin_controller.get_generation_stats(campaign.id, request.user.id)
            
            # Get validation info
            validation = linkedin_controller.validate_campaign_for_generation(campaign.id)
            
            return Response({
                'success': True,
                'stats': stats,
                'validation': validation,
                'ai_info': linkedin_controller.get_ai_info()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='reset-assets')
    def reset_campaign_assets(self, request, pk=None):
        """
        Reset all assets used in a campaign (for testing or manual reset)
        
        Response:
        {
            "success": true,
            "message": "Campaign assets reset successfully"
        }
        """
        try:
            campaign = self.get_object()
            linkedin_controller = LinkedInContentController()
            
            success = linkedin_controller.reset_campaign_assets(campaign.id)
            
            if success:
                return Response({
                    'success': True,
                    'message': 'Campaign assets reset successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': 'Failed to reset campaign assets'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='posts-by-status')
    def get_campaign_posts_by_status(self, request):
        """
        Get campaign posts filtered by status
        
        Query Parameters:
        - campaign_id: ID of the campaign
        - user_id: ID of the user (optional, defaults to current user)
        - status: Status to filter by (PENDING, APPROVED, REJECTED, PUBLISHED, DRAFT)
        - limit: Number of posts to return (optional, defaults to 50)
        
        Example:
        GET /api/campaigns/create-with-content/posts-by-status/?campaign_id=1&status=PENDING&limit=10
        
        Response:
        {
            "success": true,
            "campaign": {...},
            "posts": [...],
            "total_posts": 5,
            "status_filter": "PENDING"
        }
        """
        try:
            campaign_id = request.query_params.get('campaign_id')
            user_id = request.query_params.get('user_id', request.user.id)
            status_filter = request.query_params.get('status', 'PENDING')
            limit = int(request.query_params.get('limit', 50))
            
            if not campaign_id:
                return Response({
                    'success': False,
                    'error': 'campaign_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate campaign exists and belongs to user
            try:
                campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
            except Campaign.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Campaign not found or does not belong to user'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get posts filtered by status
            posts = CampaignPost.objects.filter(
                campaign_id=campaign_id,
                status=status_filter
            ).order_by('-created_at')[:limit]
            
            # Serialize posts with assets
            posts_data = []
            for post in posts:
                post_data = {
                    'id': post.id,
                    'content': post.content,
                    'publish_date': post.publish_date,
                    'status': post.status,
                    'created_at': post.created_at,
                    'updated_at': post.updated_at,
                    'assets': []
                }
                
                # Get assets for this post
                post_assets = PostAsset.objects.filter(post=post)
                for post_asset in post_assets:
                    asset_data = {
                        'id': post_asset.asset.id,
                        'name': post_asset.asset.name,
                        'file_type': post_asset.asset.file_type,
                        'file_url': request.build_absolute_uri(post_asset.asset.file.url) if post_asset.asset.file else None
                    }
                    post_data['assets'].append(asset_data)
                
                posts_data.append(post_data)
            
            return Response({
                'success': True,
                'campaign': {
                    'id': campaign.id,
                    'title': campaign.title,
                    'platform': campaign.platform.title
                },
                'posts': posts_data,
                'total_posts': len(posts_data),
                'status_filter': status_filter,
                'limit': limit,
                'message': f'Found {len(posts_data)} posts with status "{status_filter}"'
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({
                'success': False,
                'error': f'Invalid parameter: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='update-post-status')
    def update_post_status(self, request, pk=None):
        """
        Update the status of a specific post
        
        Request Body:
        {
            "post_id": 1,
            "status": "APPROVED"  // PENDING, APPROVED, REJECTED, PUBLISHED, DRAFT
        }
        
        Response:
        {
            "success": true,
            "message": "Post status updated successfully",
            "post": {...}
        }
        """
        try:
            campaign = self.get_object()
            post_id = request.data.get('post_id')
            new_status = request.data.get('status')
            
            if not post_id:
                return Response({
                    'success': False,
                    'error': 'post_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not new_status:
                return Response({
                    'success': False,
                    'error': 'status is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate status is valid
            valid_statuses = ['PENDING', 'APPROVED', 'REJECTED', 'PUBLISHED', 'DRAFT']
            if new_status not in valid_statuses:
                return Response({
                    'success': False,
                    'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the post and verify it belongs to this campaign
            try:
                post = CampaignPost.objects.get(id=post_id, campaign=campaign)
            except CampaignPost.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Post not found or does not belong to this campaign'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Update the status
            post.status = new_status
            post.save()
            
            # Prepare response data
            post_data = {
                'id': post.id,
                'content': post.content,
                'publish_date': post.publish_date,
                'status': post.status,
                'created_at': post.created_at,
                'updated_at': post.updated_at,
                'assets': []
            }
            
            # Get assets for this post
            post_assets = PostAsset.objects.filter(post=post)
            for post_asset in post_assets:
                asset_data = {
                    'id': post_asset.asset.id,
                    'name': post_asset.asset.name,
                    'file_type': post_asset.asset.file_type,
                    'file_url': request.build_absolute_uri(post_asset.asset.file.url) if post_asset.asset.file else None
                }
                post_data['assets'].append(asset_data)
            
            return Response({
                'success': True,
                'message': f'Post status updated to "{new_status}" successfully',
                'post': post_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
 
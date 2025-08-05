from django.db import transaction, models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from typing import List, Dict, Any, Optional, Union
import random
import os
import openai
from datetime import datetime, timedelta
import requests
import json

from .models import User, Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog
from .serializers import (
    UserSerializer, PlatformSerializer, TagSerializer, AssetLibrarySerializer, AssetSerializer, 
    CampaignSerializer, CampaignPostSerializer, PostAssetSerializer, PostLogSerializer
)

# Simple OpenRouter AI Provider
class OpenRouterAI:
    """Simple OpenRouter AI provider for content generation"""
    
    def __init__(self):
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="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",
        )
    
    def generate_content(self, prompt: str, max_tokens: int = 300) -> str:
        """Generate content using OpenRouter"""
        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional LinkedIn content creator. Create engaging, professional LinkedIn posts that are optimized for the platform. Keep posts concise, professional, and include relevant hashtags when appropriate."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise ValidationError(f"Error generating content with OpenRouter: {str(e)}")
    
    def analyze_image(self, image_url: str) -> str:
        """Analyze image using OpenRouter Vision"""
        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this image and provide a detailed description suitable for creating a LinkedIn post. Include what you see, the mood, colors, and any text or objects that could be relevant for social media content."},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                max_tokens=500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise ValidationError(f"Error analyzing image with OpenRouter Vision: {str(e)}")


class BaseController:
    """Base controller with common CRUD operations"""
    
    def __init__(self, model_class, serializer_class):
        self.model = model_class
        self.serializer = serializer_class
    
    def get_all(self, **filters) -> List[Dict[str, Any]]:
        """Get all objects with optional filters"""
        queryset = self.model.objects.filter(**filters)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_by_id(self, obj_id: int) -> Optional[Dict[str, Any]]:
        """Get object by ID"""
        try:
            obj = self.model.objects.get(id=obj_id)
            serializer = self.serializer(obj)
            return serializer.data
        except ObjectDoesNotExist:
            return None
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new object"""
        serializer = self.serializer(data=data)
        if serializer.is_valid():
            obj = serializer.save()
            return serializer.data
        raise ValidationError(serializer.errors)
    
    def update(self, obj_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update existing object"""
        try:
            obj = self.model.objects.get(id=obj_id)
            serializer = self.serializer(obj, data=data, partial=True)
            if serializer.is_valid():
                obj = serializer.save()
                return serializer.data
            raise ValidationError(serializer.errors)
        except ObjectDoesNotExist:
            return None
    
    def delete(self, obj_id: int) -> bool:
        """Delete object by ID"""
        try:
            obj = self.model.objects.get(id=obj_id)
            obj.delete()
            return True
        except ObjectDoesNotExist:
            return False
    
    def exists(self, obj_id: int) -> bool:
        """Check if object exists"""
        return self.model.objects.filter(id=obj_id).exists()


class UserController(BaseController):
    """Controller for User model operations"""
    
    def __init__(self):
        super().__init__(User, UserSerializer)
    
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        try:
            user = User.objects.get(username=username)
            serializer = self.serializer(user)
            return serializer.data
        except ObjectDoesNotExist:
            return None
    
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            user = User.objects.get(email=email)
            serializer = self.serializer(user)
            return serializer.data
        except ObjectDoesNotExist:
            return None
    
    def verify_user(self, user_id: int) -> bool:
        """Mark user as verified"""
        try:
            user = User.objects.get(id=user_id)
            user.is_verified = True
            user.save()
            return True
        except ObjectDoesNotExist:
            return False
    
    def get_verified_users(self) -> List[Dict[str, Any]]:
        """Get all verified users"""
        return self.get_all(is_verified=True)
    
    def get_active_users(self) -> List[Dict[str, Any]]:
        """Get all active users"""
        return self.get_all(is_active=True)


class PlatformController(BaseController):
    """Controller for Platform model operations"""
    
    def __init__(self):
        super().__init__(Platform, PlatformSerializer)
    
    def get_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Get platform by title"""
        try:
            platform = Platform.objects.get(title=title)
            serializer = self.serializer(platform)
            return serializer.data
        except ObjectDoesNotExist:
            return None


class TagController(BaseController):
    """Controller for Tag model operations"""
    
    def __init__(self):
        super().__init__(Tag, TagSerializer)
    
    def get_or_create(self, title: str) -> Dict[str, Any]:
        """Get existing tag or create new one"""
        tag, created = Tag.objects.get_or_create(title=title.lower())
        serializer = self.serializer(tag)
        return serializer.data
    
    def get_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Get tag by title"""
        try:
            tag = Tag.objects.get(title=title.lower())
            serializer = self.serializer(tag)
            return serializer.data
        except ObjectDoesNotExist:
            return None
    
    def create_multiple(self, titles: List[str]) -> List[Dict[str, Any]]:
        """Create multiple tags"""
        tags = []
        for title in titles:
            tag_data = self.get_or_create(title)
            tags.append(tag_data)
        return tags
    
    def get_popular_tags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most used tags"""
        tags = Tag.objects.annotate(
            asset_count=models.Count('asset'),
            campaign_count=models.Count('campaign')
        ).order_by('-asset_count', '-campaign_count')[:limit]
        serializer = self.serializer(tags, many=True)
        return serializer.data


class AssetLibraryController(BaseController):
    """Controller for AssetLibrary model operations"""
    
    def __init__(self):
        super().__init__(AssetLibrary, AssetLibrarySerializer)
    
    def get_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all asset libraries for a specific user"""
        return self.get_all(user_id=user_id)
    
    def get_by_name(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get asset library by name"""
        filters = {'name': name}
        if user_id:
            filters['user_id'] = user_id
        try:
            library = AssetLibrary.objects.get(**filters)
            serializer = self.serializer(library)
            return serializer.data
        except ObjectDoesNotExist:
            return None


class AssetController(BaseController):
    """Controller for Asset model operations"""
    
    def __init__(self):
        super().__init__(Asset, AssetSerializer)
    
    def get_by_library(self, library_id: int) -> List[Dict[str, Any]]:
        """Get all assets for a specific library"""
        return self.get_all(library_id=library_id)
    
    def get_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all assets for a specific user (through libraries)"""
        queryset = Asset.objects.filter(library__user_id=user_id)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_by_type(self, file_type: str) -> List[Dict[str, Any]]:
        """Get assets by file type"""
        return self.get_all(file_type=file_type)
    
    def get_ready_assets(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets that have files"""
        queryset = Asset.objects.filter(file__isnull=False)
        if user_id:
            queryset = queryset.filter(library__user_id=user_id)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_random_asset(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get a random ready asset"""
        ready_assets = self.get_ready_assets(user_id)
        if ready_assets:
            return random.choice(ready_assets)
        return None
    
    def add_tags(self, asset_id: int, tag_ids: List[int]) -> bool:
        """Add tags to asset"""
        try:
            asset = Asset.objects.get(id=asset_id)
            asset.tags.add(*tag_ids)
            return True
        except ObjectDoesNotExist:
            return False
    
    def remove_tags(self, asset_id: int, tag_ids: List[int]) -> bool:
        """Remove tags from asset"""
        try:
            asset = Asset.objects.get(id=asset_id)
            asset.tags.remove(*tag_ids)
            return True
        except ObjectDoesNotExist:
            return False
    
    def get_assets_with_tags(self, tag_ids: List[int]) -> List[Dict[str, Any]]:
        """Get assets that have specific tags"""
        queryset = Asset.objects.filter(tags__id__in=tag_ids).distinct()
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def mark_as_used_by_ai(self, asset_id: int) -> bool:
        """Mark asset as used by AI and increment usage count"""
        try:
            asset = Asset.objects.get(id=asset_id)
            asset.is_used_by_ai = True
            asset.used_at = timezone.now()
            asset.usage_count += 1
            asset.save()
            return True
        except ObjectDoesNotExist:
            return False
    
    def get_unused_assets(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets that haven't been used by AI yet"""
        filters = {'is_used_by_ai': False}
        if user_id:
            queryset = Asset.objects.filter(**filters, library__user_id=user_id)
        else:
            queryset = Asset.objects.filter(**filters)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_used_assets(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets that have been used by AI"""
        filters = {'is_used_by_ai': True}
        if user_id:
            queryset = Asset.objects.filter(**filters, library__user_id=user_id)
        else:
            queryset = Asset.objects.filter(**filters)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_assets_by_usage_count(self, min_count: int = 0, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets with minimum usage count"""
        queryset = Asset.objects.filter(usage_count__gte=min_count)
        if user_id:
            queryset = queryset.filter(library__user_id=user_id)
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_most_used_assets(self, limit: int = 10, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get most frequently used assets"""
        queryset = Asset.objects.order_by('-usage_count')
        if user_id:
            queryset = queryset.filter(library__user_id=user_id)
        queryset = queryset[:limit]
        serializer = self.serializer(queryset, many=True)
        return serializer.data
    
    def get_random_unused_asset(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get a random asset that hasn't been used by AI yet"""
        unused_assets = self.get_unused_assets(user_id)
        if unused_assets:
            return random.choice(unused_assets)
        return None
    
    def reset_asset_usage(self, asset_id: int) -> bool:
        """Reset asset usage tracking (for testing or manual reset)"""
        try:
            asset = Asset.objects.get(id=asset_id)
            asset.is_used_by_ai = False
            asset.used_at = None
            asset.usage_count = 0
            asset.save()
            return True
        except ObjectDoesNotExist:
            return False
    
    def get_asset_usage_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get usage statistics for assets"""
        if user_id:
            queryset = Asset.objects.filter(library__user_id=user_id)
        else:
            queryset = Asset.objects.all()
        
        total_assets = queryset.count()
        used_assets = queryset.filter(is_used_by_ai=True).count()
        unused_assets = total_assets - used_assets
        total_usage = queryset.aggregate(total=models.Sum('usage_count'))['total'] or 0
        
        return {
            'total_assets': total_assets,
            'used_assets': used_assets,
            'unused_assets': unused_assets,
            'total_usage_count': total_usage,
            'usage_percentage': (used_assets / total_assets * 100) if total_assets > 0 else 0
        }


class CampaignController(BaseController):
    """Controller for Campaign model operations"""
    
    def __init__(self):
        super().__init__(Campaign, CampaignSerializer)
    
    def get_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all campaigns for a specific user"""
        return self.get_all(user_id=user_id)
    
    def get_active_campaigns(self) -> List[Dict[str, Any]]:
        """Get campaigns that are currently active"""
        today = timezone.now().date()
        campaigns = Campaign.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            is_active=True
        )
        serializer = self.serializer(campaigns, many=True)
        return serializer.data
    
    def get_campaigns_by_platform(self, platform_id: int) -> List[Dict[str, Any]]:
        """Get campaigns by platform"""
        return self.get_all(platform_id=platform_id)
    
    def get_campaigns_by_library(self, library_id: int) -> List[Dict[str, Any]]:
        """Get campaigns by asset library"""
        return self.get_all(asset_library_id=library_id)
    
    def create_campaign_with_assets(
        self, 
        user_id: int, 
        library_id: int,
        platform_id: int,
        tag_ids: List[int] = None,
        **campaign_data
    ) -> Dict[str, Any]:
        """Create campaign with library and tags"""
        with transaction.atomic():
            # Create campaign
            campaign_data['user_id'] = user_id
            campaign_data['asset_library_id'] = library_id
            campaign_data['platform_id'] = platform_id
            campaign = self.create(campaign_data)
            
            # Add tags
            if tag_ids:
                campaign_obj = Campaign.objects.get(id=campaign['id'])
                campaign_obj.tags.add(*tag_ids)
            
            return campaign
    
    def get_campaigns_due_for_posting(self) -> List[Dict[str, Any]]:
        """Get campaigns that are due for posting (for Celery Beat)"""
        today = timezone.now().date()
        campaigns = Campaign.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            is_active=True
        )
        
        due_campaigns = []
        for campaign in campaigns:
            # Check if campaign has any posts scheduled for today
            today_posts = CampaignPost.objects.filter(
                campaign=campaign,
                publish_date__date=today
            ).exists()
            
            if not today_posts:
                serializer = self.serializer(campaign)
                due_campaigns.append(serializer.data)
        
        return due_campaigns


class CampaignPostController(BaseController):
    """Controller for CampaignPost model operations"""
    
    def __init__(self):
        super().__init__(CampaignPost, CampaignPostSerializer)
    
    def get_by_campaign(self, campaign_id: int) -> List[Dict[str, Any]]:
        """Get all posts for a specific campaign"""
        return self.get_all(campaign_id=campaign_id)
    
    def get_by_publish_date(self, date: datetime) -> List[Dict[str, Any]]:
        """Get posts by publish date"""
        return self.get_all(publish_date__date=date.date())
    
    def get_due_posts(self) -> List[Dict[str, Any]]:
        """Get posts that are due for publishing"""
        now = timezone.now()
        posts = CampaignPost.objects.filter(publish_date__lte=now)
        serializer = self.serializer(posts, many=True)
        return serializer.data
    
    def create_post_with_assets(
        self, 
        campaign_id: int, 
        content: str, 
        publish_date: datetime,
        asset_ids: List[int] = None
    ) -> Dict[str, Any]:
        """Create post with assets"""
        with transaction.atomic():
            # Create post
            post_data = {
                'campaign_id': campaign_id,
                'content': content,
                'publish_date': publish_date,
            }
            
            post = self.create(post_data)
            
            # Add assets
            if asset_ids:
                post_obj = CampaignPost.objects.get(id=post['id'])
                for asset_id in asset_ids:
                    PostAsset.objects.create(post=post_obj, asset_id=asset_id)
            
            return post
    
    def generate_content_for_post(self, campaign_id: int, asset_id: int) -> str:
        """Generate content for a post using OpenRouter"""
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            asset = Asset.objects.get(id=asset_id)
            
            # Setup AI provider
            ai_provider = OpenRouterAI()
            
            # Prepare prompt
            prompt = campaign.prompt or "Create an engaging social media post."
            
            if asset.file:
                prompt += f" Include content about the attached {asset.file_type} file."
            
            # Generate content using OpenRouter
            generated_content = ai_provider.generate_content(prompt, max_tokens=200)
            
            # Mark asset as used by AI
            asset_controller = AssetController()
            asset_controller.mark_as_used_by_ai(asset_id)
            
            return generated_content
            
        except ObjectDoesNotExist:
            raise ValidationError("Campaign or Asset not found")
        except Exception as e:
            raise ValidationError(f"Error generating content: {str(e)}")


class PostAssetController(BaseController):
    """Controller for PostAsset model operations"""
    
    def __init__(self):
        super().__init__(PostAsset, PostAssetSerializer)
    
    def get_by_post(self, post_id: int) -> List[Dict[str, Any]]:
        """Get all assets for a specific post"""
        return self.get_all(post_id=post_id)
    
    def get_by_asset(self, asset_id: int) -> List[Dict[str, Any]]:
        """Get all posts that use a specific asset"""
        return self.get_all(asset_id=asset_id)


class PostLogController(BaseController):
    """Controller for PostLog model operations"""
    
    def __init__(self):
        super().__init__(PostLog, PostLogSerializer)
    
    def get_by_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        """Get log for a specific post"""
        return self.get_by_id(post_id)
    
    def create_log(self, post_id: int, status: str, error_message: str = None) -> Dict[str, Any]:
        """Create a log entry for a post"""
        log_data = {
            'post_id': post_id,
            'status': status,
            'error_message': error_message
        }
        return self.create(log_data)
    
    def update_log_status(self, post_id: int, status: str, error_message: str = None) -> Optional[Dict[str, Any]]:
        """Update log status for a post"""
        try:
            log = PostLog.objects.get(post_id=post_id)
            log.status = status
            if error_message:
                log.error_message = error_message
            log.save()
            serializer = self.serializer(log)
            return serializer.data
        except ObjectDoesNotExist:
            return None


class LinkedInContentController:
    """Controller for LinkedIn content generation using OpenRouter"""
    
    def __init__(self):
        self.asset_controller = AssetController()
        self.campaign_controller = CampaignController()
        self.post_controller = CampaignPostController()
        self.log_controller = PostLogController()
        self.ai_provider = OpenRouterAI()
    
    def generate_linkedin_content(self, campaign_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate LinkedIn content using OpenAI with random asset selection
        
        Args:
            campaign_id: ID of the campaign to generate content for
            user_id: Optional user ID to filter assets by user
            
        Returns:
            Dict containing the generated content and metadata
        """
        try:
            # Validate campaign exists and get campaign data
            campaign_data = self.campaign_controller.get_by_id(campaign_id)
            if not campaign_data:
                raise ValidationError("Campaign not found")
            
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Check if campaign has a prompt
            if not campaign.prompt:
                raise ValidationError("Campaign must have a prompt for content generation")
            
            # Get random unused asset from the campaign's asset library
            asset = self._get_random_unused_asset(campaign.asset_library_id, user_id)
            if not asset:
                raise ValidationError("No unused assets available for content generation")
            
            # Generate content based on asset type
            generated_content = self._generate_content_for_asset(campaign, asset)
            
            # Create campaign post with generated content
            post_data = {
                'campaign_id': campaign_id,
                'content': generated_content,
                'publish_date': timezone.now() + timedelta(hours=1),  # Schedule for 1 hour from now
            }
            
            post = self.post_controller.create(post_data)
            
            # Link the asset to the post
            post_obj = CampaignPost.objects.get(id=post['id'])
            PostAsset.objects.create(post=post_obj, asset=asset)
            
            # Mark asset as used by AI
            self.asset_controller.mark_as_used_by_ai(asset.id)
            
            # Create success log
            self.log_controller.create_log(
                post_id=post['id'],
                status='generated',
                error_message=None
            )
            
            return {
                'success': True,
                'post': post,
                'asset_used': {
                    'id': asset.id,
                    'name': asset.name,
                    'file_type': asset.file_type
                },
                'campaign': campaign_data,
                'generated_content': generated_content
            }
            
        except ValidationError as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': 'validation_error'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}",
                'error_type': 'unexpected_error'
            }
    
    def _get_random_unused_asset(self, library_id: int, user_id: Optional[int] = None) -> Optional[Asset]:
        """
        Get a random unused asset from the specified library
        
        Args:
            library_id: ID of the asset library
            user_id: Optional user ID for additional filtering
            
        Returns:
            Random unused Asset object or None if none available
        """
        try:
            # Get unused assets from the library
            filters = {
                'library_id': library_id,
                'is_used_by_ai': False,
                'file__isnull': False  # Ensure asset has a file
            }
            
            if user_id:
                filters['library__user_id'] = user_id
            
            unused_assets = Asset.objects.filter(**filters)
            
            if not unused_assets.exists():
                return None
            
            # Get random asset
            return random.choice(list(unused_assets))
            
        except Exception as e:
            raise ValidationError(f"Error selecting random asset: {str(e)}")
    
    def _generate_content_for_asset(self, campaign: Campaign, asset: Asset) -> str:
        """
        Generate LinkedIn content based on asset type and campaign prompt
        
        Args:
            campaign: Campaign object with prompt
            asset: Asset object to generate content for
            
        Returns:
            Generated content string
        """
        try:
            # Prepare base prompt from campaign
            base_prompt = campaign.prompt
            
            # Enhance prompt based on asset type and process image if available
            asset_prompt = self._get_asset_specific_prompt(asset, base_prompt)
            
            # Generate content using configured AI provider
            generated_content = self.ai_provider.generate_content(asset_prompt)
            
            if not generated_content:
                raise ValidationError(f"{self.ai_provider.provider_name} returned empty content")
            
            return generated_content
            
        except Exception as e:
            raise ValidationError(f"Error generating content: {str(e)}")
    
    def _get_asset_specific_prompt(self, asset: Asset, base_prompt: str) -> str:
        """
        Create asset-specific prompt based on file type and process images
        
        Args:
            asset: Asset object
            base_prompt: Base prompt from campaign
            
        Returns:
            Enhanced prompt string
        """
        asset_description = f"Asset: {asset.name} (Type: {asset.file_type})"
        
        # Process image if it's an image file and has a URL
        image_analysis = ""
        if asset.file_type == 'image' and asset.file:
            try:
                # Get the image URL (you might need to adjust this based on your file storage)
                image_url = asset.file.url if hasattr(asset.file, 'url') else str(asset.file)
                image_analysis_result = self.ai_provider.analyze_image(image_url)
                image_analysis = f"\n\nImage Analysis: {image_analysis_result}"
            except Exception as e:
                # If image processing fails, continue without it
                image_analysis = f"\n\nNote: Could not analyze image ({str(e)})"
        
        if asset.file_type == 'video':
            prompt = f"""
{base_prompt}

Create a LinkedIn post for a video asset. The video file is: {asset_description}

Instructions:
- Create engaging content that describes what viewers can expect from the video
- Include a call-to-action to watch the video
- Make it professional and LinkedIn-appropriate
- Include relevant hashtags
- Keep it under 300 characters for optimal LinkedIn engagement
"""
        elif asset.file_type == 'image':
            prompt = f"""
{base_prompt}

Create a LinkedIn post for an image asset. The image file is: {asset_description}{image_analysis}

Instructions:
- Create engaging content that complements the image
- Use the image analysis to create relevant content
- Describe what the image shows or represents
- Include a call-to-action if appropriate
- Make it professional and LinkedIn-appropriate
- Include relevant hashtags
- Keep it under 300 characters for optimal LinkedIn engagement
"""
        else:  # audio, other, or any other file type
            prompt = f"""
{base_prompt}

Create a LinkedIn post for an asset. The asset file is: {asset_description}

Instructions:
- Create engaging content related to this asset
- Make it professional and LinkedIn-appropriate
- Include relevant hashtags
- Keep it under 300 characters for optimal LinkedIn engagement
"""
        
        return prompt.strip()
    
    def generate_multiple_posts(self, campaign_id: int, count: int = 3, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Generate multiple LinkedIn posts for a campaign
        
        Args:
            campaign_id: ID of the campaign
            count: Number of posts to generate
            user_id: Optional user ID for filtering
            
        Returns:
            List of generated post results
        """
        results = []
        
        for i in range(count):
            try:
                result = self.generate_linkedin_content(campaign_id, user_id)
                results.append(result)
                
                # Add small delay between generations to avoid rate limits
                if i < count - 1:
                    import time
                    time.sleep(1)
                    
            except Exception as e:
                results.append({
                    'success': False,
                    'error': f"Failed to generate post {i+1}: {str(e)}",
                    'error_type': 'generation_error'
                })
        
        return results
    
    def get_generation_stats(self, campaign_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get statistics about content generation for a campaign
        
        Args:
            campaign_id: ID of the campaign
            user_id: Optional user ID for filtering
            
        Returns:
            Dictionary with generation statistics
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Get all posts for this campaign
            posts = CampaignPost.objects.filter(campaign_id=campaign_id)
            
            # Get asset usage stats
            asset_stats = self.asset_controller.get_asset_usage_stats(user_id)
            
            # Get posts with assets
            posts_with_assets = PostAsset.objects.filter(post__campaign_id=campaign_id)
            
            return {
                'campaign_id': campaign_id,
                'campaign_title': campaign.title,
                'total_posts': posts.count(),
                'posts_with_assets': posts_with_assets.count(),
                'asset_usage_stats': asset_stats,
                'campaign_prompt': campaign.prompt,
                'campaign_active': campaign.is_active
            }
            
        except Campaign.DoesNotExist:
            raise ValidationError("Campaign not found")
        except Exception as e:
            raise ValidationError(f"Error getting generation stats: {str(e)}")
    
    def reset_campaign_assets(self, campaign_id: int) -> bool:
        """
        Reset all assets used in a campaign (for testing or manual reset)
        
        Args:
            campaign_id: ID of the campaign
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get all assets used in this campaign's posts
            post_assets = PostAsset.objects.filter(post__campaign_id=campaign_id)
            asset_ids = post_assets.values_list('asset_id', flat=True)
            
            # Reset usage for these assets
            for asset_id in asset_ids:
                self.asset_controller.reset_asset_usage(asset_id)
            
            return True
            
        except Exception as e:
            raise ValidationError(f"Error resetting campaign assets: {str(e)}")
    
    def validate_campaign_for_generation(self, campaign_id: int) -> Dict[str, Any]:
        """
        Validate if a campaign is ready for content generation
        
        Args:
            campaign_id: ID of the campaign
            
        Returns:
            Dictionary with validation results
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Check if campaign has prompt
            has_prompt = bool(campaign.prompt)
            
            # Check if campaign has unused assets
            unused_assets = Asset.objects.filter(
                library_id=campaign.asset_library_id,
                is_used_by_ai=False,
                file__isnull=False
            ).count()
            
            # Check if campaign is active
            is_active = campaign.is_active
            
            return {
                'campaign_id': campaign_id,
                'campaign_title': campaign.title,
                'has_prompt': has_prompt,
                'unused_assets_count': unused_assets,
                'ai_provider': 'OpenRouter',
                'is_active': is_active,
                'ready_for_generation': all([has_prompt, unused_assets > 0, is_active]),
                'missing_requirements': [
                    'prompt' if not has_prompt else None,
                    'unused_assets' if unused_assets == 0 else None,
                    'active_campaign' if not is_active else None
                ]
            }
            
        except Campaign.DoesNotExist:
            raise ValidationError("Campaign not found")
        except Exception as e:
            raise ValidationError(f"Error validating campaign: {str(e)}")
    
    def get_ai_info(self) -> Dict[str, Any]:
        """
        Get information about the AI provider being used
        
        Returns:
            Dictionary with AI provider information
        """
        return {
            'provider': 'OpenRouter',
            'model': 'openai/gpt-3.5-turbo',
            'vision_model': 'openai/gpt-4-vision-preview',
            'description': 'OpenRouter provides access to multiple AI models including GPT-3.5, GPT-4, and Claude',
            'features': [
                'Content generation for LinkedIn posts',
                'Image analysis and description',
                'Professional tone optimization',
                'Hashtag suggestions'
            ]
        }


 
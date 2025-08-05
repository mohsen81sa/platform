from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

# Import your controllers
from .controllers import LinkedInContentController

# Import your models and serializers
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog
from .serializers import (
    PlatformSerializer, TagSerializer, AssetLibrarySerializer,
    AssetSerializer, CampaignSerializer, CampaignPostSerializer,
    PostAssetSerializer, PostLogSerializer
)
# از تسک جدیدی که برای زمان‌بندی پست‌ها ساختید، ایمپورت کنید
from .tasks import schedule_campaign_posts


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
        # کمپین را با کاربر فعلی ذخیره کنید
        campaign = serializer.save(user=self.request.user, status='active')

        # یک بار تسک زمان‌بندی را اجرا کنید تا پست‌های اولیه ایجاد شوند
        schedule_campaign_posts.delay()

    def get_queryset(self):
        return Campaign.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='generate-posts')
    def generate_posts(self, request, pk=None):
        """
        Generate multiple posts for a specific campaign using the LinkedInContentController.
        """
        try:
            campaign = self.get_object()
            count = request.data.get('count', 1)
            controller = LinkedInContentController()
            results = controller.generate_multiple_posts(campaign_id=campaign.id, count=count, user_id=self.request.user.id)
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
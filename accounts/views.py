from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated # برای احراز هویت
from rest_framework.parsers import MultiPartParser, FormParser # برای آپلود فایل
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone # برای زمان‌بندی

# Import Celery tasks (assuming you have them set up as explained before)
# from myapp.tasks import create_post_for_campaign_task, check_campaign_schedule_task

from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog
from .serializers import (
    PlatformSerializer, TagSerializer, AssetLibrarySerializer,
    AssetSerializer, CampaignSerializer, CampaignPostSerializer,
    PostAssetSerializer, PostLogSerializer
)

# ViewSet عمومی برای مدل‌های ساده
class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated] # فقط کاربران احراز هویت شده می‌توانند دسترسی داشته باشند

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
        # کاربر را به AssetLibrary در حال ساخت اختصاص می‌دهد
        serializer.save(user=self.request.user)

    def get_queryset(self):
        # فقط کتابخانه‌های دارایی متعلق به کاربر فعلی را نشان می‌دهد
        return AssetLibrary.objects.filter(user=self.request.user)

class AssetViewSet(BaseViewSet):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    parser_classes = [MultiPartParser, FormParser] # برای مدیریت آپلود فایل

    def get_queryset(self):
        # فقط دارایی‌های متعلق به کتابخانه‌های کاربر فعلی را نشان می‌دهد
        return Asset.objects.filter(library__user=self.request.user)

class CampaignViewSet(BaseViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer

    def perform_create(self, serializer):
        # کاربر را به Campaign در حال ساخت اختصاص می‌دهد
        serializer.save(user=self.request.user)

    def get_queryset(self):
        # فقط کمپین‌های متعلق به کاربر فعلی را نشان می‌دهد
        return Campaign.objects.filter(user=self.request.user)

    # اکشن سفارشی برای "Create All Posts" از فلوچارت "Create Campaign" (اگر یکبار باشد)
    # فرض می‌کنیم که این اکشن به صورت دستی توسط کاربر یا از طریق یک trigger دیگر فراخوانی می‌شود
    @action(detail=True, methods=['post'], url_path='create-all-posts')
    def create_all_posts_for_campaign(self, request, pk=None):
        campaign = self.get_object()
        if campaign.execution_period == "One Time":
            # منطق ایجاد همه پست‌ها برای این کمپین یکبار مصرف
            # می‌توانید اینجا Celery task را فراخوانی کنید
            # create_post_for_campaign_task.delay(campaign.id) # برای هر پست
            return Response({'status': 'Posts creation initiated for one-time campaign.'}, status=status.HTTP_200_OK)
        return Response({'status': 'This campaign is not configured for "One Time" post creation.'}, status=status.HTTP_400_BAD_REQUEST)


class CampaignPostViewSet(BaseViewSet):
    queryset = CampaignPost.objects.all()
    serializer_class = CampaignPostSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assets_data = request.data.get('assets', []) # فرض می‌کنیم ID دارایی‌ها در 'assets' می‌آید

        with transaction.atomic():
            self.perform_create(serializer)
            campaign_post = serializer.instance

# اضافه کردن دارایی‌ها به PostAsset
            for asset_id in assets_data:
                try:
                    asset = Asset.objects.get(id=asset_id)
                    post_asset = PostAsset(post=campaign_post, asset=asset)
                    post_asset.full_clean() # اجرای متد clean برای اعتبارسنجی
                    post_asset.save()
                except ValidationError as e:
                    # اگر دارایی قبلاً استفاده شده باشد، ارور را برگردانید
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

        assets_data = request.data.get('assets', None) # None تا اگر فرستاده نشد، تغییر نکند

        with transaction.atomic():
            self.perform_update(serializer)
            campaign_post = serializer.instance

            if assets_data is not None:
                # حذف دارایی‌های قبلی و اضافه کردن جدیدها
                campaign_post.assets.clear()
                for asset_id in assets_data:
                    try:
                        asset = Asset.objects.get(id=asset_id)
                        post_asset = PostAsset(post=campaign_post, asset=asset)
                        post_asset.full_clean() # اجرای متد clean
                        post_asset.save()
                    except ValidationError as e:
                        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                    except Asset.DoesNotExist:
                        return Response({'detail': f'Asset with ID {asset_id} not found.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data)


# ViewSet برای PostAsset و PostLog
# اینها معمولاً توسط سیستم داخلی مدیریت می‌شوند و کمتر نیاز به دسترسی مستقیم از API دارند.
# اما برای مشاهده logها یا مدیریت دستی PostAsset می‌توانند مفید باشند.

class PostAssetViewSet(BaseViewSet):
    queryset = PostAsset.objects.all()
    serializer_class = PostAssetSerializer

    # اگر نیاز به اجرای clean() مدل هنگام save دارید، می‌توانید perform_create/update را override کنید
    def perform_create(self, serializer):
        try:
            # این فراخوانی clean() را تضمین می‌کند
            instance = serializer.save()
            instance.full_clean()
        except ValidationError as e:
            raise serializers.ValidationError({'detail': str(e.message_dict)})

class PostLogViewSet(BaseViewSet):
    queryset = PostLog.objects.all()
    serializer_class = PostLogSerializer
    http_method_names = ['get'] # فقط اجازه مشاهده (خواندن) را می‌دهد، چون توسط سیستم ایجاد می‌شود
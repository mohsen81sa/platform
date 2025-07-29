from rest_framework import serializers
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog

class PlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = 'all' # یا لیست فیلدهای مورد نظر شما: ['id', 'title']

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = 'all'

class AssetLibrarySerializer(serializers.ModelSerializer):
    # برای نمایش نام کاربر به جای ID، می‌توانید از SerializerMethodField استفاده کنید
    user_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AssetLibrary
        fields = 'all'
        read_only_fields = ['user'] # کاربر باید از request گرفته شود، نه از ورودی API

class AssetSerializer(serializers.ModelSerializer):
    # برای نمایش نام کتابخانه دارایی به جای ID
    library_name = serializers.CharField(source='library.name', read_only=True)
    # برای نمایش تگ‌ها
    tags = TagSerializer(many=True, read_only=True) # برای نمایش جزئیات تگ‌ها

    class Meta:
        model = Asset
        fields = 'all'
        # اگر فایل باید آپلود شود، اطمینان حاصل کنید که 'file' در 'fields' باشد
        # و در view مربوطه از Parser مناسب استفاده کنید (مثل MultiPartParser)

class PostAssetSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    # برای اعتبارسنجی 'clean' در مدل PostAsset:
    # ممکن است نیاز به override کردن validate متد در اینجا یا در ViewSet داشته باشید
    # تا ValidationError مدل به درستی مدیریت شود.

    class Meta:
        model = PostAsset
        fields = 'all'

class CampaignPostSerializer(serializers.ModelSerializer):
    # برای نمایش اطلاعات کمپین
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    # برای نمایش دارایی‌های مرتبط با پست
    assets = AssetSerializer(many=True, read_only=True)
    # یا اگر می‌خواهید اجازه اضافه/حذف دارایی‌ها را در زمان ایجاد/آپدیت پست بدهید،
    # باید از ManyToManyField با یک Serializer سفارشی یا SlugRelatedField استفاده کنید:
    # assets = serializers.SlugRelatedField(
    #     many=True,
    #     slug_field='id', # یا 'name' اگر یک فیلد منحصر به فرد دیگر دارید
    #     queryset=Asset.objects.all()
    # )

    class Meta:
        model = CampaignPost
        fields = 'all'

class CampaignSerializer(serializers.ModelSerializer):
    platform_title = serializers.CharField(source='platform.title', read_only=True)
    asset_library_name = serializers.CharField(source='asset_library.name', read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    # برای نمایش پست‌های مرتبط با کمپین (اختیاری)
    # posts = CampaignPostSerializer(many=True, read_only=True)

    class Meta:
        model = Campaign
        fields = 'all'
        read_only_fields = ['user']

class PostLogSerializer(serializers.ModelSerializer):
    post_id = serializers.IntegerField(source='post.id', read_only=True)
    post_content = serializers.CharField(source='post.content', read_only=True)

    class Meta:
        model = PostLog
        fields = 'all'
        read_only_fields = ['post', 'status', 'error_message'] 
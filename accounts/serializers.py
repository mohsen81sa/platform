from rest_framework import serializers
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog,User,CampaignSchedule, Notification



class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'phone_number', 'role',
            'first_name', 'last_name', 'is_verified',
            'is_active', 'is_staff', 'date_joined'
        )
        read_only_fields = ('is_verified', 'is_active', 'is_staff', 'role', 'date_joined')

class PlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = "__all__" # یا لیست فیلدهای مورد نظر شما: ['id', 'title']

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = "__all__"

class AssetLibrarySerializer(serializers.ModelSerializer):
    # برای نمایش نام کاربر به جای ID، می‌توانید از SerializerMethodField استفاده کنید
    user_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AssetLibrary
        fields = "__all__"
        read_only_fields = ['user'] # کاربر باید از request گرفته شود، نه از ورودی API

class AssetSerializer(serializers.ModelSerializer):
    # برای نمایش نام کتابخانه دارایی به جای ID
    library_name = serializers.CharField(source='library.name', read_only=True)
    # برای نمایش تگ‌ها
    tags = TagSerializer(many=True, read_only=True) # برای نمایش جزئیات تگ‌ها

    class Meta:
        model = Asset
        fields = "__all__"
        # اگر فایل باید آپلود شود، اطمینان حاصل کنید که 'file' در 'fields' باشد
        # و در view مربوطه از Parser مناسب استفاده کنید (مثل MultiPartParser)

class PostAssetSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    # برای اعتبارسنجی 'clean' در مدل PostAsset:
    # ممکن است نیاز به override کردن validate متد در اینجا یا در ViewSet داشته باشید
    # تا ValidationError مدل به درستی مدیریت شود.

    class Meta:
        model = PostAsset
        fields = "__all__"

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
        fields = "__all__"

class CampaignScheduleSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    campaign_id = serializers.IntegerField(source='campaign.id', read_only=True)

    class Meta:
        model = CampaignSchedule
        fields = [
            'id',
            'campaign_id',
            'campaign_title',
            'last_run_at',
            'next_run_at',
            'is_enabled',
        ]
        read_only_fields = ['last_run_at', 'next_run_at']

class CampaignSerializer(serializers.ModelSerializer):
    platform_title = serializers.CharField(source='platform.title', read_only=True)
    asset_library_name = serializers.CharField(source='asset_library.name', read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Campaign
        fields = [
            'id', 'user', 'title', 'start_date', 'end_date', 'execution_period', 'status',
            'session_type', 'times_per_week', 'platform', 'platform_title',
            'asset_library', 'asset_library_name', 'tags', 'prompt', 'is_active'
        ]
        read_only_fields = ['user', 'status', 'platform_title', 'asset_library_name']

    def validate(self, data):
        """
        Custom validation to ensure 'times_per_week' is provided
        if 'session_type' is 'multiple'.
        """
        if data.get('session_type') == 'multiple' and not data.get('times_per_week'):
            raise serializers.ValidationError({
                'times_per_week': 'This field is required for multiple session campaigns.'
            })
        return data

class PostLogSerializer(serializers.ModelSerializer):
    post_id = serializers.IntegerField(source='post.id', read_only=True)
    post_content = serializers.CharField(source='post.content', read_only=True)

    class Meta:
        model = PostLog
        fields = "__all__"
        read_only_fields = ['post', 'status', 'error_message'] 

class NotificationSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ['sent_at', 'email_sent', 'email_sent_at'] 
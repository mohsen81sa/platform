from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        EDITOR = "EDITOR", "Editor"
        USER = "USER", "User"

    base_role = Role.USER

    role = models.CharField(
        max_length=50, choices=Role.choices, default=base_role
    )
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['email', 'phone_number']

    def save(self, *args, **kwargs):
        if not self.pk:
            self.role = self.base_role
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} - {self.role}"
    
    
class Platform(models.Model):
    PLATFORM_CHOICES = [
        ('instagram', 'اینستاگرام'),
        ('telegram', 'تلگرام'),
        ('whatsapp', 'واتساپ'),
        ('twitter', 'توییتر'),
        ('linkedin', 'لینکدین'),
        ('facebook', 'فیسبوک'),
        ('other', 'سایر موارد'),
    ]

    name = models.CharField(max_length=20, choices=PLATFORM_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()


class Tag(models.Model):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title


class AssetLibrary(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='asset_libraries')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.user})"


class Asset(models.Model):
    FILE_TYPES = (
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('other', 'Other'),
    )

    library = models.ForeignKey(AssetLibrary, on_delete=models.CASCADE, related_name='assets')
    name = models.CharField(max_length=100)
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    file = models.FileField(upload_to='assets/')
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True)

    def __str__(self):
        return self.name


class Campaign(models.Model):
    STATUS_CHOICES = (
        ('pending', 'در انتظار'),
        ('active', 'فعال'),
        ('completed', 'تکمیل شده'),
        ('paused', 'متوقف شده'),
    )
    description = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    # فیلدهای جدید برای زمان‌بندی
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    

    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='campaigns')
    execution_period = models.CharField(max_length=100, help_text="مثل: '*/5 * * * *' برای Celery Beat")
    asset_library = models.ForeignKey(AssetLibrary, on_delete=models.CASCADE, related_name='campaigns')
    tags = models.ManyToManyField(Tag, blank=True)
    prompt = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class CampaignSchedule(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='schedule',
        verbose_name="Campaign"
    )
    # الگوی Celery Beat Crontab برای زمان‌بندی
    crontab_schedule = models.CharField(
        max_length=100,
        help_text="Format: 'minute hour day_of_week month day_of_month' (e.g., '*/15 * * * *' for every 15 minutes)",
        verbose_name="Crontab Schedule"
    )
    # تاریخ و زمان آخرین اجرای موفق
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last Run At"
    )
    # تاریخ و زمان اجرای بعدی
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Next Run At"
    )
    # فعال یا غیرفعال بودن زمان‌بندی
    is_enabled = models.BooleanField(
        default=True,
        verbose_name="Is Enabled"
    )

    def __str__(self):
        return f"Schedule for {self.campaign.title}"

    class Meta:
        verbose_name = "Campaign Schedule"
        verbose_name_plural = "Campaign Schedules"

class CampaignPost(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField()
    publish_date = models.DateTimeField()
    assets = models.ManyToManyField(Asset, through='PostAsset')

    def __str__(self):
        return f"Post for {self.campaign.title} at {self.publish_date}"


class PostAsset(models.Model):
    post = models.ForeignKey(CampaignPost, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('post', 'asset')

    def clean(self):
        # گرفتن کمپین مربوط به این پست
        campaign = self.post.campaign

        # چک کردن اینکه این asset قبلاً در پست‌های دیگه از همین کمپین استفاده شده یا نه
        used = PostAsset.objects.filter(
            post__campaign=campaign,
            asset=self.asset
        ).exclude(post=self.post).exists()

        if used:
            raise ValidationError("This asset has already been used in another post of the same campaign.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class PostLog(models.Model):
    post = models.OneToOneField(CampaignPost, on_delete=models.CASCADE, related_name='log')
    status = models.CharField(max_length=50)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Log for {self.post}"


 # Import models that this model relates to

class GeneratedContent(models.Model):
    """
    Represents the final content generated by AI, ready to be published.
    This model serves as the central piece connecting a Campaign, an original Asset,
    and a publishing log (PostLog).
    """
    # ارتباط با کمپین: مشخص می‌کند این محتوا برای کدام کمپین تولید شده است
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='generated_contents',
        verbose_name="Campaign"
    )
    
    # ارتباط با دارایی اصلی: مشخص می‌کند این محتوا از کدام دارایی (Asset) ساخته شده است
    original_asset = models.ForeignKey(
        'Asset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_contents',
        verbose_name="Original Asset"
    )

    # پلتفرم هدف: مثلاً 'linkedin', 'twitter' و غیره
    platform = models.CharField(
        max_length=50,
        verbose_name="Platform"
    )
    
    # محتوای متنی تولید شده توسط AI
    content = models.TextField(
        verbose_name="Content"
    )
    
    # فایل تصویری مرتبط با محتوا (اگر وجود داشته باشد)
    image = models.ImageField(
        upload_to='generated_content_images/',
        null=True,
        blank=True,
        verbose_name="Image"
    )
    
    # گزینه‌هایی برای وضعیت انتشار پست به پلتفرم‌های خارجی
    PUBLISH_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_publish', 'Pending Publish'),
        ('published', 'Published'),
        ('failed_publish', 'Failed Publish'),
    ]
    publish_status = models.CharField(
        max_length=20,
        choices=PUBLISH_STATUS_CHOICES,
        default='draft',
        verbose_name="Publish Status"
    )
    
    # اگر انتشار با شکست مواجه شود، دلیل آن در اینجا ذخیره می‌شود
    publish_error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="Publish Error Message"
    )
    
    # تاریخ و زمان انتشار موفقیت‌آمیز
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Published At"
    )

    # تاریخ و زمان ایجاد محتوا (به صورت خودکار)
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    
    # تاریخ و زمان آخرین به‌روزرسانی (به صورت خودکار)
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )

    def __str__(self):
        return f"Content for {self.campaign.title} on {self.platform} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        # برای خوانایی بیشتر در پنل ادمین
        verbose_name = "Generated Content"
        verbose_name_plural = "Generated Contents"
        
        # یک محدودیت برای جلوگیری از تولید محتوای تکراری برای یک کمپین و پلتفرم در یک زمان مشخص
        unique_together = ('campaign', 'platform', 'created_at')
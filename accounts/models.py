from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django_celery_beat.models import CrontabSchedule


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
    # Usage tracking fields
    is_used_by_ai = models.BooleanField(default=False, help_text="Whether this asset has been used by AI for content generation")
    used_at = models.DateTimeField(null=True, blank=True, help_text="When this asset was last used by AI")
    usage_count = models.PositiveIntegerField(default=0, help_text="Number of times this asset has been used by AI")

    def __str__(self):
        return self.name


class Campaign(models.Model):
    SESSION_TYPES = (
        ('single', 'Single Session'),
        ('multiple', 'Multiple Sessions'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    execution_period = models.IntegerField(default=7, help_text="Number of days for each execution period")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='single')
    times_per_week = models.IntegerField(null=True, blank=True)
    platform = models.ForeignKey('Platform', on_delete=models.CASCADE, related_name='campaigns')
    asset_library = models.ForeignKey('AssetLibrary', on_delete=models.CASCADE, related_name='campaigns')
    tags = models.ManyToManyField('Tag', blank=True)
    prompt = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class CampaignSchedule(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name="Campaign"
    )
    crontab = models.ForeignKey(
        CrontabSchedule,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Run At")
    next_run_at = models.DateTimeField(null=True, blank=True, verbose_name="Next Run At")
    
        # فیلدهای جدید برای نگهداری تاریخ شروع و پایان
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True, verbose_name="Is Enabled")

    def __str__(self):
        return f"Schedule for {self.campaign.title}"

    class Meta:
        verbose_name = "Campaign Schedule"
        verbose_name_plural = "Campaign Schedules"
        
        
class CampaignPost(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PUBLISHED = "PUBLISHED", "Published"
        DRAFT = "DRAFT", "Draft"
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField()
    publish_date = models.DateTimeField()
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING,
        help_text="Status of the post"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assets = models.ManyToManyField(Asset, through='PostAsset')

    class Meta:
        ordering = ['-created_at']
        


    def __str__(self):
        return f"Post for {self.campaign.title} at {self.publish_date} - {self.status}"

class PostAsset(models.Model):
    post = models.ForeignKey(CampaignPost, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('post', 'asset')

    def clean(self):
        # Getting the campaign related to this post
        campaign = self.post.campaign

        # Checking if this asset has already been used in other posts of the same campaign
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

class Notification(models.Model):
    """Model to track campaign notifications sent to users"""
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='notifications')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_url = models.URLField(max_length=500, help_text="URL sent to user for posting")
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False, help_text="Whether user has accessed the notification URL")
    accessed_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('campaign', 'user')
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Notification for {self.campaign.title} - {self.user.username}"
    
    def mark_as_read(self):
        """Mark notification as read and set accessed time"""
        self.is_read = True
        self.accessed_at = timezone.now()
        self.save()
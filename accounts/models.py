from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError



class Platform(models.Model):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title


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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaigns')
    title = models.CharField(max_length=200)
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='campaigns')
    start_date = models.DateField()
    end_date = models.DateField()
    execution_period = models.CharField(max_length=100, help_text="مثل: '*/5 * * * *' برای Celery Beat")
    asset_library = models.ForeignKey(AssetLibrary, on_delete=models.CASCADE, related_name='campaigns')
    tags = models.ManyToManyField(Tag, blank=True)
    prompt = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


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

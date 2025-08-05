from django.contrib import admin
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog,User,CampaignSchedule
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count


# ابتدا UserAdmin پیش‌فرض را از حالت ثبت خارج می‌کنیم
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # فیلدهای نمایش داده شده در لیست کاربران
    list_display = ('username', 'email', 'phone_number', 'role', 'is_staff', 'is_verified')
    
    # فیلترهای کناری در سمت راست
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'is_verified')
    
    # فیلدهای جستجو
    search_fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
    
    # فیلدهای فرم ویرایش کاربر را گروه‌بندی می‌کنیم
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'is_verified')}),
        ('اجازه‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'role')}),
        ('تاریخ‌های مهم', {'fields': ('last_login', 'date_joined')}),
    )
@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)


@admin.register(AssetLibrary)
class AssetLibraryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user',)
    search_fields = ('name', 'user__username',)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'library', 'file_type', 'created_at',)
    list_filter = ('file_type', 'library',)
    search_fields = ('name',)
    date_hierarchy = 'created_at'
    filter_horizontal = ('tags',)


class PostAssetInline(admin.TabularInline):
    model = PostAsset
    extra = 1
    raw_id_fields = ('asset',)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    # فیلدهایی که در لیست کمپین‌ها نمایش داده می‌شوند
    list_display = ('title', 'user', 'platform', 'status', 'start_date', 'is_active')
    
    # فیلدهایی که برای فیلتر کردن در سمت راست استفاده می‌شوند
    list_filter = ('status', 'platform', 'is_active', 'start_date')
    
    # فیلدهایی که برای جستجو در بالای صفحه استفاده می‌شوند
    search_fields = ('title', 'description', 'user__username', 'prompt')
    
    # نوار پیمایش تاریخی برای فیلد start_date
    date_hierarchy = 'start_date'
    
    # نحوه مرتب‌سازی پیش‌فرض
    ordering = ('-start_date',)
    
    # استفاده از فیلترهای افقی برای ManyToManyField
    filter_horizontal = ('tags',)
    
    # نمایش فیلدها به صورت گروه‌بندی شده
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'user', 'prompt', 'tags')
        }),
        ('زمان‌بندی و وضعیت', {
            'fields': ('start_date', 'end_date', 'execution_period', 'status', 'is_active')
        }),
        ('منابع کمپین', {
            'fields': ('platform', 'asset_library')
        }),
    )
    
    # نمایش فیلدهای ForeignKey به صورت یک فیلد متنی با ID برای کارایی بهتر
    # این به خصوص برای زمانی که تعداد زیادی کاربر یا پلتفرم دارید مفید است
    raw_id_fields = ('user', 'platform', 'asset_library')
    
@admin.register(CampaignSchedule)
class AdminCampaignSchedule(admin.ModelAdmin):
    list_display = ('campaign_title', 'crontab_schedule', 'is_enabled', 'last_run_at', 'next_run_at')
    search_fields = ('campaign__title',)
    list_filter = ('is_enabled',)
    readonly_fields = ('last_run_at', 'next_run_at')

    def campaign_title(self, obj):
        return obj.campaign.title
    campaign_title.short_description = 'Campaign'

@admin.register(CampaignPost)
class CampaignPostAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'publish_date',)
    list_filter = ('campaign', 'publish_date',)
    search_fields = ('content', 'campaign__title',)
    date_hierarchy = 'publish_date'
    inlines = [PostAssetInline,]


@admin.register(PostLog)
class PostLogAdmin(admin.ModelAdmin):
    list_display = ('post', 'status',)
    list_filter = ('status',)
    search_fields = ('post__campaign__title', 'status', 'error_message',)
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

class CampaignScheduleInline(admin.TabularInline):
    model = CampaignSchedule
    extra = 1
    fields = ('crontab_schedule','start_date', 'is_enabled', 'last_run_at', 'next_run_at')
    readonly_fields = ('last_run_at', 'next_run_at')


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'status', 'start_date', 'end_date', 'is_active')
    list_filter = ('status', 'platform', 'is_active')
    search_fields = ('title', 'prompt')
    inlines = [CampaignScheduleInline]


@admin.register(CampaignSchedule)
class CampaignScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'campaign','is_enabled', 'last_run_at', 'next_run_at')

    
@admin.register(CampaignPost)
class CampaignPostAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'publish_date',)
    list_filter = ('campaign', 'publish_date',)
    search_fields = ('content', 'campaign__title',)
    date_hierarchy = 'publish_date'
    inlines = [PostAssetInline,]

    def save_formset(self, request, form, formset, change):
        # Get the parent object before the formset is saved
        campaign_post = form.instance
        
        # Save the parent object if it's new
        if not campaign_post.pk:
            campaign_post.save()
        
        # Now, save the formset with the saved parent object
        super().save_formset(request, form, formset, change)    


@admin.register(PostLog)
class PostLogAdmin(admin.ModelAdmin):
    list_display = ('post', 'status',)
    list_filter = ('status',)
    search_fields = ('post__campaign__title', 'status', 'error_message',)
    
    


from django.contrib import admin
from .models import Platform, Tag, AssetLibrary, Asset, Campaign, CampaignPost, PostAsset, PostLog


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)


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
    list_display = ('title', 'user', 'platform', 'start_date', 'end_date', 'is_active',)
    list_filter = ('platform', 'is_active', 'start_date', 'end_date',)
    search_fields = ('title', 'user__username', 'prompt',)
    date_hierarchy = 'start_date'
    filter_horizontal = ('tags',)


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
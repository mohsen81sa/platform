from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'platforms', views.PlatformViewSet)
router.register(r'tags', views.TagViewSet)
router.register(r'asset-libraries', views.AssetLibraryViewSet)
router.register(r'assets', views.AssetViewSet)
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'campaign-posts', views.CampaignPostViewSet)
router.register(r'post-assets', views.PostAssetViewSet)
router.register(r'post-logs', views.PostLogViewSet)
router.register(r'notifications', views.NotificationViewSet)
router.register(r'campaigns/create-with-content', views.CampaignCreationViewSet, basename='campaign-creation')
urlpatterns = [
    path('api/', include(router.urls)),
    # اگر می‌خواهید رابط کاربری قابل مرور DRF را هم داشته باشید
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path("generate/",views.LinkedInContentGenerationAPIView.as_view()),
    path("notify-campaign/", views.CampaignNotificationAPIView.as_view()),
    path("campaign/<int:campaign_id>/posts/", views.CampaignPostsView.as_view()),
]
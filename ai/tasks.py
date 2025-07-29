import os
import random
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from accounts.models import RawContent, Tag, Campaign, GeneratedPost
from ai.ai_integrations import generate_text_from_gemini, generate_linkedin_post_prompt, generate_tags_from_gemini

@shared_task
def tag_content_task(raw_content_id):
    """
    تسک Celery برای تگ‌گذاری محتوای خام با استفاده از AI.
    """
    try:
        raw_content = RawContent.objects.get(id=raw_content_id)
        content_for_ai = raw_content.text_content
        if raw_content.content_type in ['image', 'video'] and raw_content.file:
            # برای تگ‌گذاری تصویر/ویدئو، شاید نیاز باشد فایل را به متن تبدیل کنیم یا توضیحات فایل را استخراج کنیم.
            # اینجا فرض می‌کنیم متنی مرتبط با تصویر برای تگ‌گذاری موجود است یا از Gemini Vision استفاده می‌شود.
            # برای سادگی، فعلاً متنی ساده را به عنوان ورودی AI می‌دهیم اگر محتوای متنی خام نباشد.
            content_for_ai = f"Content of type {raw_content.content_type} uploaded at {raw_content.uploaded_at.strftime('%Y-%m-%d %H:%M')}"
            if raw_content.file:
                # اگر Gemini Vision از مسیر فایل پشتیبانی می‌کند:
                # tags = generate_tags_from_gemini(str(raw_content.file.path), raw_content.content_type)
                pass # در حال حاضر tag_content_task فقط برای text_content استفاده می‌شود
            else:
                pass

        if raw_content.text_content:
            generated_tags = generate_tags_from_gemini(raw_content.text_content, raw_content.content_type)
        else:
            # اگر محتوای متنی نیست، می‌توانیم بر اساس نام فایل یا توضیحات پیش‌فرض تگ کنیم.
            # یا می‌توان از Gemini Vision برای توصیف تصویر استفاده کرد و سپس تگ کرد.
            # برای این مثال، اگر text_content خالی بود، تگ نمی‌کنیم.
            generated_tags = []

        for tag_name in generated_tags:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            raw_content.tags.add(tag)
        raw_content.save()
        print(f"Content {raw_content_id} tagged with: {generated_tags}")

    except RawContent.DoesNotExist:
        print(f"RawContent with ID {raw_content_id} not found.")
    except Exception as e:
        print(f"Error tagging content {raw_content_id}: {e}")

@shared_task
def generate_post_for_campaign_task(campaign_id):
    """
    تسک Celery برای تولید یک پست جدید برای یک کمپین.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        if not campaign.is_active:
            print(f"Campaign {campaign_id} is not active. Skipping post generation.")
            return

        selected_contents = list(campaign.selected_content.all())
        if not selected_contents:
            print(f"Campaign {campaign_id} has no selected content.")
            return

        # انتخاب یک محتوای تصادفی
        raw_content = random.choice(selected_contents)
        
        # استخراج متن و تگ‌ها برای پرامپت AI
        content_text_for_ai = raw_content.text_content if raw_content.text_content else ""
        
        # اگر فایل تصویر/ویدئو است، مسیر آن را برای Gemini Vision آماده می‌کنیم.
        # برای Gemini Pro Vision، نیاز به مسیر فایل یا داده‌های باینری تصویر داریم.
        image_file_path = None
        if raw_content.content_type in ['image', 'video'] and raw_content.file:
            image_file_path = raw_content.file.path
            # اگر محتوای متنی وجود ندارد، می‌توانیم به Gemini بگوییم بر اساس تصویر توضیحاتی بدهد.
            if not content_text_for_ai:
                content_text_for_ai = f"Image content related to {', '.join([tag.name for tag in raw_content.tags.all()]) if raw_content.tags.exists() else 'various topics'}."
        
        tags = [tag.name for tag in raw_content.tags.all()]
        
        prompt = generate_linkedin_post_prompt(content_text_for_ai, tags, raw_content.content_type)
        
        # تولید متن پست با AI
        generated_text = generate_text_from_gemini(prompt, image_file_path if raw_content.content_type == 'image' else None)

        # محاسبه زمان برنامه‌ریزی شده برای انتشار
        last_generated_post = GeneratedPost.objects.filter(campaign=campaign).order_by('-scheduled_publish_time').first()
        if last_generated_post and last_generated_post.scheduled_publish_time:
            scheduled_publish_time = last_generated_post.scheduled_publish_time + campaign.get_schedule_interval()
        else:
            scheduled_publish_time = campaign.start_time

        # ذخیره پست تولید شده
        GeneratedPost.objects.create(
            campaign=campaign,
            raw_content=raw_content,
            generated_text=generated_text,
            scheduled_publish_time=scheduled_publish_time,
            status='pending_review' # وضعیت اولیه: منتظر بازبینی
        )
        print(f"Generated post for campaign {campaign_id} with status 'pending_review'.")

    except Campaign.DoesNotExist:
        print(f"Campaign with ID {campaign_id} not found.")
    except Exception as e:
        print(f"Error generating post for campaign {campaign_id}: {e}")

@shared_task
def schedule_campaign_posts_task():
    """
    تسک Celery Beat برای بررسی کمپین‌ها و برنامه‌ریزی تولید پست‌های جدید.
    """
    print("Running schedule_campaign_posts_task...")
    active_campaigns = Campaign.objects.filter(is_active=True)
    now = timezone.now()

    for campaign in active_campaigns:
        last_generated_post = GeneratedPost.objects.filter(campaign=campaign).order_by('-scheduled_publish_time').first()

        next_generation_time = campaign.start_time
        if last_generated_post and last_generated_post.scheduled_publish_time:
            next_generation_time = last_generated_post.scheduled_publish_time + campaign.get_schedule_interval()
        
        # اگر زمان فعلی از زمان تولید پست بعدی گذشته است و کمپین هنوز به پایان نرسیده
        if now >= next_generation_time and (campaign.end_time is None or now < campaign.end_time):
            print(f"Scheduling post generation for campaign {campaign.id}. Next generation time: {next_generation_time}")
            generate_post_for_campaign_task.delay(campaign.id)
        else:
            print(f"Campaign {campaign.id} not ready for new post generation yet. Next scheduled: {next_generation_time}")
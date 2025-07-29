import os
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from django.conf import settings
from PIL import Image
import io

# کانفیگ Gemini API
genai.configure(api_key=settings.GOOGLE_API_KEY)

def generate_text_from_gemini(prompt: str, image_file_path: str = None) -> str:
    """
    تولید متن با استفاده از Gemini بر اساس پرامپت و تصویر (اختیاری).
    """
    model = ChatGoogleGenerativeAI(model="gemini-pro-vision" if image_file_path else "gemini-pro")
    messages = [HumanMessage(content=prompt)]

    if image_file_path:
        try:
            with Image.open(image_file_path) as img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format=img.format)
                img_byte_arr = img_byte_arr.getvalue()
                messages.append(HumanMessage(content=[{"type": "image_url", "image_url": {"url": f"data:image/{img.format.lower()};base64,{img_byte_arr.decode('latin-1')}"}}]))
                # Note: For Langchain, you might need to pass the image directly as a PIL Image object
                # or a base64 encoded string depending on the exact version and method.
                # The above is a simplification; a direct integration might look like:
                # result = model.invoke([HumanMessage(content=[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_file_path}}])])
                # However, for simplicity and broader compatibility with file paths, let's use a more direct approach.
                # For direct use with `genai.GenerativeModel`:
                model_vision = genai.GenerativeModel('gemini-pro-vision')
                response = model_vision.generate_content([prompt, Image.open(image_file_path)])
                return response.text
        except Exception as e:
            print(f"Error processing image for Gemini: {e}")
            # Fallback to text-only if image processing fails
            model = ChatGoogleGenerativeAI(model="gemini-pro")
            return model.invoke(messages).content
    else:
        return model.invoke(messages).content

def generate_linkedin_post_prompt(raw_content_text: str, tags: list, content_type: str) -> str:
    """
    تولید پرامپت مناسب برای LinkedIn بر اساس محتوای خام و تگ‌ها.
    """
    tag_str = ", ".join(tags)
    prompt = f"""
    You are an expert LinkedIn content creator. Your task is to write a compelling LinkedIn post based on the following raw content.
    The post should be professional, engaging, and optimized for LinkedIn's audience.
    Include relevant hashtags. Aim for conciseness and impact.

    Content Type: {content_type}
    Associated Tags: {tag_str}

    Raw Content:
    ---
    {raw_content_text}
    ---

    Please provide only the LinkedIn post text.
    """
    return prompt

def generate_tags_from_gemini(content_data: str, content_type: str) -> list:
    """
    تولید تگ‌ها با استفاده از Gemini بر اساس محتوای خام.
    """
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""
    Generate 5-10 relevant and concise tags (keywords) for the following {content_type} content.
    Tags should be comma-separated. Do NOT include hashtags.

    Content:
    ---
    {content_data}
    ---

    Examples: marketing, AI, technology, innovation, leadership, business, startup
    """
    response = model.generate_content(prompt)
    try:
        tags_str = response.text.strip()
        return [tag.strip() for tag in tags_str.split(',') if tag.strip()]
    except Exception as e:
        print(f"Error parsing tags from Gemini: {e}")
        return []
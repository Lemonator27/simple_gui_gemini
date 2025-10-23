from .api_client import api_client


def chat_completions(messages, model=None, temperature=None, use_web_search=False):
    return api_client.chat_completions(messages, model, temperature, use_web_search)

def generate_image(prompt, model="gemini-2.5-flash-image-preview", aspect_ratio="1:1", n=1, image_context=None):
    return api_client.generate_image(prompt, model, aspect_ratio, n, image_context)

def save_image(image_data, filename):
    return api_client.save_image(image_data, filename)

def generate_video(prompt, model='veo-3.0-generate-001', aspect_ratio='16:9', duration=8, negative_prompt='blurry, low quality', person_generation='allow_all', reference_images=None, first_frame_image_data=None, last_frame_image_data=None):
    return api_client.generate_video(prompt, model, aspect_ratio, duration, negative_prompt, person_generation, reference_images, first_frame_image_data, last_frame_image_data)

def text_to_speech(input_text: str, model: str = "gemini-2.5-flash-preview-tts", voice: str = "Zephyr", audio_format: str = "mp3", filename: str | None = None, timeout: int = 120):
    return api_client.text_to_speech(input_text, model, voice, audio_format, filename, timeout)

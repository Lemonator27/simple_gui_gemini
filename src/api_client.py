import os
import base64
import time
import requests
import json
import filetype
from dotenv import load_dotenv
import litellm
from openai import OpenAI

load_dotenv()

class ApiClient:
    def __init__(self):
        self.api_base = os.getenv("THUCCHIEN_API_BASE", "https://api.thucchien.ai")
        self.api_key = os.getenv("THUCCHIEN_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.default_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
        self.default_temp = float(os.getenv("TEMPERATURE", "1.0"))
        litellm.api_base = self.api_base
        self.openai_client = OpenAI(api_key=self.api_key, base_url=self.api_base)

    def chat_completions(self, messages, model=None, temperature=None, use_web_search=False):
        kwargs = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": self.default_temp if temperature is None else temperature,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "custom_llm_provider": "openai",
        }
        if use_web_search:
            kwargs["web_search_options"] = {"search_context_size": "medium"}
        resp = litellm.completion(**kwargs)
        content = getattr(resp.choices[0].message, "content", str(resp))
        return {"raw": resp, "content": content}

    def generate_image(self, prompt, model="gemini-2.5-flash-image-preview", aspect_ratio="1:1", n=1, image_context=None):
        try:
            content = [{"type": "text", "text": prompt}]
            if image_context:
                for img_data in image_context:
                    img_b64 = base64.b64encode(img_data).decode("utf-8")
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}})
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                modalities=["image"],
            )
            if response and response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                if hasattr(message, "images") and message.images:
                    base64_string = message.images[0].get("image_url", {}).get("url", "")
                    if base64_string:
                        encoded = base64_string.split(",", 1)[1] if "," in base64_string else base64_string
                        image_data = base64.b64decode(encoded)
                        return {"success": True, "image_data": image_data, "b64_json": encoded, "prompt": prompt, "model": model, "aspect_ratio": aspect_ratio}
                    else:
                        return {"success": False, "error": "No base64 image data in response"}
                else:
                    return {"success": False, "error": "No images in response message"}
            else:
                return {"success": False, "error": "No choices in response"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_image(self, image_data, filename):
        os.makedirs("generated_images", exist_ok=True)
        filepath = os.path.join("generated_images", filename)
        with open(filepath, "wb") as f:
            f.write(image_data)
        return filepath

    def _b64(self, img_bytes: bytes) -> str:
        return base64.b64encode(img_bytes).decode("utf-8")

    def _detect_mime(self, img_bytes: bytes) -> str:
        kind = filetype.guess(img_bytes)
        if kind is None:
            return 'image/png'
        return kind.mime

    def _image_obj(self, img_bytes: bytes) -> dict:
        return {"bytesBase64Encoded": self._b64(img_bytes), "mimeType": self._detect_mime(img_bytes)}

    def generate_video_api_call(self, prompt, model='veo-3.0-generate-001', negative_prompt='blurry, low quality', aspect_ratio='16:9', resolution='1080p', person_generation='allow_all', duration_seconds=8, reference_images=None, first_frame_image_data=None, last_frame_image_data=None):
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        if not prompt and not first_frame_image_data and not reference_images:
            raise ValueError("Provide at least a prompt or some images (reference/first frame).")
        step1_url = f'{self.api_base}/gemini/v1beta/models/{model}:predictLongRunning'
        instance = {'prompt': prompt or ""}
        if first_frame_image_data:
            instance["image"] = self._image_obj(first_frame_image_data)
        parameters = {
            'negativePrompt': negative_prompt, 'aspectRatio': aspect_ratio, 'resolution': resolution,
            'personGeneration': person_generation, 'durationSeconds': int(duration_seconds)
        }
        if last_frame_image_data:
            parameters["lastFrame"] = {"image": self._image_obj(last_frame_image_data)}
        if reference_images:
            parameters["referenceImages"] = [{"image": self._image_obj(b)} for b in reference_images[:3]]
        step1_payload = {'instances': [instance], 'parameters': parameters}
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': self.gemini_api_key}
        response1 = requests.post(step1_url, json=step1_payload, headers=headers)
        if response1.status_code != 200:
            response1.raise_for_status()
        operation_name = response1.json().get('name')
        if not operation_name:
            raise ValueError('No operation name returned from video generation start.')
        max_attempts = 60
        attempt = 0
        while attempt < max_attempts:
            step2_url = f'{self.api_base}/gemini/v1beta/{operation_name}'
            response2 = requests.get(step2_url, headers=headers)
            if response2.status_code != 200:
                response2.raise_for_status()
            result = response2.json()
            if result.get('done'):
                try:
                    if "response" in result and "generateVideoResponse" in result["response"] and result["response"]["generateVideoResponse"]["generatedSamples"]:
                        video_uri = result['response']['generateVideoResponse']['generatedSamples'][0]['video']['uri']
                    else:
                        raise ValueError("No 'generateVideoResponse' found in the completion payload.")
                    video_id = video_uri.split('/files/')[1].split(':')[0]
                    return {"video_id": video_id, "video_uri": video_uri}
                except (KeyError, IndexError) as e:
                    raise ValueError(f"Invalid response format from video generation status: {e}")
            attempt += 1
            time.sleep(5)
        raise TimeoutError('Video generation timeout.')

    def download_video_api_call(self, video_id):
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        download_url = f"{self.api_base}/gemini/download/v1beta/files/{video_id}:download?alt=media"
        headers = {"x-goog-api-key": self.gemini_api_key}
        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()
        return response.content

    def generate_video(self, prompt, model='veo-3.0-generate-001', aspect_ratio='16:9', duration=8, negative_prompt='blurry, low quality', person_generation='allow_all', reference_images=None, first_frame_image_data=None, last_frame_image_data=None):
        try:
            resolution_to_use = "1080p" if aspect_ratio == "16:9" else "720p"
            video_gen_result = self.generate_video_api_call(
                prompt=prompt, model=model, aspect_ratio=aspect_ratio, resolution=resolution_to_use,
                duration_seconds=duration, negative_prompt=negative_prompt, person_generation=person_generation,
                reference_images=reference_images, first_frame_image_data=first_frame_image_data,
                last_frame_image_data=last_frame_image_data,
            )
            if video_gen_result and "video_id" in video_gen_result:
                video_id = video_gen_result["video_id"]
                video_data = self.download_video_api_call(video_id)
                return {
                    "success": True, "video_data": video_data, "video_id": video_id, "prompt": prompt,
                    "model": model, "resolution": resolution_to_use, "aspect_ratio": aspect_ratio,
                    "duration": duration, "negative_prompt": negative_prompt,
                    "reference_images": bool(reference_images),
                    "first_frame_present": bool(first_frame_image_data),
                    "last_frame_present": bool(last_frame_image_data),
                }
            else:
                return {"success": False, "error": video_gen_result.get("error", "Unknown error during video generation start.")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def text_to_speech(self, input_text: str, model: str = "gemini-2.5-flash-preview-tts", voice: str = "Zephyr", audio_format: str = "mp3", filename: str | None = None, timeout: int = 120):
        if not self.api_key:
            return {"success": False, "error": "THUCCHIEN_API_KEY is not set.", "status_code": 0}
        url = f"{self.api_base}/audio/speech"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {"model": model, "input": input_text, "voice": voice}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
            status = resp.status_code
            content_type = resp.headers.get("Content-Type", "")
            if not content_type.startswith("audio/"):
                try:
                    data = resp.json()
                except Exception:
                    data = {"message": resp.text[:500]}
                return {"success": False, "status_code": status, "content_type": content_type, "error": data.get("error") or data.get("message") or "Unexpected non-audio response."}
            os.makedirs("generativeAudios", exist_ok=True)
            ext_map = {
                "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
                "audio/ogg": "ogg", "audio/opus": "opus", "audio/webm": "webm", "audio/aac": "aac",
                "audio/flac": "flac",
            }
            ext = ext_map.get(content_type.lower(), audio_format.lower() if audio_format else "mp3")
            if not filename:
                safe_voice = "".join(c for c in voice if c.isalnum() or c in ("-", "_")).strip() or "voice"
                ts = int(time.time())
                filename = f"tts_{safe_voice}_{ts}.{ext}"
            elif not filename.lower().endswith(f".{ext}"):
                filename = f"{filename}.{ext}"
            out_path = os.path.join("generativeAudios", filename)
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            file_size = os.path.getsize(out_path)
            return {"success": True, "status_code": status, "content_type": content_type, "path": out_path, "bytes": file_size, "model": model, "voice": voice}
        except requests.RequestException as e:
            return {"success": False, "error": str(e), "status_code": 0}

api_client = ApiClient()

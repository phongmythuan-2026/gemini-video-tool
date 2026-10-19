"""
Tên file: video_generator_tool.py
Mô tả: Công cụ tự động hóa hoàn thiện sử dụng SDK `google-genai` chuẩn mới, 
       hỗ trợ xoay vòng Key Pool, xử lý đa phương thức (Text + Multi-images), 
       chọn khung hình (9:16 / 16:9), tạo giọng đọc Edge-TTS và Render Video MoviePy.
"""

import os
import time
import asyncio
from pathlib import Path
from google import genai
from PIL import Image
from moviepy.video.VideoClip import ColorClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

class GeminiKeyPool:
    def __init__(self, api_keys: list[str], model_name: str = "gemini-1.5-flash"):
        if not api_keys:
            raise ValueError("Danh sách API Key không được để trống!")
        self.api_keys = api_keys
        self.current_index = 0
        self.model_name = model_name
        self._init_client()

    def _init_client(self):
        current_key = self.api_keys[self.current_index]
        # Khởi tạo client chính thức theo SDK mới google-genai
        self.client = genai.Client(api_key=current_key)
        print(f"[INFO] Đang sử dụng Tài khoản / API Key thứ {self.current_index + 1}/{len(self.api_keys)} với model: {self.model_name}")

    def rotate_key(self):
        """Chuyển sang key tiếp theo khi key hiện tại gặp giới hạn hoặc lỗi."""
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Key hiện tại gặp lỗi/chạm giới hạn. Đang chuyển sang Key thứ {self.current_index + 1}...")
        self._init_client()

    def generate_content_with_fallback(self, contents):
        """Gọi API với cơ chế xoay vòng key tự động khi gặp lỗi."""
        total_keys = len(self.api_keys)
        checked_keys = 0

        while checked_keys < total_keys:
            try:
                # Cú pháp chuẩn của google-genai SDK
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                )
                return response.text
            except Exception as e:
                print(f"[WARN] Key {self.current_index + 1} gặp lỗi: {e}")
                self.rotate_key()
                checked_keys += 1
                time.sleep(3)
        
        raise Exception("[CRITICAL] Tất cả các tài khoản Google API trong Pool đều đã gặp lỗi!")

async def generate_voiceover(text: str, output_audio_path: str):
    """Sử dụng edge-tts để tạo file âm thanh tiếng Việt từ kịch bản."""
    import edge_tts
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def render_video_with_audio(audio_path: str, output_video_path: str, aspect_ratio: str):
    """Render video với khung hình tùy chọn 9:16 hoặc 16:9 sử dụng MoviePy chuẩn."""
    print(f"[INFO] Bắt đầu render video với tỷ lệ {aspect_ratio}...")
    try:
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration

        # Thiết lập kích thước khung hình
        if aspect_ratio == "16:9":
            width, height = 1280, 720  # Khung ngang YouTube
        else:
            width, height = 720, 1280  # Khung dọc TikTok/Shorts (mặc định 9:16)

        background = ColorClip(size=(width, height), color=(20, 24, 33), duration=duration)
        video = background.set_audio(audio_clip)

        video.write_videofile(
            output_video_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            logger=None
        )
        
        audio_clip.close()
        video.close()
        print(f"[SUCCESS] Đã render video thành công: {output_video_path}")
    except Exception as e:
        print(f"[ERROR] Lỗi khi render video: {e}")
        raise e

def main():
    # Lấy danh sách key từ biến môi trường GitHub Secrets
    keys_env = os.getenv("GEMINI_KEYS", "")
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    if not api_keys:
        print("[ERROR] Không tìm thấy biến môi trường GEMINI_KEYS!")
        return

    # Khởi tạo Pool quản lý key (Sử dụng model gemini-1.5-flash ổn định)
    pool = GeminiKeyPool(api_keys=api_keys, model_name="gemini-1.5-flash")

    # Đọc tham số từ giao diện GitHub Actions
    input_filename = os.getenv("INPUT_FILENAME", "").strip()
    input_topic = os.getenv("INPUT_TOPIC", "").strip()
    aspect_ratio = os.getenv("ASPECT_RATIO", "9:16").strip()
    images_folder = os.getenv("IMAGES_FOLDER", "").strip()

    # 1. Tải danh sách hình ảnh đa phương thức (nếu có thư mục ảnh)
    pil_images = []
    if images_folder:
        folder_path = Path("inputs") / images_folder
        if folder_path.exists() and folder_path.is_dir():
            print(f"[INFO] Đang quét hình ảnh từ thư mục: {folder_path}")
            valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
            for img_file in sorted(folder_path.iterdir()):
                if img_file.suffix.lower() in valid_extensions:
                    try:
                        img = Image.open(img_file)
                        pil_images.append(img)
                        print(f"[LOADED] Đã tải ảnh: {img_file.name}")
                    except Exception as ex:
                        print(f"[WARNING] Không thể mở file ảnh {img_file.name}: {ex}")

    # 2. Thu thập danh sách tác vụ / prompt
    tasks = []
    if input_filename:
        file_path = Path("inputs") / input_filename
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            tasks = [line.strip() for line in lines if line.strip()]

    if not tasks and input_topic:
        tasks = [input_topic]

    if not tasks:
        tasks = ["Viết kịch bản ngắn dựa trên các hình ảnh đính kèm mô tả sản phẩm/quy trình."]

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, task in enumerate(tasks, 1):
        print(f"\n======================================")
        print(f"Đang xử lý tác vụ {idx}: {task} (Khung hình: {aspect_ratio})")
        print(f"======================================")
        try:
            # Đóng gói dữ liệu đa phương thức chuẩn SDK mới [Prompt, Ảnh 1, Ảnh 2, ...]
            gemini_payload = [task] + pil_images if pil_images else task

            # Sinh kịch bản qua Gemini Pool
            script_text = pool.generate_content_with_fallback(gemini_payload)
            
            timestamp = int(time.time())
            script_path = output_dir / f"script_{idx}_{timestamp}.txt"
            script_path.write_text(script_text, encoding="utf-8")
            print(f"[SUCCESS] Đã lưu kịch bản vào: {script_path}")
            
            # Tạo file âm thanh giọng đọc MP3
            audio_path = output_dir / f"voice_{idx}_{timestamp}.mp3"
            asyncio.run(generate_voiceover(script_text, str(audio_path)))
            
            # Render video hoàn chỉnh theo tỷ lệ khung hình
            video_path = output_dir / f"video_{idx}_{timestamp}.mp4"
            render_video_with_audio(str(audio_path), str(video_path), aspect_ratio)
            
            time.sleep(2)
        except Exception as e:
            print(f"[FATAL] Tác vụ thất bại: {e}")
            break

    print("\n[INFO] Hoàn thành toàn bộ quy trình sinh kịch bản, giọng đọc và render video!")

if __name__ == "__main__":
    main()

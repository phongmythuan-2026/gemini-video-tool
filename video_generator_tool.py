"""
Tên file: video_generator_tool.py
Mô tả: Công cụ tự động hóa hoàn thiện với cơ chế Tự động dò tìm Model khả dụng của Key,
       Xoay vòng Key Pool, xử lý Excel/Text, Multi-images, Edge-TTS và MoviePy.
"""

import os
import time
import asyncio
from pathlib import Path
import pandas as pd
from google import genai
from PIL import Image
from moviepy.video.VideoClip import ColorClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

def get_auto_detected_model(client) -> str:
    """Tự động quét danh sách model được phép sử dụng từ API key hiện tại để chọn model Flash tối ưu."""
    try:
        models = client.models.list()
        available_models = []
        for m in models:
            name = m.name.replace("models/", "")
            # Ưu tiên tìm các dòng model flash hỗ trợ sinh nội dung
            if "flash" in name.lower():
                available_models.append(name)
        
        if available_models:
            # Lấy model flash đầu tiên hoặc mới nhất tìm được
            selected = available_models[0]
            print(f"[INFO] Tự động phát hiện model hợp lệ cho API key này: {selected}")
            return selected
    except Exception as e:
        print(f"[WARNING] Không thể tự động quét model từ API: {e}")
    
    # Dự phòng an toàn nếu không quét được
    return "gemini-1.5-flash"

class GeminiKeyPool:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("Danh sách API Key không được để trống!")
        self.api_keys = api_keys
        self.current_index = 0
        self._init_client()

    def _init_client(self):
        current_key = self.api_keys[self.current_index]
        self.client = genai.Client(api_key=current_key)
        # Tự động dò tìm model chạy mượt nhất cho key này
        self.model_name = get_auto_detected_model(self.client)
        print(f"[INFO] Đang sử dụng Tài khoản / API Key thứ {self.current_index + 1}/{len(self.api_keys)} với model: {self.model_name}")

    def rotate_key(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Key hiện tại gặp lỗi. Đang chuyển sang Key thứ {self.current_index + 1}...")
        self._init_client()

    def generate_content_with_fallback(self, contents):
        total_keys = len(self.api_keys)
        checked_keys = 0

        while checked_keys < total_keys:
            try:
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
    import edge_tts
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def render_video_with_audio(audio_path: str, output_video_path: str, aspect_ratio: str):
    print(f"[INFO] Bắt đầu render video với tỷ lệ {aspect_ratio}...")
    try:
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration

        if aspect_ratio == "16:9":
            width, height = 1280, 720
        else:
            width, height = 720, 1280

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
    keys_env = os.getenv("GEMINI_KEYS", "")
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    if not api_keys:
        print("[ERROR] Không tìm thấy biến môi trường GEMINI_KEYS!")
        return

    # Khởi tạo Pool quản lý key tự động dò tìm model
    pool = GeminiKeyPool(api_keys=api_keys)

    input_filename = os.getenv("INPUT_FILENAME", "").strip()
    input_topic = os.getenv("INPUT_TOPIC", "").strip()
    aspect_ratio = os.getenv("ASPECT_RATIO", "9:16").strip()
    images_folder = os.getenv("IMAGES_FOLDER", "").strip()

    # 1. Tải danh sách hình ảnh đa phương thức (nếu có)
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

    # 2. Đọc danh sách tác vụ từ file (.xlsx hoặc .txt)
    tasks = []
    if input_filename:
        file_path = Path("inputs") / input_filename
        if not file_path.exists():
            file_path = Path(input_filename)

        if file_path.exists():
            print(f"[INFO] Đang đọc file dữ liệu: {file_path}")
            if file_path.suffix.lower() == ".xlsx":
                df = pd.read_excel(file_path)
                tasks = df.iloc[:, 0].dropna().astype(str).tolist()
            else:
                lines = file_path.read_text(encoding="utf-8").splitlines()
                tasks = [line.strip() for line in lines if line.strip()]
        else:
            print(f"[WARNING] Không tìm thấy file {input_filename}")

    if not tasks and input_topic:
        tasks = [input_topic]

    if not tasks:
        tasks = ["Viết kịch bản ngắn nấu ăn miền Tây."]

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, task in enumerate(tasks, 1):
        print(f"\n======================================")
        print(f"Đang xử lý tác vụ {idx}: {task} (Khung hình: {aspect_ratio})")
        print(f"======================================")
        try:
            gemini_payload = [task] + pil_images if pil_images else task
            script_text = pool.generate_content_with_fallback(gemini_payload)
            
            timestamp = int(time.time())
            script_path = output_dir / f"script_{idx}_{timestamp}.txt"
            script_path.write_text(script_text, encoding="utf-8")
            print(f"[SUCCESS] Đã lưu kịch bản vào: {script_path}")
            
            audio_path = output_dir / f"voice_{idx}_{timestamp}.mp3"
            asyncio.run(generate_voiceover(script_text, str(audio_path)))
            
            video_path = output_dir / f"video_{idx}_{timestamp}.mp4"
            render_video_with_audio(str(audio_path), str(video_path), aspect_ratio)
            
            time.sleep(2)
        except Exception as e:
            print(f"[FATAL] Tác vụ thất bại: {e}")
            break

    print("\n[INFO] Hoàn thành toàn bộ quy trình tự động hóa thành công!")

if __name__ == "__main__":
    main()

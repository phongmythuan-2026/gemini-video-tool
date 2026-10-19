"""
Tên file: video_generator_tool.py
Mô tả: Hỗ trợ đọc danh sách kịch bản linh hoạt từ file Text hoặc file Excel (.xlsx),
       tự động quét model Gemini mới nhất, xoay vòng Key Pool, xử lý Multi-images và Render Video.
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

def get_best_available_model(client) -> str:
    """Tự động quét danh sách model từ API và chọn model Flash khả dụng."""
    try:
        models = client.models.list()
        for m in models:
            model_name = m.name.replace("models/", "")
            if "flash" in model_name.lower():
                print(f"[INFO] Tự động chọn model khả dụng: {model_name}")
                return model_name
    except Exception as e:
        print(f"[WARNING] Không thể quét danh sách model: {e}")
    return "gemini-2.5-flash"

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
        self.model_name = get_best_available_model(self.client)
        print(f"[INFO] Đang sử dụng Tài khoản / API Key thứ {self.current_index + 1}/{len(self.api_keys)} với model: {self.model_name}")

    def rotate_key(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Key hiện tại gặp lỗi/chạm giới hạn. Đang chuyển sang Key thứ {self.current_index + 1}...")
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

    # 2. Đọc danh sách tác vụ từ file (Hỗ trợ cả .txt và .xlsx)
    tasks = []
    if input_filename:
        # Kiểm tra xem file ở thư mục inputs/ hay ở thư mục gốc
        file_path = Path("inputs") / input_filename
        if not file_path.exists():
            file_path = Path(input_filename) # Tìm ở thư mục gốc

        if file_path.exists():
            print(f"[INFO] Đang đọc file dữ liệu: {file_path}")
            if file_path.suffix.lower() == ".xlsx":
                # Đọc file Excel (lấy dữ liệu từ cột đầu tiên hoặc cột chứa kịch bản)
                df = pd.read_excel(file_path)
                # Lấy tất cả các dòng ở cột đầu tiên bỏ qua ô trống
                tasks = df.iloc[:, 0].dropna().astype(str).tolist()
            else:
                # Đọc file text thông thường
                lines = file_path.read_text(encoding="utf-8").splitlines()
                tasks = [line.strip() for line in lines if line.strip()]
        else:
            print(f"[WARNING] Không tìm thấy file {input_filename} ở cả thư mục inputs/ lẫn thư mục gốc.")

    if not tasks and input_topic:
        tasks = [input_topic]

    if not tasks:
        tasks = ["Viết kịch bản ngắn nấu ăn miền Tây dựa trên dữ liệu Excel."]

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

    print("\n[INFO] Hoàn thành toàn bộ quy trình đọc Excel và tạo video tự động!")

if __name__ == "__main__":
    main()

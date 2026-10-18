"""
Tên file: video_generator_tool.py
Mô tả: Hỗ trợ đọc danh sách tác vụ từ file kịch bản có sẵn trên repo hoặc nhập trực tiếp.
"""

import os
import time
import asyncio
from pathlib import Path
import google.generativeai as genai

class GeminiKeyPool:
    def __init__(self, api_keys: list[str], model_name: str = "gemini-2.5-flash"):
        if not api_keys:
            raise ValueError("Danh sách API Key không được để trống!")
        self.api_keys = api_keys
        self.current_index = 0
        self.model_name = model_name
        self._init_client()

    def _init_client(self):
        current_key = self.api_keys[self.current_index]
        genai.configure(api_key=current_key)
        self.model = genai.GenerativeModel(self.model_name)
        print(f"[INFO] Đang sử dụng Tài khoản / API Key thứ {self.current_index + 1}/{len(self.api_keys)}")

    def rotate_key(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Key hiện tại đã chạm giới hạn. Đang chuyển sang Key thứ {self.current_index + 1}...")
        self._init_client()

    def generate_content_with_fallback(self, prompt: str):
        total_keys = len(self.api_keys)
        checked_keys = 0

        while checked_keys < total_keys:
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                if any(err in error_str for err in ["429", "quota", "resourceexhausted", "exhausted", "limit"]):
                    print(f"[WARN] Key {self.current_index + 1} gặp lỗi hạn mức: {e}")
                    self.rotate_key()
                    checked_keys += 1
                    time.sleep(3)
                else:
                    raise e
        raise Exception("[CRITICAL] Tất cả các tài khoản Google API đều đã hết hạn mức!")

async def generate_voiceover(text: str, output_audio_path: str):
    import edge_tts
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def main():
    keys_env = os.getenv("GEMINI_KEYS", "")
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    if not api_keys:
        print("[ERROR] Không tìm thấy biến môi trường GEMINI_KEYS!")
        return

    pool = GeminiKeyPool(api_keys=api_keys, model_name="gemini-2.5-flash")

    # Lấy thông số từ môi trường GitHub Actions
    input_filename = os.getenv("INPUT_FILENAME", "").strip()
    input_topic = os.getenv("INPUT_TOPIC", "").strip()

    tasks = []

    # Ưu tiên 1: Đọc từ file kịch bản có sẵn trong thư mục inputs/ trên repo
    if input_filename:
        file_path = Path("inputs") / input_filename
        if file_path.exists():
            print(f"[INFO] Đang đọc danh sách tác vụ từ file: {file_path}")
            lines = file_path.read_text(encoding="utf-8").splitlines()
            tasks = [line.strip() for line in lines if line.strip()]
        else:
            print(f"[WARNING] Không tìm thấy file {file_path}. Chuyển sang kiểm tra chủ đề trực tiếp.")

    # Ưu tiên 2: Nếu không có file hoặc file trống, lấy nội dung nhập trực tiếp
    if not tasks and input_topic:
        tasks = [input_topic]
        print(f"[INFO] Nhận chủ đề trực tiếp từ giao diện: {input_topic}")

    # Mặc định nếu không nhập gì cả
    if not tasks:
        tasks = ["Viết kịch bản ngắn 30s TikTok: Bí quyết tối ưu hóa quy trình sản xuất tinh gọn."]

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, task in enumerate(tasks, 1):
        print(f"\n======================================")
        print(f"Đang xử lý tác vụ {idx}: {task}")
        print(f"======================================")
        try:
            script_text = pool.generate_content_with_fallback(task)
            
            timestamp = int(time.time())
            script_path = output_dir / f"script_{idx}_{timestamp}.txt"
            script_path.write_text(script_text, encoding="utf-8")
            print(f"[SUCCESS] Đã lưu kịch bản vào: {script_path}")
            
            audio_path = output_dir / f"voice_{idx}_{timestamp}.mp3"
            asyncio.run(generate_voiceover(script_text, str(audio_path)))
            
            time.sleep(2)
        except Exception as e:
            print(f"[FATAL] Tác vụ thất bại: {e}")
            break

    print("\n[INFO] Hoàn thành toàn bộ quy trình!")

if __name__ == "__main__":
    main()

"""
Tên file: video_generator_tool.py
Mô tả: Công cụ tự động tạo kịch bản video bằng Gemini API (với cơ chế xoay vòng nhiều tài khoản/key)
       kết hợp tạo giọng đọc tự động (Edge-TTS) và xử lý file trên GitHub Actions.
"""

import os
import time
import asyncio
from pathlib import Path
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

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
        """Chuyển sang key tiếp theo khi key hiện tại hết hạn mức."""
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Key hiện tại đã chạm giới hạn (Quota). Đang chuyển sang Key thứ {self.current_index + 1}...")
        self._init_client()

    def generate_content_with_fallback(self, prompt: str):
        """Gọi API với cơ chế tự động chuyển key khi gặp lỗi quota."""
        total_keys = len(self.api_keys)
        checked_keys = 0

        while checked_keys < total_keys:
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                # Bắt các mã lỗi giới hạn hạn mức phổ biến từ Google API
                if any(err in error_str for err in ["429", "quota", "resourceexhausted", "exhausted", "limit"]):
                    print(f"[WARN] Key {self.current_index + 1} gặp lỗi hạn mức: {e}")
                    self.rotate_key()
                    checked_keys += 1
                    time.sleep(3) # Chờ ngắn trước khi thử key tiếp theo
                else:
                    print(f"[ERROR] Lỗi phát sinh không do quota ở Key {self.current_index + 1}: {e}")
                    raise e
        
        raise Exception("[CRITICAL] Tất cả các tài khoản Google API trong Pool đều đã hết hạn mức!")

async def generate_voiceover(text: str, output_audio_path: str):
    """Sử dụng edge-tts để tạo file âm thanh tiếng Việt từ kịch bản."""
    import edge_tts
    # Chọn giọng đọc tiếng Việt chuẩn (ví dụ: vi-VN-HoaiMyNeural hoặc vi-VN-NamMinhNeural)
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def main():
    # 1. Lấy danh sách key từ biến môi trường GitHub Secrets
    keys_env = os.getenv("GEMINI_KEYS", "")
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    if not api_keys:
        print("[ERROR] Không tìm thấy biến môi trường GEMINI_KEYS!")
        return

    # 2. Khởi tạo Pool quản lý key
    pool = GeminiKeyPool(api_keys=api_keys, model_name="gemini-2.5-flash")

    # 3. Danh sách tác vụ tạo nội dung video tuần tự
    tasks = [
        "Viết kịch bản ngắn 30s TikTok: Bí quyết tối ưu hóa quy trình sản xuất tinh gọn.",
        "Viết kịch bản ngắn 30s TikTok: 3 sai lầm phổ biến khi quản lý chuỗi cung ứng.",
        "Viết kịch bản ngắn 30s TikTok: Ứng dụng tự động hóa bằng AI trong doanh nghiệp."
    ]

    # Tạo thư mục lưu kết quả đầu ra
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, task in enumerate(tasks, 1):
        print(f"\n======================================")
        print(f"Đang xử lý tác vụ {idx}/{len(tasks)}")
        print(f"======================================")
        try:
            # Sinh kịch bản qua Gemini Pool
            script_text = pool.generate_content_with_fallback(task)
            
            # Lưu kịch bản thành file text
            script_path = output_dir / f"script_video_{idx}.txt"
            script_path.write_text(script_text, encoding="utf-8")
            print(f"[SUCCESS] Đã lưu kịch bản vào: {script_path}")
            
            # Tạo file audio giọng đọc tương ứng
            audio_path = output_dir / f"voice_{idx}.mp3"
            asyncio.run(generate_voiceover(script_text, str(audio_path)))
            
            # Nghỉ ngơi nhẹ giữa các request để tránh quá tải tốc độ gọi
            time.sleep(2)
        except Exception as e:
            print(f"[FATAL] Tác vụ {idx} thất bại: {e}")
            break

    print("\n[INFO] Hoàn thành toàn bộ quy trình sinh kịch bản và giọng đọc tự động!")

if __name__ == "__main__":
    main()

"""
Tên file: video_generator_tool.py
Mô tả: Công cụ render video AI thực sự bằng Google GenAI Video Generation.
       - Đọc trực tiếp kịch bản và Prompt (hình ảnh/bối cảnh) từ file Excel.
       - Render video có hình ảnh động AI (chứ không phải khung đen).
       - Sinh giọng đọc lồng vào video.
"""

import os
import time
import asyncio
from pathlib import Path
import pandas as pd
from google import genai
from google.genai import types
from PIL import Image
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

class GeminiVideoAI:
    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("Danh sách API Key không được để trống!")
        self.api_keys = api_keys
        self.current_index = 0
        self._init_client()

    def _init_client(self):
        current_key = self.api_keys[self.current_index]
        self.client = genai.Client(api_key=current_key)
        # Sử dụng model sinh video của Google (Veo 2.0 hoặc model video tương đương)
        self.video_model_name = "veo-2.0-generate-video-001" 
        print(f"[INFO] Đang sử dụng Tài khoản / API Key thứ {self.current_index + 1}/{len(self.api_keys)}")

    def rotate_key(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        print(f"[WARNING] Đang chuyển sang Key thứ {self.current_index + 1}...")
        self._init_client()

    def generate_video(self, prompt_text: str, aspect_ratio: str, output_path: str):
        """Gọi API Google để generate video AI thực sự từ Text Prompt."""
        print(f"[INFO] Bắt đầu render AI Video từ Google với Prompt: '{prompt_text[:50]}...'")
        total_keys = len(self.api_keys)
        checked_keys = 0

        # Chuyển đổi định dạng khung hình theo chuẩn API (16:9 hoặc 9:16)
        ratio_api = "16:9" if aspect_ratio == "16:9" else "9:16"

        while checked_keys < total_keys:
            try:
                # Gọi API sinh video trực tiếp của Gemini/Veo
                operation = self.client.models.generate_videos(
                    model=self.video_model_name,
                    prompt=prompt_text,
                    config=types.GenerateVideosConfig(
                        aspect_ratio=ratio_api,
                        person_generation="ALLOW_ADULT"
                    )
                )
                
                print("[INFO] Đang chờ Google render video (có thể mất 1-3 phút)...")
                # Chờ cho đến khi render xong trên server
                while not operation.done:
                    time.sleep(10)
                    operation.reload()

                if operation.error:
                    raise Exception(f"Lỗi API: {operation.error.message}")
                
                # Tải video mp4 về máy
                video_bytes = operation.response.generated_videos[0].video.video_bytes
                with open(output_path, "wb") as f:
                    f.write(video_bytes)
                print(f"[SUCCESS] Đã tải AI Video về máy thành công: {output_path}")
                return True

            except Exception as e:
                print(f"[WARN] Key {self.current_index + 1} gặp lỗi render video: {e}")
                self.rotate_key()
                checked_keys += 1
                time.sleep(3)
        
        raise Exception("[CRITICAL] Không thể render video, tất cả API Key đều báo lỗi!")

async def generate_voiceover(text: str, output_audio_path: str):
    """Sử dụng edge-tts để tạo file giọng đọc."""
    import edge_tts
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def merge_video_audio(video_path: str, audio_path: str, final_output_path: str):
    """Ghép video AI vừa sinh ra với giọng đọc."""
    print(f"[INFO] Bắt đầu ghép Video AI với Giọng đọc...")
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)
        
        # Gán âm thanh vào video (Cắt bằng chiều dài của video hoặc audio tùy ý)
        final_clip = video_clip.set_audio(audio_clip)

        final_clip.write_videofile(
            final_output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            logger=None
        )
        
        audio_clip.close()
        video_clip.close()
        final_clip.close()
        print(f"[SUCCESS] Đã xuất video hoàn chỉnh cuối cùng: {final_output_path}")
    except Exception as e:
        print(f"[ERROR] Lỗi khi ghép video và audio: {e}")

def main():
    keys_env = os.getenv("GEMINI_KEYS", "")
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]

    if not api_keys:
        print("[ERROR] Không tìm thấy biến môi trường GEMINI_KEYS!")
        return

    ai_engine = GeminiVideoAI(api_keys=api_keys)

    input_filename = os.getenv("INPUT_FILENAME", "").strip()
    aspect_ratio = os.getenv("ASPECT_RATIO", "9:16").strip()

    tasks = []
    if input_filename:
        file_path = Path("inputs") / input_filename
        if not file_path.exists():
            file_path = Path(input_filename)

        if file_path.exists() and file_path.suffix.lower() == ".xlsx":
            print(f"[INFO] Đang đọc file Excel kịch bản AI: {file_path}")
            df = pd.read_excel(file_path)
            
            # Lặp qua từng dòng của file Excel
            for index, row in df.iterrows():
                # Lấy nội dung từ cột "Prompt gợi ý (AI)" để làm hình ảnh video
                prompt_col = [col for col in df.columns if "prompt" in str(col).lower()]
                voice_col = [col for col in df.columns if "lời thoại" in str(col).lower() or "giọng" in str(col).lower()]
                
                if prompt_col and voice_col:
                    video_prompt = str(row[prompt_col[0]]).strip()
                    voice_text = str(row[voice_col[0]]).strip()
                    
                    if video_prompt and video_prompt != "nan" and voice_text and voice_text != "nan":
                        tasks.append({"prompt": video_prompt, "voice": voice_text})
        else:
            print(f"[WARNING] Không tìm thấy file Excel {input_filename}")

    if not tasks:
        print("[INFO] Không có tác vụ hợp lệ, đang chạy tác vụ mặc định...")
        tasks = [{"prompt": "A beautiful Vietnamese woman in traditional Ao Dai walking in a green rice field, cinematic lighting.", "voice": "Xin chào các bạn, hôm nay mình đi thăm đồng lúa quê mình."}]

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, task in enumerate(tasks, 1):
        print(f"\n======================================")
        print(f"Đang render Cảnh {idx} (Khung hình: {aspect_ratio})")
        print(f"======================================")
        try:
            timestamp = int(time.time())
            
            # 1. Render Video AI không lời (Dùng Prompt)
            raw_video_path = str(output_dir / f"raw_video_{idx}_{timestamp}.mp4")
            ai_engine.generate_video(prompt_text=task["prompt"], aspect_ratio=aspect_ratio, output_path=raw_video_path)
            
            # 2. Tạo giọng đọc AI
            audio_path = str(output_dir / f"voice_{idx}_{timestamp}.mp3")
            asyncio.run(generate_voiceover(task["voice"], audio_path))
            
            # 3. Ghép Video AI với Audio lại thành một video lồng tiếng hoàn chỉnh
            final_video_path = str(output_dir / f"final_video_{idx}_{timestamp}.mp4")
            merge_video_audio(raw_video_path, audio_path, final_video_path)
            
            time.sleep(2)
        except Exception as e:
            print(f"[FATAL] Cảnh {idx} thất bại: {e}")
            break

    print("\n[INFO] Đã hoàn thành render tất cả các phân cảnh thành video thực sự!")

if __name__ == "__main__":
    main()

"""
Tên file: video_generator_tool.py
Mô tả: Tự động hóa render Video AI chân thực bằng Fal.ai API trên GitHub Actions:
       - Đọc kịch bản Excel (Prompt AI & Lời thoại).
       - Gọi Fal.ai (Mô hình HunyuanVideo / LTX-Video) render video chuyển động AI 5 giây.
       - Tạo giọng đọc lồng tiếng bằng Edge-TTS.
       - Ghép Video AI + Audio lại thành file MP4 hoàn chỉnh.
"""

import os
import time
import asyncio
from pathlib import Path
import pandas as pd
import requests
import fal_client
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

def render_fal_video(prompt_text: str, aspect_ratio: str, output_video_path: str) -> bool:
    """Gọi Fal.ai API để render ra file video AI chuyển động thực sự (.mp4)."""
    print(f"[INFO] Gửi Prompt sang Fal.ai: '{prompt_text[:60]}...'")
    try:
        ratio = "9:16" if aspect_ratio == "9:16" else "16:9"
        
        # Gọi mô hình sinh Video AI sắc nét HunyuanVideo trên Fal.ai
        result = fal_client.subscribe(
            "fal-ai/hunyuan-video",
            arguments={
                "prompt": prompt_text,
                "aspect_ratio": ratio,
                "num_frames": 129  # Khung thời lượng ~5 giây chuẩn
            }
        )
        
        video_url = result['video']['url']
        print(f"[INFO] Đã nhận được link video từ Fal.ai. Đang tải về...")
        
        response = requests.get(video_url)
        with open(output_video_path, "wb") as f:
            f.write(response.content)
            
        print(f"[SUCCESS] Đã tải thành công Video AI: {output_video_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Lỗi render video từ Fal.ai: {e}")
        return False

async def generate_voiceover(text: str, output_audio_path: str):
    """Sử dụng edge-tts tạo giọng đọc tiếng Việt."""
    import edge_tts
    voice = "vi-VN-HoaiMyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_audio_path)
    print(f"[SUCCESS] Đã tạo file giọng đọc: {output_audio_path}")

def merge_video_audio(video_path: str, audio_path: str, final_output_path: str):
    """Ghép Video AI vừa render với Giọng đọc MP3."""
    print(f"[INFO] Đang ghép Video AI với giọng đọc...")
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)
        
        try:
            final_clip = video_clip.with_audio(audio_clip)
        except AttributeError:
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
        print(f"[SUCCESS] ĐÃ XUẤT VIDEO HOÀN CHỈNH: {final_output_path}")
    except Exception as e:
        print(f"[ERROR] Lỗi ghép audio/video: {e}")

def main():
    fal_key = os.getenv("FAL_KEY", "").strip()
    if not fal_key:
        print("[ERROR] Không tìm thấy FAL_KEY trong môi trường/GitHub Secrets!")
        return

    os.environ["FAL_KEY"] = fal_key

    input_filename = os.getenv("INPUT_FILENAME", "kich_ban_nau_an_mien_tay_6ph.xlsx").strip()
    aspect_ratio = os.getenv("ASPECT_RATIO", "9:16").strip()

    file_path = Path("inputs") / input_filename
    if not file_path.exists():
        file_path = Path(input_filename)

    if not file_path.exists():
        print(f"[ERROR] Không tìm thấy file kịch bản: {input_filename}")
        return

    print(f"[INFO] Đang đọc file Excel kịch bản: {file_path}")
    df = pd.read_excel(file_path)

    prompt_col = [col for col in df.columns if "prompt" in str(col).lower()]
    voice_col = [col for col in df.columns if "lời thoại" in str(col).lower() or "giọng" in str(col).lower()]

    if not prompt_col or not voice_col:
        print("[ERROR] File Excel cần chứa cột 'Prompt gợi ý (AI)' và 'Lời thoại (Giọng miền Tây)'")
        return

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for idx, row in df.iterrows():
        prompt = str(row[prompt_col[0]]).strip()
        voice = str(row[voice_col[0]]).strip()

        if prompt and prompt != "nan" and voice and voice != "nan":
            print(f"\n======================================")
            print(f"Đang xử lý Phân đoạn {idx + 1}")
            print(f"======================================")
            timestamp = int(time.time())
            
            # 1. Render Video AI chuyển động từ Fal.ai
            raw_video_path = str(output_dir / f"raw_video_scene_{idx + 1}_{timestamp}.mp4")
            render_success = render_fal_video(prompt, aspect_ratio, raw_video_path)
            
            if render_success:
                # 2. Sinh giọng đọc lồng tiếng MP3
                audio_path = str(output_dir / f"voice_scene_{idx + 1}_{timestamp}.mp3")
                asyncio.run(generate_voiceover(voice, audio_path))
                
                # 3. Ghép thành Video hoàn chỉnh
                final_video_path = str(output_dir / f"final_video_scene_{idx + 1}_{timestamp}.mp4")
                merge_video_audio(raw_video_path, audio_path, final_video_path)

    print("\n[INFO] Đã hoàn thành render toàn bộ các phân cảnh thành video MP4 sống động!")

if __name__ == "__main__":
    main()

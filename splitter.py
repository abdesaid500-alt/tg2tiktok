import os
import re
import logging
import subprocess
import shutil
from config import TEMP_DIR

logger = logging.getLogger("splitter")


def _get_ffmpeg():
    try:
        from static_ffmpeg import run_static_ffmpeg, run_static_ffprobe
        return run_static_ffmpeg, run_static_ffprobe
    except ImportError:
        pass
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return lambda args, **kw: subprocess.run(
            [ffmpeg] + args, **kw
        ), lambda args, **kw: subprocess.run(
            [ffprobe] + args, **kw
        )
    raise RuntimeError("ffmpeg/ffprobe غير موجودين. ثبّت static-ffmpeg أو ffmpeg.")


ffmpeg_run, ffprobe_run = None, None


def _ensure_ffmpeg():
    global ffmpeg_run, ffprobe_run
    if ffmpeg_run is None:
        ffmpeg_run, ffprobe_run = _get_ffmpeg()


def get_duration(file_path):
    _ensure_ffmpeg()
    try:
        result = ffprobe_run([
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ], capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"فشل الحصول على المدة: {e}")
        return 0


def split_video(input_path, video_id, speed, segment_seconds, video_title, user_id):
    _ensure_ffmpeg()
    os.makedirs(TEMP_DIR, exist_ok=True)
    duration = get_duration(input_path)
    if duration <= 0:
        logger.error("مدة الفيديو غير صالحة")
        return []
    seg_dir = os.path.join(TEMP_DIR, f"{video_id}_parts")
    os.makedirs(seg_dir, exist_ok=True)
    logger.info(f"مدة الفيديو: {duration:.0f} ثانية، السرعة: {speed}x, المقطع: {segment_seconds} ث")
    input_segment = int(segment_seconds * speed)
    overlap = 5
    parts = []
    current_start = 0
    part_num = 1
    while current_start < duration:
        part_file = os.path.join(seg_dir, f"part_{part_num:03d}.mp4")
        end_time = min(current_start + input_segment, duration)
        actual_duration = end_time - current_start
        if actual_duration < 1:
            break
        output_duration = actual_duration / speed
        if part_num > 1 and output_duration < 30:
            logger.info(f"آخر جزء ({output_duration:.0f}) أقل من 30 ثانية، يُدمج مع السابق")
            break
        fps_filter = f"setpts={1/speed}*PTS"
        atempo_filter = f"atempo={speed}"
        safe_title = re.sub(r'[^\w\s-]', '', video_title)[:80]
        caption = f"{safe_title} | الجزء {part_num}"
        cmd = [
            "-y",
            "-ss", str(current_start),
            "-i", input_path,
            "-t", str(actual_duration),
            "-vf", fps_filter,
            "-af", atempo_filter,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "22",
            part_file,
        ]
        try:
            result = ffmpeg_run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.error(f"فشل تقطيع الجزء {part_num}: {result.stderr}")
                break
        except Exception as e:
            logger.error(f"خطأ في تقطيع الجزء {part_num}: {e}")
            break
        if os.path.exists(part_file):
            file_size = os.path.getsize(part_file)
            if file_size > 1000:
                parts.append({
                    "part": part_num,
                    "total": 0,
                    "path": part_file,
                    "caption": caption,
                })
                logger.info(f"الجزء {part_num}: {file_size / 1024:.0f} كيلوبايت")
                part_num += 1
        current_start = end_time - overlap
    total = len(parts)
    for p in parts:
        p["total"] = total
    logger.info(f"تم التقطيع إلى {total} أجزاء")
    return parts

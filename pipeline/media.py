import os
import asyncio
import subprocess
import json
import logging
import shutil
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _init_ffmpeg() -> None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        logger.info("static-ffmpeg initialized")
    except Exception as e:
        logger.warning("static-ffmpeg not available: %s", e)


_init_ffmpeg()


def _find_font() -> Optional[str]:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# Called only when video is split into multiple parts (total_dur >= min_part_seconds).
# The "Part N" text appears for the first 5 seconds of each part only.
def _make_text_overlay(output_dir: str, part_idx: int) -> str:
    path = os.path.join(output_dir, f"overlay_{part_idx:03d}.png")
    img = Image.new("RGBA", (1080, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_path = _find_font()
    font_size = 56
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()
    text = f"Part {part_idx}"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (1080 - tw) // 2
    y = (140 - th) // 2
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    img.save(path)
    return path


async def download_video(
    url: str,
    output_dir: str,
    cookies_b64: str,
    po_token: Optional[str] = None,
    visitor_data: Optional[str] = None,
) -> dict:
    loop = asyncio.get_running_loop()

    def _run() -> dict:
        import base64
        cookies_file = os.path.join(output_dir, "cookies.txt")
        if cookies_b64:
            padding = "=" * (-len(cookies_b64) % 4)
            raw = base64.b64decode(cookies_b64 + padding)
            with open(cookies_file, "wb") as f:
                f.write(raw)

        output_template = os.path.join(output_dir, "%(title).80s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--force-ipv4",
            "--no-playlist",
            "--print", "after_move:%(title)s",
            "--print", "after_move:%(duration)s",
            "--print", "after_move:%(filename)s",
            "-o", output_template,
        ]
        if cookies_b64:
            cmd.extend(["--cookies", cookies_file])
        extractor_args = "youtube:player_client=ios,android,mweb"
        if po_token:
            extractor_args += f";po_token={po_token}"
        if visitor_data:
            extractor_args += f";visitor_data={visitor_data}"
        cmd.extend(["--extractor-args", extractor_args])
        cmd.append(url)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            err = result.stderr.strip()
            if any(k in err.lower() for k in ["cookie", "sign in", "403", "bot"]):
                raise PermissionError("COOKIES_EXPIRED")
            raise RuntimeError(f"yt-dlp failed: {err[-300:]}")

        lines = result.stdout.strip().split("\n")
        title = lines[0] if len(lines) > 0 else "Unknown"
        duration = 0.0
        if len(lines) > 1:
            try:
                duration = float(lines[1]) if lines[1] not in ("NA", "") else 0.0
            except (ValueError, TypeError):
                duration = 0.0
        fname = lines[2] if len(lines) > 2 else ""

        if not fname or not os.path.exists(fname):
            for f in os.listdir(output_dir):
                if f.endswith((".mp4", ".mkv", ".webm")):
                    fname = os.path.join(output_dir, f)
                    break

        return {"title": title, "duration": duration, "path": fname}

    try:
        return await loop.run_in_executor(None, _run)
    except PermissionError:
        raise
    except subprocess.TimeoutExpired:
        raise RuntimeError("Download timed out")
    except Exception as e:
        raise RuntimeError(str(e))


def _verify_video(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        return False
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0 and "video" in result.stdout


async def split_and_speed(
    input_path: str,
    output_dir: str,
    split_minutes: int,
    speed: float,
    overlap: int = 5,
    min_part_seconds: int = 30,
) -> list:
    loop = asyncio.get_running_loop()

    def _run() -> list:
        if not _verify_video(input_path):
            raise RuntimeError(
                "ملف الفيديو تالف أو غير مكتمل.\nحاول إرسال الرابط مجدداً."
            )

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", input_path],
            capture_output=True, text=True, timeout=30,
        )
        info = {}
        try:
            info = json.loads(probe.stdout) if probe.stdout.strip() else {}
        except json.JSONDecodeError:
            pass

        total_dur = 0.0
        fmt = info.get("format", {})
        if "duration" in fmt:
            total_dur = float(fmt["duration"])
        else:
            for s in info.get("streams", []):
                if s.get("codec_type") == "video" and "duration" in s:
                    total_dur = max(total_dur, float(s["duration"]))
        if total_dur <= 0:
            total_dur = _get_duration(input_path)

        has_audio = any(
            s.get("codec_type") == "audio" for s in info.get("streams", [])
        )

        if total_dur < min_part_seconds:
            out = os.path.join(output_dir, "part_001.mp4")
            _run_ffmpeg(input_path, out, speed, has_audio, 0, total_dur)
            return [out]

        chunk = split_minutes * 60
        parts = []
        start = 0.0
        idx = 1

        while start < total_dur:
            dur = chunk
            if start + dur > total_dur:
                dur = total_dur - start

            part_file = os.path.join(output_dir, f"part_{idx:03d}.mp4")
            overlay_img = _make_text_overlay(output_dir, idx)
            t0 = time.time()
            _run_ffmpeg(input_path, part_file, speed, has_audio, start, dur, text_overlay=overlay_img)
            elapsed = time.time() - t0
            logger.info("Part %03d done in %.1fs (start=%.1f dur=%.1f)", idx, elapsed, start, dur)

            actual = _get_duration(part_file)
            if actual < min_part_seconds and parts:
                os.remove(part_file)
            else:
                parts.append(part_file)

            start += chunk - overlap
            idx += 1

        return parts

    return await loop.run_in_executor(None, _run)


def _run_ffmpeg(
    input_path: str, output_path: str,
    speed: float, has_audio: bool,
    ss: float, t: float,
    text_overlay: Optional[str] = None,
) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(ss),
        "-i", input_path,
    ]
    if text_overlay:
        cmd.extend(["-i", text_overlay])

    if text_overlay:
        vf = (
            f"[0:v]setpts={1/speed}*PTS,"
            f"scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[base];"
            f"[base][1:v]overlay=(W-w)/2:280:enable='between(t,0,5)'[outv]"
        )
        ac = f"[0:a]atempo={speed}[outa]" if has_audio else ""
        if ac:
            cmd.extend(["-filter_complex", f"{vf};{ac}", "-map", "[outv]", "-map", "[outa]"])
        else:
            cmd.extend(["-filter_complex", vf, "-map", "[outv]"])
        cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
    else:
        cmd.extend([
            "-vf",
            f"setpts={1/speed}*PTS,"
            f"scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        ])
        if has_audio:
            cmd.extend(["-af", f"atempo={speed}"])

    cmd.extend([
        "-t", str(t),
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_path,
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[:1500]}")
    actual_dur = _get_duration(output_path)
    logger.info("FFmpeg output duration: %.2fs (expected ~%.2fs)", actual_dur, t / speed)


def _get_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        info = json.loads(r.stdout) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        info = {}
    fmt = info.get("format", {})
    if "duration" in fmt:
        return float(fmt["duration"])
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and "duration" in s:
            return float(s["duration"])
    return 0.0


async def create_bumper(output_dir: str) -> str:
    loop = asyncio.get_running_loop()

    def _run() -> str:
        path = os.path.join(output_dir, "_bumper.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "color=c=black:s=1080x1920:d=3",
             "-c:v", "libx264", "-preset", "ultrafast", path],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return path

    return await loop.run_in_executor(None, _run)


async def cleanup_temp(temp_dir: str, age_seconds: int = 3600) -> None:
    loop = asyncio.get_running_loop()

    def _run():
        now = time.time()
        try:
            for entry in os.listdir(temp_dir):
                fpath = os.path.join(temp_dir, entry)
                try:
                    if now - os.path.getmtime(fpath) > age_seconds:
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                        elif os.path.isdir(fpath):
                            shutil.rmtree(fpath, ignore_errors=True)
                except Exception:
                    pass
        except Exception:
            pass

    await loop.run_in_executor(None, _run)

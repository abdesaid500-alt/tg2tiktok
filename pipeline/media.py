import os
import asyncio
import subprocess
import json
import logging
import shutil
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _init_ffmpeg() -> None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        logger.info("static-ffmpeg initialized")
    except Exception as e:
        logger.warning("static-ffmpeg not available: %s", e)


_init_ffmpeg()


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
            "-o", output_template,
            "--print", "after_move:%(title)s|%(duration)s|%(filename)s",
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

        out = result.stdout.strip().split("\n")[0].strip()
        parts = out.split("|")
        title = parts[0] if len(parts) > 0 else "Unknown"
        duration = float(parts[1]) if len(parts) > 1 and parts[1] != "NA" else 0
        fname = parts[2] if len(parts) > 2 else ""

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
        info = json.loads(probe.stdout)
        total_dur = float(info["format"]["duration"])
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
            dur = chunk + overlap
            if start + dur > total_dur:
                dur = total_dur - start

            part_file = os.path.join(output_dir, f"part_{idx:03d}.mp4")
            _run_ffmpeg(input_path, part_file, speed, has_audio, start, dur)

            actual = _get_duration(part_file)
            if actual < min_part_seconds and parts:
                os.remove(part_file)
            else:
                parts.append(part_file)

            start += chunk
            idx += 1

        return parts

    return await loop.run_in_executor(None, _run)


def _run_ffmpeg(
    input_path: str, output_path: str,
    speed: float, has_audio: bool,
    ss: float, t: float,
) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(ss),
        "-t", str(t),
        "-vf",
        f"setpts={1/speed}*PTS,"
        f"scale=360:360:force_original_aspect_ratio=increase,"
        f"scale=min(1080\\,iw):min(1920\\,ih)"
        f":force_original_aspect_ratio=decrease,setsar=1",
        "-avoid_negative_ts", "make_zero",
    ]
    if has_audio:
        cmd.extend(["-af", f"atempo={speed}"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        output_path,
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-300:]}")


def _get_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, timeout=30,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


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

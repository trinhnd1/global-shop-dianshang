"""SSRF-guarded media helper + FFmpeg 4-frame keyframe extraction & <=15s video segment slicer."""
import base64
import hashlib
from pathlib import Path
import shutil
import subprocess
import urllib.request

from ..responses import is_public_http_url

MAX_DOWNLOAD_BYTES = 45 * 1024 * 1024


def ffmpeg_status() -> dict:
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    return {"ffmpeg_available": bool(ff), "ffprobe_available": bool(fp), "ffmpeg_path": ff or ""}


def download_public_video(url: str, dest_path: Path, timeout: int = 35) -> Path:
    if not is_public_http_url(url):
        raise ValueError("URL media không hợp lệ hoặc bị chặn bởi bộ lọc SSRF")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
    )
    total = 0
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest_path.open("wb") as out:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise OverflowError("Dung lượng video vượt giới hạn an toàn 45MB")
            out.write(chunk)
    return dest_path


def probe_duration_sec(video_path: Path) -> float:
    fp = shutil.which("ffprobe")
    if not fp or not video_path.is_file():
        return 15.0
    try:
        proc = subprocess.run(
            [fp, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return max(1.0, float(proc.stdout.strip() or 15.0))
    except Exception:
        return 15.0


def extract_4_keyframes(video_path: Path, media_dir: Path) -> tuple[list[str], dict[str, str]]:
    """Extract 4 normalized 640px JPEG frames (padded >=280px) at 6%, 28%, 60%, 88% of duration."""
    ff = shutil.which("ffmpeg")
    if not ff or not video_path.is_file():
        return [], {}
    media_dir.mkdir(parents=True, exist_ok=True)
    dur = probe_duration_sec(video_path)
    tag = hashlib.sha256(f"{video_path.name}:{video_path.stat().st_size}".encode("utf-8")).hexdigest()[:12]
    filenames: list[str] = []
    assets_b64: dict[str, str] = {}
    vf = "scale='min(640,iw)':-2,pad='max(280,iw)':'max(280,ih)':(ow-iw)/2:(oh-ih)/2"

    for idx, ratio in enumerate((0.06, 0.28, 0.60, 0.88)):
        ts = max(0.0, round(dur * ratio, 2))
        fname = f"{tag}_f{idx}.jpg"
        out_file = media_dir / fname
        subprocess.run(
            [ff, "-y", "-ss", str(ts), "-i", str(video_path), "-frames:v", "1", "-vf", vf, "-q:v", "5", str(out_file)],
            capture_output=True,
            timeout=15,
        )
        if out_file.is_file() and out_file.stat().st_size > 0:
            filenames.append(fname)
            b64 = base64.b64encode(out_file.read_bytes()).decode("ascii")
            assets_b64[f"frame_{idx}"] = f"data:image/jpeg;base64,{b64}"
    return filenames, assets_b64


def slice_15s_segments(video_path: Path, out_dir: Path, max_seg_sec: float = 15.0) -> list[dict]:
    """Slice source video into physical <=15.0s MP4 reference segments + keyframe per segment."""
    dur = probe_duration_sec(video_path)
    step = max(5.0, min(15.0, float(max_seg_sec)))
    ff = shutil.which("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)

    bounds: list[tuple[float, float]] = []
    cur = 0.0
    while cur < dur - 0.2:
        nxt = min(dur, cur + step)
        if dur - nxt < 2.5:
            nxt = dur
        bounds.append((round(cur, 2), round(nxt, 2)))
        cur = nxt
    if not bounds:
        bounds = [(0.0, round(min(dur, 15.0), 2))]

    segments = []
    for idx, (s_sec, e_sec) in enumerate(bounds, start=1):
        seg_dur = round(max(1.0, e_sec - s_sec), 2)
        clip_name = f"seg_{idx:02d}.mp4"
        thumb_name = f"seg_{idx:02d}.jpg"
        if ff and video_path.is_file():
            subprocess.run(
                [ff, "-y", "-ss", str(s_sec), "-t", str(seg_dur), "-i", str(video_path), "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out_dir / clip_name)],
                capture_output=True,
                timeout=25,
            )
            subprocess.run(
                [ff, "-y", "-ss", str(round(s_sec + seg_dur * 0.25, 2)), "-i", str(video_path), "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", str(out_dir / thumb_name)],
                capture_output=True,
                timeout=12,
            )
        segments.append({
            "segment_index": idx,
            "start_sec": s_sec,
            "end_sec": e_sec,
            "duration_sec": seg_dur,
            "clip_file": clip_name if (out_dir / clip_name).is_file() else "",
            "thumb_file": thumb_name if (out_dir / thumb_name).is_file() else "",
        })
    return segments

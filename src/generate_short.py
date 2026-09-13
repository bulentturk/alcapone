#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont


API_BASE = "https://api.elevenlabs.io"
DEFAULT_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"
WIDTH = 1080
HEIGHT = 1920


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


def api_headers(api_key: str) -> dict[str, str]:
    return {"xi-api-key": api_key, "Content-Type": "application/json"}


def check_response(response: requests.Response, action: str) -> None:
    if response.ok:
        return
    hints = {
        400: "API key or request configuration was rejected.",
        401: "Check API key validity and TTS permission.",
        403: "Check TTS permission and voice availability.",
        404: "The approved voice may be unavailable.",
        422: "A speech-generation setting was rejected.",
        429: "Check ElevenLabs credits and rate limits.",
    }
    hint = hints.get(response.status_code, "The provider rejected the request.")
    raise RuntimeError(
        f"ElevenLabs {action} failed (HTTP {response.status_code}). {hint} No automatic retry."
    )


def resolve_voice(api_key: str, configured_voice_id: str | None) -> tuple[str, str]:
    if configured_voice_id:
        return configured_voice_id.strip(), "configured ELEVENLABS_VOICE_ID"
    return DEFAULT_VOICE_ID, "approved Roger voice"


def generate_speech(
    api_key: str, voice_id: str, script: str, output_path: Path
) -> dict:
    response = requests.post(
        f"{API_BASE}/v1/text-to-speech/{voice_id}/with-timestamps",
        headers=api_headers(api_key),
        params={"output_format": "mp3_44100_128"},
        json={
            "text": script,
            "model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.78,
                "style": 0.18,
                "use_speaker_boost": True,
            },
        },
        timeout=120,
    )
    check_response(response, "speech generation")
    payload = response.json()
    output_path.write_bytes(base64.b64decode(payload["audio_base64"]))
    return payload.get("normalized_alignment") or payload.get("alignment") or {}


def words_from_alignment(alignment: dict) -> list[tuple[str, float, float]]:
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    if not chars or not (len(chars) == len(starts) == len(ends)):
        return []

    full_text = "".join(chars)
    words: list[tuple[str, float, float]] = []
    for match in re.finditer(r"\S+", full_text):
        first = match.start()
        last = match.end() - 1
        words.append((match.group(), float(starts[first]), float(ends[last])))
    return words


def captions_from_alignment(alignment: dict) -> list[Caption]:
    words = words_from_alignment(alignment)
    if not words:
        return []

    captions: list[Caption] = []
    group: list[tuple[str, float, float]] = []
    for word in words:
        candidate = " ".join([item[0] for item in group] + [word[0]])
        if group and (len(group) >= 6 or len(candidate) > 36):
            captions.append(Caption(group[0][1], group[-1][2], " ".join(x[0] for x in group)))
            group = []
        group.append(word)
        if re.search(r"[.!?…:]$", word[0]) and len(group) >= 3:
            captions.append(Caption(group[0][1], group[-1][2], " ".join(x[0] for x in group)))
            group = []
    if group:
        captions.append(Caption(group[0][1], group[-1][2], " ".join(x[0] for x in group)))
    return captions


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def ass_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def write_ass(captions: list[Caption], path: Path) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,62,&H00FFFFFF,&H00009FFF,&H00101825,&HA0000000,-1,0,0,0,100,100,0,0,3,3,0,2,90,90,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for caption in captions:
        lines.append(
            "Dialogue: 0,"
            f"{ass_time(caption.start)},{ass_time(caption.end)},"
            f"Caption,,0,0,0,,{ass_escape(caption.text)}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / filename
    return ImageFont.truetype(str(path), size=size)


def fit_lines(draw: ImageDraw.ImageDraw, text: str, typeface: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=typeface)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:4]


def draw_background(title: str, source_url: str, output_path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#07111f")
    pixels = image.load()
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        for x in range(WIDTH):
            glow = max(0.0, 1 - math.dist((x, y), (840, 420)) / 1150)
            pixels[x, y] = (
                int(6 + 7 * glow),
                int(16 + 29 * glow + 3 * ratio),
                int(30 + 48 * glow + 8 * ratio),
            )

    draw = ImageDraw.Draw(image, "RGBA")
    for x in range(0, WIDTH, 90):
        draw.line((x, 0, x, HEIGHT), fill=(68, 145, 180, 22), width=1)
    for y in range(0, HEIGHT, 90):
        draw.line((0, y, WIDTH, y), fill=(68, 145, 180, 22), width=1)

    rng = random.Random(20260913)
    nodes = [(rng.randint(60, 1020), rng.randint(160, 1700)) for _ in range(34)]
    for index, (x1, y1) in enumerate(nodes):
        distances = sorted(
            ((math.dist((x1, y1), point), point) for point in nodes[index + 1 :]),
            key=lambda item: item[0],
        )
        for distance, (x2, y2) in distances[:2]:
            if distance < 300:
                draw.line((x1, y1, x2, y2), fill=(46, 196, 182, 35), width=2)
        draw.ellipse((x1 - 6, y1 - 6, x1 + 6, y1 + 6), fill=(255, 159, 28, 150))

    draw.rounded_rectangle((54, 72, 1026, 174), radius=36, fill=(11, 30, 50, 225), outline=(255, 159, 28, 190), width=3)
    draw.text((92, 101), "ALGO TEAM", font=font(40, True), fill=(255, 255, 255, 255))
    draw.text((405, 108), "ENGINEERING SHORTS", font=font(29, True), fill=(255, 159, 28, 255))

    title_font = font(76, True)
    lines = fit_lines(draw, title.upper(), title_font, 900)
    y = 300
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x + 4, y + 5), line, font=title_font, fill=(0, 0, 0, 135))
        draw.text((x, y), line, font=title_font, fill=(244, 248, 252, 255))
        y += 98
    draw.rounded_rectangle((390, y + 18, 690, y + 28), radius=5, fill=(255, 159, 28, 255))

    draw.text((90, 1065), "VOICE SIGNAL", font=font(25, True), fill=(87, 207, 197, 210))
    draw.rounded_rectangle((70, 1100, 1010, 1430), radius=34, fill=(5, 14, 27, 155), outline=(73, 207, 196, 90), width=2)

    host = urlparse(source_url).netloc or source_url
    footer = host[:50] if host else "algo-team.com"
    draw.text((70, 1810), footer, font=font(25), fill=(178, 193, 207, 210))
    draw.text((790, 1806), "#Engineering", font=font(25, True), fill=(255, 159, 28, 230))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=95)


def probe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def generate_offline_tone(script: str, audio_path: Path) -> dict:
    word_count = max(1, len(script.split()))
    duration = max(8.0, min(58.0, word_count / 2.45))
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=44100:duration={duration}",
            "-filter:a",
            "volume=0.035",
            "-q:a",
            "5",
            "-y",
            str(audio_path),
        ],
        check=True,
    )
    chars = list(script)
    step = duration / max(1, len(chars))
    return {
        "characters": chars,
        "character_start_times_seconds": [i * step for i in range(len(chars))],
        "character_end_times_seconds": [(i + 1) * step for i in range(len(chars))],
    }


def render_video(background: Path, audio: Path, subtitles: Path, output: Path) -> None:
    subtitle_filter = str(subtitles).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    filter_graph = (
        "[1:a]showwaves=s=860x250:mode=cline:colors=0xFF9F1C@0.92:rate=30,format=rgba[wave];"
        "[0:v][wave]overlay=(W-w)/2:1138:shortest=1[base];"
        f"[base]subtitles='{subtitle_filter}'[video]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(background),
            "-i",
            str(audio),
            "-filter_complex",
            filter_graph,
            "-map",
            "[video]",
            "-map",
            "1:a",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            "-y",
            str(output),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an ALGO TEAM engineering Short")
    parser.add_argument("--title", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--source-url", default="https://www.algo-team.com")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--offline-tone", action="store_true")
    args = parser.parse_args()

    title = " ".join(args.title.split())
    script = " ".join(args.script.split())
    if not 12 <= len(title) <= 120:
        raise ValueError("Title must be between 12 and 120 characters.")
    if not 80 <= len(script) <= 1200:
        raise ValueError("Script must be between 80 and 1200 characters.")

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "voiceover.mp3"
    background_path = output_dir / "background.png"
    subtitles_path = output_dir / "captions.ass"
    video_path = output_dir / "engineering-short.mp4"

    voice_note = "offline test tone"
    if args.offline_tone:
        alignment = generate_offline_tone(script, audio_path)
    else:
        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is missing.")
        voice_id, voice_note = resolve_voice(
            api_key, os.getenv("ELEVENLABS_VOICE_ID")
        )
        alignment = generate_speech(api_key, voice_id, script, audio_path)

    captions = captions_from_alignment(alignment)
    if not captions:
        duration = probe_duration(audio_path)
        words = script.split()
        chunk_size = 6
        chunks = [words[i : i + chunk_size] for i in range(0, len(words), chunk_size)]
        captions = [
            Caption(i * duration / len(chunks), (i + 1) * duration / len(chunks), " ".join(chunk))
            for i, chunk in enumerate(chunks)
        ]

    write_ass(captions, subtitles_path)
    draw_background(title, args.source_url, background_path)
    render_video(background_path, audio_path, subtitles_path, video_path)

    duration = probe_duration(audio_path)
    description = textwrap.dedent(
        f"""\
        {title}

        {script}

        Kaynak: {args.source_url}

        #muhendislik #engineering #madencilik #mining #teknoloji #shorts
        """
    )
    (output_dir / "youtube-description.txt").write_text(description, encoding="utf-8")
    metadata = {
        "title": title,
        "duration_seconds": round(duration, 2),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "voice_selection": voice_note,
        "source_url": args.source_url,
        "caption_count": len(captions),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

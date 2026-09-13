"""Generate and render the approved RevA episode. Secrets are used only for TTS."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata

from generate_short import generate_speech, probe_duration

ROOT = Path(__file__).resolve().parents[1]
EPISODE_FILE = ROOT / "episodes/pilot01-reva.json"


class PilotError(RuntimeError):
    """Fixed, safe messages that may be printed to Actions logs."""


def episode() -> dict:
    return json.loads(EPISODE_FILE.read_text(encoding="utf-8"))


def script_text(ep: dict) -> str:
    # Preserve the paragraph pauses in the approved ElevenLabs export.
    s = ep["sentences"]
    paragraphs = [s[0] + " " + s[1], s[2], s[3] + " " + s[4], s[5],
                  s[6] + " " + s[7], s[8], s[9] + " " + s[10], s[11], s[12]]
    return "\n\n".join(paragraphs)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical(text: str) -> str:
    # Ignore whitespace and Unicode presentation differences, never speech content.
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def timing_from_alignment(alignment: dict, ep: dict) -> list[dict]:
    try:
        chars = alignment["characters"]
        starts = alignment["character_start_times_seconds"]
        ends = alignment["character_end_times_seconds"]
        if not chars or not (len(chars) == len(starts) == len(ends)):
            raise ValueError()
        if not all(isinstance(c, str) and len(c) == 1 for c in chars):
            raise ValueError()
        times = [(float(a), float(b)) for a, b in zip(starts, ends)]
        if any(not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < a for a, b in times):
            raise ValueError()
        if any(a[0] > b[0] or a[1] > b[1] for a, b in zip(times, times[1:])):
            raise ValueError()
        mapping = []
        compact = []
        for i, char in enumerate(chars):
            for c in canonical(char):
                compact.append(c)
                mapping.append(i)
        if "".join(compact) != canonical(script_text(ep)):
            raise ValueError()
        cues = []
        offset = 0
        for sentence in ep["sentences"]:
            length = len(canonical(sentence))
            first, last = mapping[offset], mapping[offset + length - 1]
            cues.append({"start": times[first][0], "end": times[last][1], "text": sentence})
            offset += length
        return cues
    except (KeyError, TypeError, ValueError, IndexError):
        raise PilotError("Speech timing does not match the approved script; audio preserved, render stopped.") from None


def validate_timing(cues: list[dict], duration: float, ep: dict) -> None:
    try:
        if not math.isfinite(duration) or not 5 <= duration <= 90:
            raise ValueError()
        if len(cues) != 13 or [c["text"] for c in cues] != ep["sentences"]:
            raise ValueError()
        previous = 0.0
        for cue in cues:
            start, end = float(cue["start"]), float(cue["end"])
            if not (math.isfinite(start) and math.isfinite(end) and
                    previous <= start < end <= duration + 0.05):
                raise ValueError()
            previous = end
    except (TypeError, KeyError, ValueError):
        raise PilotError("Invalid or overlapping narration timing; render stopped.") from None


def verify_environment() -> None:
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            raise PilotError("FFmpeg and FFprobe are required before speech generation.")
    # Draw a real scene before spending credits: catches missing fonts and assets.
    import reva_scene as scene
    ep = episode()
    scene.configure_timeline(ep["reference"]["timing"], 50.808125)
    scene.frame(1.0)


def prepare_speech(output: Path, reference_audio: Path | None = None, offline: bool = False) -> None:
    ep = episode()
    output.mkdir(parents=True, exist_ok=True)
    marker = output / "speech-attempted.json"
    audio = output / "voiceover.mp3"
    if marker.exists() or audio.exists():
        raise PilotError("Speech already attempted in this directory. Render the saved package; do not pay again.")
    verify_environment()
    if reference_audio:
        if digest(reference_audio) != ep["reference"]["audio_sha256"]:
            raise PilotError("Reference audio checksum does not match RevA; fixed timings cannot be reused.")
        shutil.copyfile(reference_audio, audio)
        cues = ep["reference"]["timing"]
        mode = "approved_elevenlabs_reference"
    elif offline:
        # Deliberately synthetic; only used in CI. No provider call or secret read.
        duration = 9.1
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", f"sine=frequency=220:duration={duration}", "-af", "volume=0.035", str(audio)], check=True)
        cues = [{"start": i * .7, "end": i * .7 + .6, "text": s}
                for i, s in enumerate(ep["sentences"])]
        mode = "offline_test_tone"
    else:
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not key:
            raise PilotError("ELEVENLABS_API_KEY is missing; no request made.")
        voice = ep["voice"]
        # Exclusive marker precedes the only paid call, including timeout failures.
        with marker.open("x", encoding="utf-8") as f:
            json.dump({"episode": ep["id"], "automatic_retry": False}, f)
        try:
            alignment = generate_speech(key, voice["voice_id"], script_text(ep), audio,
                                        model_id=voice["model_id"], voice_settings=voice["voice_settings"])
        except Exception:
            raise PilotError("ElevenLabs generation failed. Check TTS permission, credits and connectivity. No automatic retry.") from None
        finally:
            key = ""
        cues = timing_from_alignment(alignment, ep)
        mode = "elevenlabs_api"
    duration = probe_duration(audio)
    validate_timing(cues, duration, ep)
    dump(output / "timing.json", cues)
    # An explicit allowlist: never serialize environment, request headers, or provider errors.
    dump(output / "speech.json", {"episode": ep["id"], "mode": mode, "voice": ep["voice"],
                                  "audio_sha256": digest(audio), "duration_seconds": duration,
                                  "script_sha256": hashlib.sha256(script_text(ep).encode()).hexdigest()})
    print(f"Speech prepared: {mode}, {duration:.2f} seconds.", flush=True)


def timecode(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{sec:02},{ms:03}"


def render(output: Path, preview_only: bool = False) -> None:
    from PIL import Image, ImageDraw
    import reva_scene as scene
    ep = episode()
    audio = output / "voiceover.mp3"
    info = json.loads((output / "speech.json").read_text())
    if info["audio_sha256"] != digest(audio):
        raise PilotError("Saved narration has changed; timing must be regenerated.")
    if info["script_sha256"] != hashlib.sha256(script_text(ep).encode()).hexdigest():
        raise PilotError("The script has changed; saved audio cannot be used.")
    cues = json.loads((output / "timing.json").read_text())
    duration = probe_duration(audio)
    validate_timing(cues, duration, ep)
    scene.configure_timeline(cues, duration)
    count = math.ceil((duration + 1.5) * scene.FPS)
    video_duration = count / scene.FPS
    qa = output / "qa"
    qa.mkdir(exist_ok=True)
    sample_times = [min(b - .12, a + (b - a) * .6) for a, b, _ in scene.SCENES] + [duration + .9]
    sheet = Image.new("RGB", (4 * 216, 2 * 410), "#09121d")
    for i, t in enumerate(sample_times):
        frame = scene.frame(t).convert("RGB")
        if i == 0:
            frame.save(output / "poster.jpg", quality=92)
        sheet.paste(frame.resize((216, 384)), ((i % 4) * 216, (i // 4) * 410))
        ImageDraw.Draw(sheet).text(((i % 4) * 216 + 8, (i // 4) * 410 + 389), f"{t:.2f} s", fill="white")
    sheet.save(qa / "contact-sheet.jpg", quality=93)
    captions = []
    for i, cue in enumerate(cues):
        end = min(cue["end"] + .16, cues[i+1]["start"] if i+1 < len(cues) else duration)
        captions.append(f"{i+1}\n{timecode(cue['start'])} --> {timecode(end)}\n" + "\n".join(scene.wrapped(cue["text"])) + "\n")
    (output / "captions.srt").write_text("\n".join(captions), encoding="utf-8")
    if preview_only:
        print("RevA preview frames prepared; no video or speech generation.")
        return
    silent = output / "silent.tmp.mp4"
    video = output / "engineering-short.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{scene.W}x{scene.H}", "-r", str(scene.FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p", str(silent)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(count):
            proc.stdin.write(scene.frame(i / scene.FPS).convert("RGB").tobytes())
            if i % 300 == 0:
                print(f"Render {i}/{count}", flush=True)
        proc.stdin.close()
        if proc.wait():
            raise PilotError("FFmpeg video rendering failed; narration is saved.")
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af",
                    f"loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=duration={video_duration}",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", str(video_duration),
                    "-movflags", "+faststart", str(video)], check=True)
    silent.unlink()
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                                     check=True, capture_output=True, text=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    if (v["width"], v["height"], v["codec_name"], a["codec_name"]) != (1080, 1920, "h264", "aac"):
        raise PilotError("Output format validation failed.")
    if abs(float(v["duration"]) - float(a["duration"])) > .08:
        raise PilotError("Output audio/video durations differ.")
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True)
    dump(qa / "probe.json", probe)
    metadata = {"title": ep["title"], "source_url": ep["source_url"], "style": "RevA original motion graphics",
                "narration_mode": info["mode"], "voice": info["voice"], "duration_seconds": video_duration,
                "resolution": "1080x1920", "fps": 30, "caption_count": len(cues), "scene_count": 6,
                "outro_seconds": 1.5, "decode_validation": "passed", "youtube_uploaded": False,
                "audio_sha256": info["audio_sha256"], "video_sha256": digest(video)}
    dump(output / "metadata.json", metadata)
    (output / "youtube-description.txt").write_text(
        ep["title"] + "\n\n" + script_text(ep) + "\n\nKaynak: " + ep["source_url"] +
        "\n\nGörseller temsili teknik animasyondur.\nhttps://www.algo-team.com\n\n"
        "#muhendislik #engineering #madencilik #mining #shorts\n", encoding="utf-8")
    print(f"Short complete: {video_duration:.2f} seconds, six RevA scenes, decode passed.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "render", "preflight"])
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reference-audio", type=Path)
    mode.add_argument("--offline-tone", action="store_true")
    parser.add_argument("--preview-only", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        verify_environment()
    elif args.command == "prepare":
        prepare_speech(args.output_dir, args.reference_audio, args.offline_tone)
    else:
        render(args.output_dir, args.preview_only)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("ERROR: Pipeline failed; inspect saved media and dependencies. No automatic retry.", file=sys.stderr)
        raise SystemExit(1) from None

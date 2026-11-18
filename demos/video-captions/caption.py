import argparse
import json
import math
import os
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
FFMPEG = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-protocol_whitelist", "file,pipe"]
FFPROBE = ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe"]


def probe(source):
    data = subprocess.check_output([*FFPROBE, "-show_format", "-show_streams",
                                    "-of", "json", str(source)])
    info = json.loads(data)
    video = next((track for track in info["streams"] if track["codec_type"] == "video"
                  and not track["disposition"]["attached_pic"]), None)
    audio = next((track for track in info["streams"] if track["codec_type"] == "audio"), None)
    if not video or not audio or audio["codec_name"] != "aac":
        raise ValueError("This demo needs a video track and AAC as the first audio track.")
    if video.get("color_transfer") in ("arib-std-b67", "smpte2084") or any(
        "DOVI" in side.get("side_data_type", "") for side in video.get("side_data_list", [])
    ):
        raise ValueError("Use SDR video. This demo does not tone-map HDR or Dolby Vision.")
    return info["format"], video, audio


def dimensions(video, limit):
    aspect = video.get("sample_aspect_ratio", "1:1")
    aspect = Fraction(aspect.replace(":", "/")) if aspect not in ("0:1", "N/A") else 1
    width, height = video["width"] * aspect, video["height"]
    rotation = next((side["rotation"] for side in video.get("side_data_list", []) if "rotation" in side), 0)
    if rotation % 90:
        raise ValueError("This demo supports right-angle display rotations.")
    if rotation % 180:
        width, height = height, width
    scale = min(1, limit / max(width, height)) if limit else 1
    return tuple(max(2, 2 * round(float(size * scale) / 2)) for size in (width, height))


def bitrate_for(source, audio, duration, byte_limit):
    packets = subprocess.check_output([*FFPROBE, "-select_streams", str(audio["index"]),
                                       "-show_entries", "packet=size", "-of", "json", str(source)])
    audio_bytes = sum(int(packet["size"]) for packet in json.loads(packets)["packets"])
    video_bytes = byte_limit * 0.975 - audio_bytes - 8192
    bitrate = int(video_bytes * 8 / duration / 1000)
    if bitrate < 1:
        raise ValueError("The byte budget is too small for the copied audio and MP4 container.")
    return bitrate


def encode(source, target, directory, video, audio, layout, size, manifest, limit, duration):
    width, height = size
    y_position = height - layout.margin - layout.plate_height
    filters = (f"[0:{video['index']}]scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p10le[base];"
               f"[base][1:v]overlay=x=0:y={y_position}:format=yuv420p10:alpha=straight:eof_action=pass[out]")
    inputs = [*FFMPEG, "-i", source, "-f", "concat", "-safe", "0", "-i", manifest,
              "-filter_complex", filters, "-map", "[out]", "-c:v", "libx265", "-preset", "medium",
              "-pix_fmt", "yuv420p10le", "-fps_mode:v", "passthrough", "-enc_time_base:v", video["time_base"]]
    params = "log-level=error:info=0"
    rate = ["-crf", "21"]
    if limit is not None:
        bitrate = bitrate_for(source, audio, duration, limit)
        rate = ["-b:v", f"{bitrate}k"]
        subprocess.run([*inputs, *rate, "-x265-params", params + ":pass=1:stats=pass.log",
                        "-an", "-f", "null", "-"], cwd=directory, check=True)
        params += ":pass=2:stats=pass.log"
    subprocess.run([*inputs, *rate, "-x265-params", params, "-map", f"0:{audio['index']}", "-c:a", "copy",
                    "-map_metadata", "-1", "-map_metadata:s", "-1", "-map_chapters", "-1", "-write_tmcd", "0",
                    "-tag:v", "hvc1", "-video_track_timescale", str(Fraction(video["time_base"]).denominator),
                    "-movflags", "+faststart", target], cwd=directory, check=True)
    if limit is not None and target.stat().st_size > limit:
        raise ValueError("The two-pass result exceeded the byte cap. Use a smaller long edge or more room.")


def main():
    parser = argparse.ArgumentParser(description="Burn Mandarin captions into a new SDR H.265 MP4.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cues", type=Path, help="burn edited JSON cues and skip recognition")
    parser.add_argument("--font", type=Path, help="CJK TrueType, OpenType or collection font file")
    parser.add_argument("--long-edge", type=int, help="maximum display dimension in pixels (even)")
    parser.add_argument("--max-mb", type=float, help="decimal MB cap, using two-pass x265")
    args = parser.parse_args()
    if args.long_edge is not None and (args.long_edge < 2 or args.long_edge % 2):
        parser.error("--long-edge must be a positive even number")
    if args.max_mb is not None and (not math.isfinite(args.max_mb) or args.max_mb <= 0):
        parser.error("--max-mb must be finite and positive")
    try:
        from timeline import CaptionLayout, make_draft, plates
    except ModuleNotFoundError as error:
        if error.name != "PIL":
            raise
        parser.exit(1, "Pillow is missing. Install demos/video-captions/requirements.txt in a Python venv.\n")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            parser.exit(1, f"Install {tool} with libx265 support.\n")

    source, output = args.input.resolve(strict=True), args.output.resolve()
    draft = output.with_suffix(".cues.json")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output must be an MP4 path.")
    if output.exists() or (not args.cues and draft.exists()):
        raise ValueError("Choose a new output name. The MP4 or its generated cues already exist.")
    format_info, video, audio = probe(source)
    duration = float(format_info["duration"])
    size = dimensions(video, args.long_edge)
    layout = CaptionLayout(*size, args.font)
    with tempfile.TemporaryDirectory(prefix=".captions-", dir=output.parent) as job:
        directory = Path(job)
        if args.cues:
            cues = json.loads(args.cues.read_text(encoding="utf-8"))
        else:
            bridge = subprocess.check_output([ROOT / "scripts/build-swift", "file"], text=True).strip()
            wav = directory / "speech.wav"
            subprocess.run([*FFMPEG, "-i", source, "-map", f"0:{audio['index']}", "-ar", "16000",
                            "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
            phrases = json.loads(subprocess.check_output([bridge, wav]))
            offset = float(audio.get("start_time", 0)) - float(format_info.get("start_time", 0))
            cues = make_draft(phrases, layout, offset, duration)
            (directory / "draft.json").write_text(json.dumps(cues, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")

        manifest = plates(cues, layout, duration, directory)
        result = directory / "captioned.mp4"
        limit = None if args.max_mb is None else int(args.max_mb * 1_000_000)
        encode(source, result, directory, video, audio, layout, size, manifest, limit, duration)
        os.link(result, output)
        if not args.cues:
            try:
                os.link(directory / "draft.json", draft)
            except OSError:
                output.unlink()
                raise
    print(f"{len(cues)} cues · {size[0]} × {size[1]} · {output.stat().st_size:,} bytes")
    if not args.cues:
        print(f"Editable cues: {draft.name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))

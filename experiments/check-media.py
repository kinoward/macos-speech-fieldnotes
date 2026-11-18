"""Compare presentation times and the copied AAC payload, then decode the entire output."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess


def probe(path, *arguments):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                                              *arguments, "-of", "json", path.resolve(strict=True)]))


def times(path):
    info = probe(path, "-select_streams", "V:0", "-show_frames", "-show_entries",
                 "frame=best_effort_timestamp:stream=time_base:format=start_time")
    base = Fraction(info["streams"][0]["time_base"])
    origin = Fraction(info["format"].get("start_time", "0"))
    return [int(frame["best_effort_timestamp"]) * base - origin for frame in info["frames"]]


def audio_hash(path):
    return subprocess.check_output(["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                                    "-i", path.resolve(strict=True), "-map", "0:a:0",
                                    "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-mb", type=float)
    args = parser.parse_args()
    tracks = probe(args.output, "-show_streams")["streams"]
    if [track["codec_name"] for track in tracks] != ["hevc", "aac"] or tracks[0]["pix_fmt"] != "yuv420p10le":
        parser.exit(1, "Expected an HEVC 10-bit video track and a single AAC track.\n")
    if args.max_mb is not None and args.output.stat().st_size > args.max_mb * 1_000_000:
        parser.exit(1, "Output exceeds the decimal MB cap.\n")
    source_times = times(args.input)
    if not source_times or source_times != times(args.output):
        parser.exit(1, "Video frame count or presentation timestamps differ.\n")
    original_audio = probe(args.input, "-select_streams", "a:0", "-show_streams")["streams"][0]
    if any(original_audio[key] != tracks[1][key] for key in ("sample_rate", "channels")):
        parser.exit(1, "Audio format differs.\n")
    if audio_hash(args.input) != audio_hash(args.output):
        parser.exit(1, "AAC packet payload differs.\n")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-protocol_whitelist", "file,pipe",
                    "-i", args.output.resolve(strict=True), "-f", "null", "-"],
                   check=True)
    print(f"{len(source_times)} matching frame times · {tracks[0]['width']} × {tracks[0]['height']} · "
          f"{tracks[1]['sample_rate']} Hz · matching AAC payload · full decode OK · "
          f"{args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

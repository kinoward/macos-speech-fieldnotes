"""Compare presentation times and the copied AAC payload, then decode the entire output."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess


def probe(path, *arguments):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                                              *arguments, "-of", "json", path.resolve(strict=True)]))


def times(path, selector):
    info = probe(path, "-select_streams", selector, "-show_frames", "-show_entries",
                 "frame=best_effort_timestamp,nb_samples:stream=time_base,sample_rate:format=start_time")
    stream = info["streams"][0]
    base = Fraction(stream["time_base"])
    origin = Fraction(info["format"].get("start_time", "0"))
    result = []
    for frame in info["frames"]:
        start = int(frame["best_effort_timestamp"]) * base - origin
        result.append(start)
        if "nb_samples" in frame:
            result.append(start + Fraction(frame["nb_samples"], int(stream["sample_rate"])))
    return result


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
    source_times = times(args.input, "V:0")
    if not source_times or source_times != times(args.output, "V:0"):
        parser.exit(1, "Video frame count or presentation timestamps differ.\n")
    original_audio = probe(args.input, "-select_streams", "a:0", "-show_streams")["streams"][0]
    if any(original_audio[key] != tracks[1][key] for key in ("sample_rate", "channels")):
        parser.exit(1, "Audio format differs.\n")
    if audio_hash(args.input) != audio_hash(args.output):
        parser.exit(1, "AAC packet payload differs.\n")
    original_times = times(args.input, "a:0")
    output_times = times(args.output, "a:0")
    tolerance = Fraction(1, 1000)
    if len(original_times) != len(output_times) or any(
        abs(left - right) > tolerance for left, right in zip(original_times, output_times)
    ):
        parser.exit(1, "Audio presentation times differ by more than 1 ms or decoded frame counts differ.\n")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-protocol_whitelist", "file,pipe",
                    "-i", args.output.resolve(strict=True), "-f", "null", "-"],
                   check=True)
    print(f"{len(source_times)} matching frame times · {tracks[0]['width']} × {tracks[0]['height']} · "
          f"{tracks[1]['sample_rate']} Hz · matching AAC payload and timing · full decode OK · "
          f"{args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

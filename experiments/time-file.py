"""Measure file transcription wall time, including Swift process startup."""
from pathlib import Path
import json
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 experiments/time-file.py INPUT")
    root = Path(__file__).resolve().parents[1]
    bridge = subprocess.check_output([root / "scripts/build-swift", "file"], text=True).strip()
    with tempfile.TemporaryDirectory() as directory:
        wav = Path(directory) / "input.wav"
        start = perf_counter()
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                        "-i", Path(sys.argv[1]).resolve(strict=True), "-map", "0:a:0", "-ac", "1",
                        "-ar", "16000", "-c:a", "pcm_s16le", wav], check=True)
        extract_seconds = perf_counter() - start
        duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                                  "-of", "default=nw=1:nk=1", wav]))
        samples = []
        for _ in range(3):
            start = perf_counter()
            phrases = json.loads(subprocess.check_output([bridge, wav]))
            samples.append(perf_counter() - start)
            if not phrases:
                sys.exit("No final phrases. Use a speech sample for this measurement.")
    print(json.dumps({"audio_s": round(duration, 3), "extract_s": round(extract_seconds, 3),
                      "asr_wall_s": [round(sample, 3) for sample in samples],
                      "median_realtime_factor": round(statistics.median(samples) / duration, 3)}, indent=2))


if __name__ == "__main__":
    main()

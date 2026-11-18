"""Check a gap in AAC timestamps, and a deliberately shifted soundtrack."""
from array import array
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos/video-captions"
sys.path.insert(0, str(DEMO))
from caption import recognition_wav


def check_soundtrack(directory):
    ffmpeg = ["ffmpeg", "-v", "error", "-nostdin"]
    base, gap, rendered, shifted = [directory / (name + ".mp4") for name in ("base", "gap", "render", "shift")]
    subprocess.run([*ffmpeg, "-f", "lavfi", "-i", "color=s=160x120:r=10:d=2.5",
                    "-f", "lavfi", "-i", "sine=f=600:r=48000:d=1.4", "-c:v", "libx264", "-c:a", "aac", base],
                   check=True)
    jump = "setts=pts='PTS+gte(PTS,24000)*48000':dts='DTS+gte(DTS,24000)*48000'"
    subprocess.run([*ffmpeg, "-i", base, "-c", "copy", "-bsf:a", jump, gap], check=True)
    wav = directory / "speech.wav"
    recognition_wav(gap, 1, wav)
    with wave.open(str(wav)) as stream:
        rate = stream.getframerate()
        samples = array("h", stream.readframes(stream.getnframes()))
    assert rate == 16000 and abs(len(samples) / rate - 2.4) < 0.01
    assert not any(samples[rate * 3 // 4:rate * 5 // 4])
    assert max(samples[rate // 4:rate // 2]) > 1000 and max(samples[rate * 2:]) > 1000

    cues = directory / "cues.json"
    cues.write_text('[{"start":0.1,"end":0.4,"text":"星星"}]', encoding="utf-8")
    subprocess.run([sys.executable, DEMO / "caption.py", gap, rendered, "--cues", cues], check=True)
    checker = [sys.executable, ROOT / "experiments/check-media.py"]
    subprocess.run([*checker, gap, rendered], check=True)
    subprocess.run([*ffmpeg, "-i", rendered, "-itsoffset", "0.8", "-i", rendered,
                    "-map", "0:v", "-map", "1:a", "-c", "copy", shifted], check=True)
    result = subprocess.run([*checker, rendered, shifted], capture_output=True, text=True)
    assert result.returncode == 1 and "Audio presentation times differ" in result.stderr, result.stderr


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        check_soundtrack(directory)
    print("OK: AAC timestamp gap and shifted-audio control")

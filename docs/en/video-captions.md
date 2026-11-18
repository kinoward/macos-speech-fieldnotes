# Video captions · from audio to editable pixels

[Field notes](../../README.md) · [简体中文](../zh-CN/video-captions.md)

**Input** · An SDR MP4 with a video stream and AAC as its first audio track. **Output** · A new 10-bit H.265 MP4 and, on the recognition path, an editable `.cues.json`. The demo selects one picture stream and one audio stream. Camera data, alternate tracks and chapters are outside the export. [Encoder](../../demos/video-captions/caption.py)

## From the first draft to a reviewed frame

Run the [video quick start](../../README.md#run-either-demo). On the neutral sample, the recognizer produced two cues and heard the last character in “望远镜” as “近”. Opening the JSON makes this easy to fix. Times are seconds; the end of a cue may meet the start of the next.

```json
[
  {"start": 0.00, "end": 2.64, "text": "夜空中有一颗星星。"},
  {"start": 2.64, "end": 5.46, "text": "我们可以用望远镜观察月亮。"}
]
```

Edit `scratch/captioned.cues.json`, then render from the original. Use a new output name; existing media and generated timelines are protected from overwrites.

```bash
./demos/video-captions/run scratch/sky.mp4 scratch/reviewed.mp4 \
  --cues scratch/captioned.cues.json
python3 experiments/check-media.py scratch/sky.mp4 scratch/reviewed.mp4
```

### Why the pipeline uses two audio representations

1. FFmpeg writes a temporary 16 kHz mono PCM WAV. Swift reads it through `AVAudioFile`, requests Mandarin final results and extracts the audio time range of each attributed text run. A run may contain a character, a word or punctuation. If the timed runs do not reconstruct the full text, the result's own range keeps that phrase on the timeline. [File reader](../../demos/video-captions/Transcribe.swift) · [Apple Speech](https://developer.apple.com/videos/play/wwdc2025/277/)
2. The draft groups runs at sentence endings, pauses around 550 ms, long-held punctuation or the two-line display limit. Around six seconds is a further break opportunity. An oversized untimed phrase gets estimated internal boundaries. Review names, homophones and cue edges before publishing. [Cue builder](../../demos/video-captions/timeline.py)
3. Pillow draws one transparent plate per cue. Type is about 3.6% of frame height with a dark outline, an 86% text width and a bottom margin of about 6.4%. One or two lines are centered; blank plates represent gaps. Fonts are read locally. Pass `--font FONT_FILE` to select another CJK font.
4. FFmpeg reads the plates on a millisecond clock and overlays them on the original picture. Its output audio comes directly from the original AAC packets. Resampling the recognition WAV therefore has no effect on the soundtrack. The encoded video contains the caption pixels and plays without a subtitle track. [Overlay filter](https://ffmpeg.org/ffmpeg-filters.html#overlay) · [FFmpeg stream copy](https://ffmpeg.org/ffmpeg.html#Stream-copy)

## A 2.7K export with a byte cap

The original 4:3 case used **2688 × 2016**, **60000/1001 fps**, 10-bit H.265, 48 kHz stereo AAC and a **300,000,000-byte** ceiling. Its 20 captions were reviewed by hand. The historical export measured about 293.15 MB. These are results for one clip; the public sample contains new material.

```bash
./demos/video-captions/run scratch/sky.mp4 scratch/budget.mp4 \
  --cues scratch/captioned.cues.json --long-edge 2688 --max-mb 300
python3 experiments/check-media.py scratch/sky.mp4 scratch/budget.mp4 --max-mb 300
```

`--long-edge` caps the display dimension, preserves aspect ratio, rounds to even dimensions and avoids upscaling. A 960 × 540 input stays 960 × 540. The default uses x265 medium, CRF 21. A byte cap switches to two passes over the same scaled and captioned picture. The budget uses the actual AAC packet sizes and reserves room for MP4 overhead:

```text
target video kbit/s = floor(8 × (0.975 × limit_bytes − AAC_bytes − 8192) / duration_s / 1000)
```

The second pass writes a temporary output. The renderer checks its actual size before publishing it. If the copied audio alone consumes the budget or the muxed result is too large, choose a feasible cap. For a faster trial, use `--long-edge 960 --max-mb 0.80` on the generated sample. [x265 rate control](https://x265.readthedocs.io/en/master/cli.html#cmdoption-pass)

## What to verify

The provided checker compares **every decoded frame's presentation time relative to its container start**, the AAC payload hash, sample rate and channel count. It verifies the output streams and decodes the full file. For a visual check, seek before, during and after a cue against the same region of the original. On the synthetic 4:3 fixture only the active interval showed bright text in that region. [Verification code](../../experiments/check-media.py)

Right-angle display rotations are accounted for when sizing the plates. HDR-to-SDR mapping, multiple requested audio tracks and preserving camera metadata would each need an explicit export policy and suitable test inputs. Subtitle timing and readability on fast overlapping speech still need human review.

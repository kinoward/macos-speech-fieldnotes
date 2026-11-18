<h1 align="center">macOS Speech Field Notes</h1>

<p align="center"><strong>Engineering field notes · Two minimal demos · Reproducible experiments</strong><br>
One on-device Mandarin recognizer powers both video subtitles and live Mandarin-to-English translation.</p>

<p align="center">
  English · <a href="./README.zh-CN.md" lang="zh-CN">简体中文</a><br>
  By <a href="https://github.com/kinoward">Kino Ward (@kinoward)</a> ·
  <a href="https://github.com/kinoward/macos-speech-fieldnotes/stargazers"><img src="https://img.shields.io/github/stars/kinoward/macos-speech-fieldnotes?style=flat&amp;label=Stars" alt="GitHub star count"></a>
</p>

<p align="center"><code>macOS</code> <code>Apple silicon</code> <code>Swift</code> <code>on-device ASR</code> <code>video subtitles</code> <code>streaming translation</code></p>

<p align="center">
  <a href="#how-audio-becomes-captions">Architecture &amp; stack</a> ·
  <a href="#run-either-demo">Run the demos</a>
</p>

> **Final snapshot · 2026-11-18.** The demos are for study and reproduction only. The repository will receive no further updates. Use this date as the reference for the macOS and SDK versions, API behavior and timings reported here. [Demo source at that date](https://github.com/kinoward/macos-speech-fieldnotes/tree/1ed1c80effb51ccd5a6cf5bba69ab16531da4ccb/demos)

<p align="center">
  <picture>
    <source media="(max-width: 600px)" srcset="docs/assets/preview-mobile.png">
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/preview.png">
    <img src="docs/assets/preview.gif" width="1120" alt="The same Mandarin sentence burned into a night-sky video and progressively translated into English. Final text: There is a star in the night sky.">
  </picture>
</p>
<p align="center"><em>One utterance, illustrated. The reviewed video caption is on the left. The live draft and final translation are on the right.</em> · <a href="docs/assets/preview.png">Still image</a></p>

## How audio becomes captions

Both demos start with the same recognizer. A video editor can correct a word before export. A live viewer sees a draft first, so the English translation needs to follow revisions to the Mandarin text.

| Path | Technologies | What they do here |
| --- | --- | --- |
| [Shared recognizer](docs/en/architecture.md) | Swift · AVFoundation · Apple Speech (`SpeechAnalyzer`, `SpeechTranscriber`) | Feed file or microphone audio to the on-device model. Read timed text from a file or draft and final results from a stream. |
| [Video captions](docs/en/video-captions.md) | Python · Pillow · FFmpeg / ffprobe · H.265 (libx265) | Review timed cues, draw the text and burn it into the original video. Copy the AAC track and use two-pass encoding for a size budget. |
| [Live translation](docs/en/live-translation.md) | JavaScript · Web Audio API (`AudioWorklet`) · Node.js · WebSocket (`ws`) · Apple Translation (`TranslationSession`) | Stream mono PCM over a local connection, choose sentence breaks and keep the English caption paired with the latest Mandarin text. |

```mermaid
flowchart TD
  file("Video file"):::video --> wav["FFmpeg · mono WAV"]:::video
  mic("Browser microphone"):::live --> pcm["AudioWorklet · PCM<br/>Local WebSocket"]:::live
  wav --> speech(["Apple SpeechAnalyzer<br/>+ SpeechTranscriber"]):::core
  pcm --> speech
  speech --> time["Final text<br/>+ time ranges"]:::video
  speech --> live["Drafts + finals"]:::live
  time --> cues["Editable cues<br/>Pillow plates"]:::video
  cues --> burn("FFmpeg · captioned MP4"):::video
  file --> burn
  live --> split["Choose sentence breaks"]:::live
  split --> ui("Chinese + English captions"):::live
  split --> mt["Apple TranslationSession"]:::live
  mt --> ui
  classDef video fill:#fff0d8,stroke:#a76b34,color:#392a21
  classDef live fill:#e2f3ef,stroke:#4d8276,color:#173e38
  classDef core fill:#203c42,stroke:#82c6ad,color:#ffffff,stroke-width:2px
```

To reproduce the measurements, start with the file-timing probes and live replays. The experiment log gives the input, timing reference and controls for each run. [Experiments and results](docs/en/experiments.md)

## Run either demo

Tested on **Apple silicon with macOS 27.3 and the macOS 27.2 SDK**. Both demos compile Swift locally and work without a cloud API key. Prepare the Mandarin speech asset once. The live demo also needs the Simplified Chinese and US English translation languages in **System Settings → General → Language & Region → Translation Languages**. [Compatibility and asset setup](docs/en/architecture.md)

### Burn subtitles into a video

Use Python 3 with Pillow and an FFmpeg installation including `ffprobe`, `libx264` for the sample and `libx265` for export. Run these commands from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r demos/video-captions/requirements.txt
./demos/video-captions/run --prepare
./scripts/make-sample scratch/sky.mp4
./demos/video-captions/run scratch/sky.mp4 scratch/captioned.mp4
```

Open `scratch/captioned.mp4`. Its editable timeline is `scratch/captioned.cues.json`. Substitute your own SDR MP4 with AAC to try a different voice. [Review and re-render](docs/en/video-captions.md)

### Speak Mandarin, read English

Install Node.js 22+ with npm. The launcher installs its one locked dependency on first use.

```bash
./demos/live-translation/run --prepare
./demos/live-translation/run
```

In the local browser page, click **开始收听** (start), allow the microphone and speak Mandarin. Click **停止收听** (stop) to finish the last pair. Press Ctrl-C in the terminal to close the service. [Live protocol and timing](docs/en/live-translation.md)

## A result worth reproducing

In the synthetic sample, the recognizer heard **望远镜** (“telescope”) as **望远近**. The English preview inherited the error. A file user can edit one cue and re-render from the original. A live client needs to replace an earlier translation whenever the underlying words change. The probes show how to observe that difference and how to measure draft latency separately from finalization. [Experiment log](docs/en/experiments.md)

## Reading the commit history

Read the commits in chronological order to trace the work from file transcription through video captioning, live translation and sentence segmentation. The history follows Conventional Commits 1.0.0, with one logical change per commit. For example, `fix(live): keep timed commas with their preceding clause` records a specific segmentation decision. The commit body explains the reason for the change and how it was checked. [Commit specification](https://www.conventionalcommits.org/en/v1.0.0/) · [Project history](https://github.com/kinoward/macos-speech-fieldnotes/commits/main/)

## License

The **MIT License** covers the original code, field notes and silent illustrations. You may use, modify and redistribute them, including for commercial purposes. Keep the copyright and permission notices in all copies or substantial portions. The materials come without warranty. [Full license](LICENSE)

The sample generator creates audio locally. Model assets, system voices, fonts and third-party dependencies have their own license terms. [Data and materials](docs/en/architecture.md#data-and-materials)

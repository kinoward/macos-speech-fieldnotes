<h1 align="center">macOS Speech Field Notes</h1>

<p align="center"><strong>Engineering field notes · Two minimal demos · Reproducible experiments</strong><br>
One on-device Mandarin recognizer powers both video subtitles and live Mandarin-to-English translation.</p>

<p align="center">
  English · <a href="./README.zh-CN.md" lang="zh-CN">简体中文</a>
</p>

<p align="center">
  <a href="https://github.com/kinoward"><img src="https://img.shields.io/badge/Author-Kino%20Ward-5F568C?style=flat&amp;labelColor=293747&amp;logo=github&amp;logoColor=white" height="23" alt="Author Kino Ward (@kinoward)"></a>
  <a href="https://github.com/kinoward/macos-speech-fieldnotes/stargazers"><img src="https://img.shields.io/github/stars/kinoward/macos-speech-fieldnotes?style=flat&amp;label=Stars&amp;labelColor=293747&amp;color=1679A3" height="23" alt="GitHub star count"></a>
</p>

<p align="center">
  <a href="docs/en/experiments.md"><img src="https://img.shields.io/badge/Project-Field%20notes-7556B3?style=flat&amp;labelColor=293747" height="23" alt="Project · Field notes"></a>
  <a href="docs/en/architecture.md"><img src="https://img.shields.io/badge/macOS-Apple%20silicon-226794?style=flat&amp;labelColor=293747&amp;logo=apple&amp;logoColor=white" height="23" alt="macOS · Apple silicon"></a>
  <a href="docs/en/architecture.md"><img src="https://img.shields.io/badge/Swift-Apple%20Speech-B34829?style=flat&amp;labelColor=293747&amp;logo=swift&amp;logoColor=white" height="23" alt="Swift · Apple Speech"></a>
  <br>
  <a href="docs/en/architecture.md"><img src="https://img.shields.io/badge/ASR-On--device%20speech-246A86?style=flat&amp;labelColor=293747" height="23" alt="ASR · On-device speech"></a>
  <a href="docs/en/video-captions.md"><img src="https://img.shields.io/badge/Captions-FFmpeg%20%2B%20H.265-985720?style=flat&amp;labelColor=293747&amp;logo=ffmpeg&amp;logoColor=white" height="23" alt="Captions · FFmpeg + H.265"></a>
  <a href="docs/en/live-translation.md"><img src="https://img.shields.io/badge/Live%20translation-ZH%20%E2%86%92%20EN-167061?style=flat&amp;labelColor=293747&amp;logo=nodedotjs&amp;logoColor=white" height="23" alt="Live translation · ZH → EN"></a>
</p>

<p align="center">
  <a href="#find-a-solution">Find a solution</a> ·
  <a href="#how-audio-becomes-captions">Architecture</a> ·
  <a href="#run-either-demo">Demos</a>
</p>

> **Final snapshot · 2026-11-18.** These field notes and demos are complete. No further updates are planned. Versions and measurements refer to this date. [Demo source at that date](https://github.com/kinoward/macos-speech-fieldnotes/tree/1ed1c80effb51ccd5a6cf5bba69ab16531da4ccb/demos)

## Find a solution

- **How do I get timestamped JSON from a Mandarin WAV?** The Swift reader returns text with start and end times in seconds. [Swift transcription code](demos/video-captions/Transcribe.swift)
- **How do I keep a pause from changing the meaning?** In “我没有说要……关掉走廊的灯” (“I didn’t say to … turn off the hallway light”), a cut after the pause can turn the last words into a command. [Boundary rules](docs/en/live-translation.md#where-to-make-a-cut) · [Replay the 700 ms pause](docs/en/experiments.md#reproduce-the-measurements)
- **How do I keep an old translation off the screen?** When the Mandarin changes, match the English reply to the current revision before displaying it. [Display logic](demos/live-translation/public/revisions.js)
- **Did burning subtitles change the timing or audio?** Compare every frame’s presentation time and the AAC packet hashes against the original. [Media checker](experiments/check-media.py) · [Recorded results](docs/en/experiments.md#acceptance-evidence)

**Both demos require an Apple silicon Mac, macOS 27+ and the macOS 27+ SDK.** Prepare the Mandarin speech model once. Live translation also needs the Simplified Chinese and US English language packs. [Setup guide](docs/en/architecture.md#prepare-a-mac)

<p align="center">
  <picture>
    <source media="(max-width: 600px)" srcset="docs/assets/preview-mobile.png">
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/preview.png">
    <img src="docs/assets/preview.gif" width="1120" alt="The same Mandarin sentence burned into a night-sky video and progressively translated into English. Final text: There is a star in the night sky.">
  </picture>
</p>
<p align="center"><em>The same utterance appears as a reviewed video caption and as a live draft that becomes a final translation.</em> · <a href="docs/assets/preview.png">Still image</a></p>

## How audio becomes captions

Both demos start with the same recognizer. A video editor can correct a word before export. A live viewer sees a draft first, so the English translation needs to follow revisions to the Mandarin text.

- **Shared recognizer.** Swift and AVFoundation feed file or microphone audio to Apple’s `SpeechAnalyzer` and `SpeechTranscriber`. [Audio formats and clocks](docs/en/architecture.md)
- **Video captions.** Python and Pillow draw the reviewed cues. FFmpeg burns them into the picture with libx265 and copies the AAC track. Two-pass encoding targets a size budget. [Video pipeline](docs/en/video-captions.md)
- **Live translation.** A browser AudioWorklet sends PCM over a local WebSocket to Node.js. Swift chooses the sentence breaks and uses Apple’s `TranslationSession` to translate each revision. [Streaming protocol](docs/en/live-translation.md)

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

The reference runs used **macOS 27.3 and the macOS 27.2 SDK**. Both demos compile Swift locally and work without a cloud API key.

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

## Contributors

<p>
  <img src="https://github.com/kinoward.png?size=96" width="40" height="40" align="middle" alt=""> &nbsp;<strong>Kino Ward</strong> · <a href="https://github.com/kinoward">@kinoward</a>
</p>

## Reading the commit history

Read the commits in chronological order to trace the work from file transcription through video captioning, live translation and sentence segmentation. The history follows Conventional Commits 1.0.0, with one logical change per commit. For example, `fix(live): keep timed commas with their preceding clause` records a specific segmentation decision. The commit body explains the reason for the change and how it was checked. [Commit specification](https://www.conventionalcommits.org/en/v1.0.0/) · [Project history](https://github.com/kinoward/macos-speech-fieldnotes/commits/main/)

## Star history

<p align="center">
  <a href="https://www.star-history.com/?repos=kinoward%2Fmacos-speech-fieldnotes&amp;type=date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=kinoward/macos-speech-fieldnotes&amp;type=date&amp;legend=top-left&amp;theme=dark">
      <img src="https://api.star-history.com/chart?repos=kinoward/macos-speech-fieldnotes&amp;type=date&amp;legend=top-left" width="680" alt="GitHub star count for macOS Speech Field Notes by date">
    </picture>
  </a>
</p>

The badge at the top shows the current count. The chart plots stars by date, so a line appears once there are points on more than one date. [Explore the interactive chart](https://www.star-history.com/?repos=kinoward%2Fmacos-speech-fieldnotes&type=date)

## License

The **MIT License** covers the original code, field notes and silent illustrations. You may use, modify and redistribute them, including for commercial purposes. Keep the copyright and permission notices in all copies or substantial portions. The materials come without warranty. [Full license](LICENSE)

The sample generator creates audio locally. Model assets, system voices, fonts and third-party dependencies have their own license terms. [Data and materials](docs/en/architecture.md#data-and-materials)

# Architecture and model readiness

[Field notes](../../README.md) · [简体中文](../zh-CN/architecture.md)

Start with the shape of the audio. A file has an end and can be processed faster than playback. A microphone has a clock; its first draft must reach the screen before the end of the utterance. The two paths share a Mandarin asset selector and use different reporting options in the same Speech framework. [Shared implementation](../../shared/MandarinSpeech.swift) · [Apple's SpeechAnalyzer walkthrough](https://developer.apple.com/videos/play/wwdc2025/277/)

| Decision | File captions | Live captions |
| --- | --- | --- |
| Input | FFmpeg selects the first AAC track and writes a temporary 16 kHz mono PCM WAV | Browser AudioWorklet averages samples down to 16 kHz and sends 1,440 signed 16-bit little-endian samples per full message |
| Recognition | `SpeechAnalyzer.analyzeSequence(from:)` reads the audio file; collect final results with `audioTimeRange` | `AnalyzerInputConverter` feeds an async sequence of buffers; `.timeIndexedProgressiveTranscription` produces revisable and final results |
| Clock | Cue times are seconds on the media timeline. The audio stream's offset from the container start is added back. | Samples received since the start define the audio clock. Network packet boundaries have no linguistic meaning. |
| Consumer | An editable JSON timeline, then raster text and a new MP4 | A local Node process relays results; the browser pairs source and translation by segment and revision |
| End of input | Finalize the last analyzed time, then wait for the result sequence to finish | Flush the audio worklet, close Swift's input, finish analysis and drain translations before `done` |

## Which system does this require?

| Component | Version or capability | Check |
| --- | --- | --- |
| Reference route | Apple silicon; tested on M4, macOS 27.3, SDK 27.2 and Swift 6.4.2. Both launchers target macOS 27. | `uname -m`, `sw_vers -productVersion`, `xcrun --sdk macosx --show-sdk-version` |
| Speech | `SpeechAnalyzer` and `SpeechTranscriber` start at macOS 26; device and requested locale must also be supported. | `./demos/video-captions/run --check` |
| Buffer conversion | The live demo uses `AnalyzerInputConverter`, introduced in macOS 27. A macOS 26 port would need a streaming converter such as `AVAudioConverter`, coverage for final buffers, and validation on that OS. | [Converter availability](https://developer.apple.com/documentation/speech/analyzerinputconverter.md) |
| Translation | Installed `zh-Hans` and `en-US` models; the bridge requests the low-latency strategy. | `./demos/live-translation/run --check` |
| App-specific tools | File: Python 3 + Pillow, FFmpeg/ffprobe with x265. Sample creation also uses `say` and x264. Live: Node.js 22+ with npm and a browser supporting `getUserMedia` and `AudioWorklet`. | `ffmpeg -encoders`, `python3 --version`, `node --version` |

Install Apple's command-line developer tools with `xcode-select --install` if `xcrun` is unavailable. Verify the SDK version after installation. [Apple developer tools](https://developer.apple.com/xcode/resources/) · [SpeechTranscriber availability](https://developer.apple.com/documentation/speech/speechtranscriber.md)

## Prepare a Mac

1. Run the desired demo with `--prepare` while online. Swift resolves the supported Mandarin locale, checks `AssetInventory` and requests installation if necessary. The regular demo and `--check` report missing assets; only `--prepare` requests a speech download. [AssetInventory](https://developer.apple.com/documentation/speech/assetinventory)
2. For translation, open **System Settings → General → Language & Region → Translation Languages** and download Simplified Chinese and US English. Run the live check again. The bridge constructs `TranslationSession(installedSource:target:preferredStrategy:)` and checks `isReady`. [Download translation languages](https://support.apple.com/guide/mac-help/mchldd8b3c15/mac) · [TranslationSession](https://developer.apple.com/documentation/translation/translationsession)
3. Install the demo's software dependencies once. The live start script compiles the local bridge, installs the locked `ws` package and opens the loopback page. Browser microphone permission is requested when the listener starts. Use `OPEN_BROWSER=0` for replay or an existing browser tab.

## Data and materials

| Material | Where it goes |
| --- | --- |
| Video and editable text | User-selected input, output MP4 and sibling cue JSON. Temporary recognition WAV, PNG plates and encoding statistics live in a per-run directory that is removed on normal exit, including reported failures. |
| Live audio and translations | Browser → loopback WebSocket → local Node → Swift and Apple's system frameworks. Audio and captions are kept in memory in the live demo. The page keeps its rows after stop until the next successful start or page reload. |
| Network and permissions | Node listens on `127.0.0.1` and checks Host and Origin. Assets and dependencies may need downloads. Apple describes possible API usage and performance metrics that exclude the source text and translation. [Apple's translation privacy details](https://developer.apple.com/documentation/translation/translationsession.md) |
| Distributed material | Original source, notes, neutral example text and silent generated images. Dependencies and models are obtained separately. The `say` commands create audio for local personal testing; keep that audio and videos containing it out of distribution. For a public recording, use your own cleared material. [macOS licence, section 2F](https://www.apple.com/legal/sla/docs/macOSGoldenGate.pdf#page=3) · [FFmpeg licensing](https://ffmpeg.org/legal.html) |

Before sharing a fork, inspect the staged filenames and contents, the exported media tracks and metadata, and the identity used for commits. This edition was assembled from reviewed source and newly drawn images. Its staged export was checked locally with Gitleaks and a separate scan for identifying paths and private phrases. [GitHub guidance on sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

The [illustration generator](../../scripts/render-preview.py) draws the night sky and the caption states. The waveform and animation timing are illustrative. The [experiment log](experiments.md) records the timings measured at actual application boundaries.

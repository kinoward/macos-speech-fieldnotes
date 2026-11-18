# Experiments and reuse guide

[Field notes](../../README.md) · [简体中文](../zh-CN/experiments.md)

Use the question that matches your application. **File throughput** measures how fast an existing recording becomes text. **Live draft latency** measures how long a listener waits for the first useful words. **Finalization** measures when a segment stops changing. Two systems with identical ASR throughput can give a listener very different experiences.

## Reproduce the measurements

Run the [setup for the relevant demo](../../README.md#run-either-demo). The scripts generate new neutral Mandarin utterances locally. `VOICE` selects an installed Mandarin `say` voice; the reference runs used Tingting. The synthetic fixtures are for local personal testing.

```bash
mkdir -p scratch
./scripts/make-sample scratch/measure.mp4
python3 experiments/time-file.py scratch/measure.mp4
./experiments/make-probes scratch/probes
node --test experiments/revisions.test.mjs
```

Start `OPEN_BROWSER=0 ./demos/live-translation/run` in another terminal, then run:

```bash
(
  for case_name in negation condition noun independent mixed-condition pronoun-condition quiet noise silence; do
    node demos/live-translation/replay.mjs "scratch/probes/$case_name.wav" --expect "$case_name" --text || exit 1
  done
)
```

With the video demo’s Python environment active, the following check exercises the two-line portrait layout, a gap in the AAC clock, and a deliberately delayed soundtrack.

```bash
python3 experiments/video-regressions.py
```

The file timer extracts the WAV once and starts a fresh compiled Swift process three times. Its timed interval includes process startup, ASR and reading the JSON result. Compilation and model installation occur before measurement. The realtime factor is elapsed time divided by audio duration; smaller is faster. [Timer](../../experiments/time-file.py)

The replay decodes the audio incrementally and sends 90 ms packets according to sample time. `readyMs` starts at connection setup. `firstMs` and `doneMs` start when the bridge reports `ready`. The first final can arrive while later audio is still playing. `doneMs − audioMs` measures the tail after the last samples. `--text` displays local words for semantic review. `--expect` checks a named fixture’s expected outcome. For example, two independent clauses must yield two sections even when both languages incorrectly agree on one. Omit `--expect` for your own recordings. [Replay client](../../demos/live-translation/replay.mjs)

## Measurements from the initial release

Reference machine: Apple M4, macOS 27.3, SDK 27.2, Swift 6.4.2, Node 26.13.1 and FFmpeg 9.0.2. The clean video environment used Python 3.9.6 and Pillow 11.3. The language assets were already installed. Each live row below is **one paced replay**, with the live server and its Swift child restricted to loopback for IP connections.

The original replay decoded the whole file before opening the connection. The current replay starts FFmpeg at `ready`, so its first-draft timing also includes decoder startup.

| Probe | Audio (ms) | First Chinese draft (ms) | First English draft (ms) | First final English (ms) | Observed final content |
| --- | ---: | ---: | ---: | ---: | --- |
| Negation, 700 ms inserted pause | 3,543 | 1,026 | 1,091 | 3,676 | One section preserved “didn't say to turn off the light.” |
| Conditional clause | 4,288 | 1,000 | 2,086 | 4,343 | Condition and consequence stayed together. |
| Noun phrase | 3,893 | 1,027 | 2,064 | 3,976 | The modifier stayed with the noun. |
| Two independent clauses | 3,891 | 1,026 | 2,078 | 4,006 | Two translated sections within one final segment. |
| Conditional at −24 dB | 4,288 | 1,008 | 2,063 | 4,343 | The conditional meaning survived. |
| Conditional + seeded pink noise | 4,288 | 1,022 | 2,044 | 4,325 | Same final meaning as the clean take. |
| Digital silence | 3,000 | — | — | — | Zero caption events; the session ended normally. |

The independent-clause probe first produced one English sentence. Its final Speech result included a timed run containing a space and a comma. The original boundary logic treated that run as a word and placed the cut before the punctuation. Trimming the run **for punctuation classification**, while keeping its original character offsets, fixed the split and retained the negation and conditional controls. [Boundary policy](../../demos/live-translation/SpeechBridge.swift) · [Fixture text and timings](../../experiments/make-probes)

For file recognition, the astronomy sample contains **5.933 s** of audio. Three fresh processes yielded **0.192 / 0.187 / 0.188 s** in one run. FFmpeg extraction took **0.027 s**. The draft contained “望远近” for “望远镜”; the video guide shows the edited cue. The recognizer and translation can change with system language asset updates. [Video workflow](video-captions.md)

## Historical experiments

| Experiment | Observation | What to carry forward |
| --- | --- | --- |
| File recognition on one 52.33 s single-speaker recording | ASR reached final text in **1.05 / 0.82 / 0.80 s** across three runs; the original two-pass HEVC encode took roughly 12 minutes. | Preserve the boundary of each timer. The older ASR-only measurement and the public process timer use different scopes. |
| Early live prototype, 19.12 s synthetic speech | First English drafts at **5.11 / 2.06 / 2.05 s**. The first final arrived around **16.5 s**. The later segmentation experiment saw a first English preview around **1.1 s** on its controlled sample. | Always record draft and final times separately, along with the input and warm-up state. |
| Terminology hints | On a small clean/noisy homophone comparison, the default SpeechTranscriber showed no observed improvement from hints. DictationTranscriber with hints improved two target terms in clean speech and one in light noise. | Keep SpeechTranscriber as this demo's baseline. Compare a second recognizer with the **same** speaker, script and negative controls before changing it. [Apple DictationTranscriber](https://developer.apple.com/documentation/speech/dictationtranscriber) |

## Acceptance evidence

- A fresh directory containing only selected Git index files built both Swift tools, installed the locked Node dependency and used a new Python environment. No previous demo binary, installed project package or personal font was required.
- The video demo produced editable cues and re-rendered corrected text from the original. The checker matched presentation times for constant- and variable-frame-rate inputs and compared copied 48 kHz AAC by payload hash. The edited 0.80 MB export measured **769,898 bytes**, with all 178 frame times matching. A 4:3 synthetic export reached 2688 × 2016 at 60000/1001 fps using Main 10. The bright caption appeared and disappeared at the specified interval. [Media checker](../../experiments/check-media.py)
- Chrome's simulated microphone exercised the actual worklet, WebSocket, Swift and DOM. Both the Stop button and an input track's end event produced matching final revisions, released the input and left the captions visible. A separate deterministic check delivered an obsolete translation after a source correction. [Revision regression](../../experiments/revisions.test.mjs)
- With models installed, file inference ran under a process policy denying outbound IP connections. The live service and its child ran with only loopback IP allowed; a non-loopback socket control was denied. This verifies the applications' IP boundary. The host network and separate Apple system daemons were outside that isolation test. Physical microphone acoustics and sustained multi-speaker sessions remain open tests.

## Where to extend the research

| Question | Controlled comparison | Readouts |
| --- | --- | --- |
| Do hints help domain terms in natural speech? | Same consented local recording, current module vs. DictationTranscriber, with/without hints. Add similar correct words as controls. | Term errors, incorrect substitutions, first-draft latency. |
| Will the pause policy travel across rooms? | Play the same sentences at fixed distance, then vary level, noise and microphone distance one at a time. | Lost words, false splits, missed splits, final lag after speech. |
| What happens over a long conversation? | Fixed single-speaker take, then turns and overlap; replay at wall-clock speed. | Unpaired finals, maximum queue depth, memory and latency over time. |
| Can the live path move to macOS 26? | Replace only the audio converter, compare identical PCM inputs on an actual macOS 26 system. | Last-buffer delivery, audio time ranges, draft/final behavior. |

For a new experiment, record the question, system and asset readiness, input provenance, controlled change, timer origin, observed result and limitation. Share aggregate measurements and cleared example text; keep the underlying private recording and transcript with its owner.

# macOS 本地语音识别实践笔记

[English](./README.md) · 简体中文

怎样把普通话变成让人读得明白的字幕？这份手册沿着同一个端侧识别器走两条路。处理视频时，可以先校对时间轴，再把文字烧进画面。面对实时麦克风，识别器还在改字，观众已经需要看到原文和译文。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/preview-mobile.png">
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/preview.png">
  <img src="docs/assets/preview.gif" width="1120" alt="同一句普通话在左侧烧录进夜空画面，在右侧逐步译为英文。定稿为「夜空中有一颗星星」。">
</picture>

*流程示意。左侧是校对后的视频字幕，右侧展示中文草稿补全、英文逐步定稿。* [查看静态图](docs/assets/preview.png)

## 沿着音频看架构

```mermaid
flowchart TD
  file("本地视频"):::video --> wav["FFmpeg · 单声道 WAV"]:::video
  mic("浏览器麦克风"):::live --> pcm["AudioWorklet · PCM<br/>本机 WebSocket"]:::live
  wav --> speech(["Apple SpeechAnalyzer<br/>+ SpeechTranscriber"]):::core
  pcm --> speech
  speech --> time["定稿文字与时间范围"]:::video
  speech --> live["中文草稿与定稿"]:::live
  time --> cues["可编辑时间轴<br/>Pillow 字幕图层"]:::video
  cues --> burn("FFmpeg · 硬字幕 MP4"):::video
  file --> burn
  live --> split["结合停顿和句意分段"]:::live
  split --> ui("中英对照字幕"):::live
  split --> mt["Apple TranslationSession"]:::live
  mt --> ui
  classDef video fill:#fff0d8,stroke:#a76b34,color:#392a21
  classDef live fill:#e2f3ef,stroke:#4d8276,color:#173e38
  classDef core fill:#203c42,stroke:#82c6ad,color:#ffffff,stroke-width:2px
```

| 你正在解决的问题 | 可复用的内容 |
| --- | --- |
| [怎样选择本地语音接口](docs/zh-CN/architecture.md) | 模型准备、文件和音频流输入、系统版本，以及本地推理和下载资源的边界。 |
| [怎样为视频加字幕](docs/zh-CN/video-captions.md) | 词级时间范围、字幕校对、文字排版、原音轨复制和两遍编码的体积预算。 |
| [怎样做实时双语字幕](docs/zh-CN/live-translation.md) | 根据原文修订更新译文，以及一句话在停顿处被切开后，为什么会译出相反意思。 |
| [怎样复现或扩展研究](docs/zh-CN/experiments.md) | 可执行的实验、计时起点、实测结果，以及带对照条件的后续研究问题。 |

## 运行任一 Demo

实测环境为 **Apple silicon、macOS 27.3、macOS 27.2 SDK**。两个 Demo 均在本机编译 Swift，使用系统语言资源，无需云端 API 密钥。请先准备普通话语音识别资源。实时翻译还需在**系统设置 → 通用 → 语言与地区 → 翻译语言**下载简体中文和美式英语。[兼容性与语言资源](docs/zh-CN/architecture.md)

**A · 把字幕烧进视频。** 准备 Python 3、Pillow 和 FFmpeg；生成示例需要 `libx264`，导出需要 `libx265`，读取媒体信息需要 `ffprobe`。在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r demos/video-captions/requirements.txt
./demos/video-captions/run --prepare
./scripts/make-sample scratch/sky.mp4
./demos/video-captions/run scratch/sky.mp4 scratch/captioned.mp4
```

打开 `scratch/captioned.mp4` 即可观看，旁边的 `scratch/captioned.cues.json` 是可编辑的时间轴。也可以换成自己的 SDR 视频，第一条音轨需为 AAC。[校对和重新烧录](docs/zh-CN/video-captions.md)

**B · 说中文，看英文。** 准备 Node.js 22+ 和 npm。首次启动时，脚本会安装锁文件指定的一个依赖。

```bash
./demos/live-translation/run --prepare
./demos/live-translation/run
```

在本机网页点**开始收听**，允许麦克风并说中文。点**停止收听**后，网页会收完最后一组字幕。在终端按 Ctrl-C 可关闭服务。[实时协议和计时](docs/zh-CN/live-translation.md)

## 一个值得复现的细节

在新合成的样例中，识别器把“望远镜”听成了“望远近”，英文预览也继承了这个错误。视频用户可以只改一条字幕，从原片重新烧录。实时客户端则需要在原文被修订时替换旧译文。实验手册给出了观察这两种行为的方法，也说明了预览延迟和定稿时间应怎样分别测量。[实验记录](docs/zh-CN/experiments.md)

原创代码、笔记与静音插图使用 [MIT 许可](LICENSE)。示例音频在使用者本机生成。模型、系统音色和字体由各自的提供方供应。[数据流与素材说明](docs/zh-CN/architecture.md#数据与素材)

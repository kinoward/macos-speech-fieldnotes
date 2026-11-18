# 技术架构与模型准备

[实践笔记](../../README.zh-CN.md) · [English](../en/architecture.md)

选择接口时，先看音频怎样到达。文件有明确结尾，可以快于播放速度处理。麦克风输入按真实时间到达，观众希望在讲话结束前看到草稿。两条路线共用普通话语言资源的选择逻辑，在同一个 Speech 框架里开启不同的结果选项。[共享实现](../../shared/MandarinSpeech.swift) · [Apple SpeechAnalyzer 技术讲解](https://developer.apple.com/videos/play/wwdc2025/277/)

| 决策 | 视频字幕 | 实时字幕 |
| --- | --- | --- |
| 输入 | FFmpeg 读取第一条 AAC 音轨，临时提取 16 kHz 单声道 PCM WAV | 浏览器 AudioWorklet 通过区间加权平均把采样率降到 16 kHz，每个完整消息传输 1,440 个 16 位小端有符号样本 |
| 识别 | `SpeechAnalyzer.analyzeSequence(from:)` 读取音频文件，收集带 `audioTimeRange` 的最终结果 | `AnalyzerInputConverter` 把缓冲区转换为异步输入；`.timeIndexedProgressiveTranscription` 提供可修订结果和定稿 |
| 时间轴 | 字幕起止时间用媒体时间轴上的秒数。提取音轨后，加回音轨起点相对容器起点的偏移。 | 累计采样数构成音频时钟。传输包的边界与语句的边界相互独立。 |
| 消费结果 | 生成可编辑 JSON 时间轴，绘制文字，再导出新的 MP4 | 本机 Node 转发结果，浏览器按段号和版本匹配原文与译文 |
| 输入结束 | 要求分析器定稿到最后一个已分析时间，等待结果序列结束 | 冲刷 AudioWorklet 的尾部样本，关闭 Swift 输入，等识别与翻译结束后才发送 `done` |

## 系统要求

| 组件 | 版本或能力 | 自查方式 |
| --- | --- | --- |
| 实测路线 | Apple silicon；实测 M4、macOS 27.3、SDK 27.2、Swift 6.4.2。两个启动入口均以 macOS 27 为目标。 | `uname -m`、`sw_vers -productVersion`、`xcrun --sdk macosx --show-sdk-version` |
| 语音识别 | `SpeechAnalyzer` 和 `SpeechTranscriber` 自 macOS 26 提供，仍需检查设备与目标语言是否受支持。 | `./demos/video-captions/run --check` |
| 缓冲区转换 | 实时 Demo 使用 macOS 27 新增的 `AnalyzerInputConverter`。适配 macOS 26 可研究 `AVAudioConverter` 的流式用法，验证末尾缓冲区，并在该系统上复测。 | [接口可用性](https://developer.apple.com/documentation/speech/analyzerinputconverter.md) |
| 翻译 | 需要已安装的 `zh-Hans` 和 `en-US` 模型。桥接层选择低延迟翻译策略。 | `./demos/live-translation/run --check` |
| 各 Demo 的依赖 | 视频需要 Python 3、Pillow、带 x265 的 FFmpeg 和 ffprobe；生成样例还需 `say` 和 x264。实时需要 Node.js 22+、npm 和支持 `getUserMedia`、`AudioWorklet` 的浏览器。 | `ffmpeg -encoders`、`python3 --version`、`node --version` |

若找不到 `xcrun`，可用 `xcode-select --install` 安装 Apple 命令行开发工具，之后再核对 SDK 版本。[Apple 开发工具](https://developer.apple.com/xcode/resources/) · [SpeechTranscriber 可用性](https://developer.apple.com/documentation/speech/speechtranscriber.md)

## 准备一台 Mac

1. 联网时对所需 Demo 执行 `--prepare`。Swift 匹配系统支持的普通话区域，查询 `AssetInventory`，在缺少资源时请求下载。正常运行和 `--check` 会报告缺失项；申请下载的入口是 `--prepare`。[AssetInventory](https://developer.apple.com/documentation/speech/assetinventory)
2. 实时翻译还需打开**系统设置 → 通用 → 语言与地区 → 翻译语言**，下载简体中文和美式英语，再运行实时检查。桥接层通过 `TranslationSession(installedSource:target:preferredStrategy:)` 建立会话，并检查 `isReady`。[下载翻译语言](https://support.apple.com/guide/mac-help/mchldd8b3c15/mac) · [TranslationSession](https://developer.apple.com/documentation/translation/translationsession)
3. 安装所选 Demo 的软件依赖。实时启动脚本会编译本机桥接程序、安装锁文件指定的 `ws` 包并打开回环地址。点击开始收听时，浏览器会请求麦克风权限。回放测试或使用已有标签页时可设置 `OPEN_BROWSER=0`。

## 数据与素材

| 内容 | 去向 |
| --- | --- |
| 视频与可编辑文字 | 使用者选定输入、输出 MP4 及同名字幕 JSON。临时 WAV、PNG 图层和编码统计保存在单次运行目录，正常结束或报告错误时清理。 |
| 实时音频与译文 | 从浏览器经过本机 WebSocket 和 Node 送入 Swift 与 Apple 系统框架。实时 Demo 在内存中保存音频缓冲和字幕。停止后网页仍保留字幕，直至下次成功开始或页面重新加载。 |
| 网络与权限 | Node 仅监听 `127.0.0.1`，检查 Host 和 Origin。首次获取依赖与语言包可能需要网络。Apple 说明可能收集接口用量和性能指标，其中不包含原文和译文。[Apple 翻译隐私说明](https://developer.apple.com/documentation/translation/translationsession.md) |
| 公开材料 | 原创代码、笔记、中性示例文字和无声插图。依赖及模型另行获取。`say` 命令供本机个人测试；其录音及含该音轨的视频留在本机。公开有声素材请使用另行确认可分发的内容。[macOS 许可第 2F 节](https://www.apple.com/legal/sla/docs/macOSGoldenGate.pdf#page=3) · [FFmpeg 许可](https://ffmpeg.org/legal.html) |

发布衍生项目之前，应检查暂存的文件名与内容、媒体轨道及元数据，以及提交时使用的署名与邮箱。本版由逐项审阅的源码与全新绘制的图像组成，对暂存文件导出的目录执行了本机 Gitleaks 检查，并另行扫描可识别个人的路径和私人原文。[GitHub 敏感数据处理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

[插图生成脚本](../../scripts/render-preview.py)绘制夜空画面和字幕状态。波形与动画节奏用于示意，真实应用边界上的测量值见[实验记录](experiments.md)。

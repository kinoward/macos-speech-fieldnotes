# 视频字幕 · 从音轨到可校对的画面文字

[实践笔记](../../README.zh-CN.md) · [English](../en/video-captions.md)

**输入**为含视频流的 SDR MP4，第一条音轨为 AAC。**输出**是新的 10 位 H.265 MP4；自动识别时还会输出可编辑的 `.cues.json`。Demo 选择一条画面流和一条音轨，导出时省略相机数据、其他轨道和章节。[编码实现](../../demos/video-captions/caption.py)

## 从初稿到校对后的字幕

先按[快速开始](../../README.zh-CN.md#运行任一-demo)运行视频流程。中性样例生成了两条字幕，识别器把“望远镜”的“镜”听成了“近”。可以打开时间轴直接修改。时间单位为秒，上一条的结束时间可以等于下一条的开始时间。

```json
[
  {"start": 0.00, "end": 2.64, "text": "夜空中有一颗星星。"},
  {"start": 2.64, "end": 5.46, "text": "我们可以用望远镜观察月亮。"}
]
```

修改 `scratch/captioned.cues.json` 后，从原片重新烧录。请给输出取新名字，入口会保护已有视频与自动生成的字幕时间轴。

```bash
./demos/video-captions/run scratch/sky.mp4 scratch/reviewed.mp4 \
  --cues scratch/captioned.cues.json
python3 experiments/check-media.py scratch/sky.mp4 scratch/reviewed.mp4
```

### 为什么需要两份音频表示

1. FFmpeg 临时提取一份 16 kHz 单声道 PCM WAV。AAC 时间戳中途出现缺口时，识别用 WAV 在相应位置补静音，让录制停顿后的字幕仍能对上画面。Swift 通过 `AVAudioFile` 读取，获取普通话最终识别结果，再读取每个文本片段的音频时间范围。一个片段可能是单字、整词或标点。带时间的片段拼不回完整原文时，保留整段结果的时间范围。[文件识别实现](../../demos/video-captions/Transcribe.swift) · [Apple Speech](https://developer.apple.com/videos/play/wwdc2025/277/)
2. 初稿会在句末、约 550 毫秒的停顿、持续时间较长的标点或超过两行的地方分组，六秒左右也是一个候选断点。缺少细粒度时间的超长片段按长度估计内部边界。发布前应校对专名、同音词和字幕起止位置。[时间轴生成](../../demos/video-captions/timeline.py)
3. Pillow 把每条字幕绘制成透明图层。字号约为画面高度的 3.6%，使用深色描边，可用文字宽度为画面的 86%，底部安全距离约为画面高度的 6.4%。一到两行居中显示，空白图层表示无字幕时段。默认字体在本机读取，也可通过 `--font FONT_FILE` 指定其他中文字体。
4. FFmpeg 根据毫秒时间轴将图层叠加到原始画面，输出音频直接复制自原始 AAC 数据包。识别用 WAV 的重采样不会改变成片的声音。字幕成为画面像素，播放时无需字幕轨。[Overlay 滤镜](https://ffmpeg.org/ffmpeg-filters.html#overlay) · [FFmpeg 流复制](https://ffmpeg.org/ffmpeg.html#Stream-copy)

## 定体积的 2.7K 配方

历史 4:3 案例使用 **2688 × 2016、60000/1001 fps、10 位 H.265、48 kHz 双声道 AAC**，上限为 **300,000,000 字节**。20 条字幕经过人工校对，最终成片约 293.15 MB。公开样例使用全新素材，便于独立复现。

```bash
./demos/video-captions/run scratch/sky.mp4 scratch/budget.mp4 \
  --cues scratch/captioned.cues.json --long-edge 2688 --max-mb 300
python3 experiments/check-media.py scratch/sky.mp4 scratch/budget.mp4 --max-mb 300
```

`--long-edge` 限制显示画幅的长边，保持宽高比并将尺寸取为偶数。960 × 540 的样例不会被放大。默认使用 x265 medium、CRF 21；设置体积上限后，对同一套缩放与字幕合成结果执行两遍编码。预算采用 AAC 数据包的实际大小，并留出 MP4 封装余量：

```text
目标视频码率 kbit/s = 向下取整(8 × (0.975 × 上限字节数 − AAC 字节数 − 8192) / 时长秒数 / 1000)
```

第二遍先写临时文件，检查实际字节数后才生成目标文件。如果原音轨已耗尽预算，或封装后仍超限，需要选择可行的上限。用生成的小样本测试时，可以试 `--long-edge 960 --max-mb 0.80`。[x265 码率控制](https://x265.readthedocs.io/en/master/cli.html#cmdoption-pass)

## 怎样验收

随附检查脚本会对比**每一帧相对容器起点的显示时间**、音频相对画面的播放时间、AAC 数据包哈希、音频采样率与声道数，核对输出轨道并解码全片。即使 AAC 数据原样复制，整体移动音轨也应触发校验失败。画面验证应抽取字幕出现前、显示中、消失后的相同区域，与原片对照。合成 4:3 样例只在设定时段有亮色文字。[媒体校验代码](../../experiments/check-media.py)

在合成语音中插入两秒的时间戳缺口后，“观察”的识别时间从 4.14 秒移到 6.12 秒。仍有一个文本片段横跨静音，最终的字幕边界值得对照原音校对。媒体检查比较解码后的音频时间时，允许 1 毫秒的封装舍入误差。

图层尺寸计算会考虑直角旋转。要支持 HDR 到 SDR 的映射、多音轨或相机元数据，需要单独确定导出策略并补充相应样本。多人重叠、语速快的素材仍需人工判断字幕是否跟得上、读得完。

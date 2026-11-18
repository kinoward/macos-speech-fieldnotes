import AVFoundation
import CoreMedia
import Darwin
import Foundation
import Speech
import Synchronization
import Translation

private struct Message: Encodable {
    let type: String
    var text: String?
    var final: Bool?
    var message: String?
    var segmentId: Int?
    var revision: Int?
    var translatedRevision: Int?
}

private let stdoutClosed = Mutex(false)

private func send(_ message: Message) {
    stdoutClosed.withLock { closed in
        guard !closed else { return }
        var bytes = try! JSONEncoder().encode(message)
        bytes.append(10)
        FileHandle.standardOutput.write(bytes)
        closed = message.type == "error" || message.type == "done"
    }
}

private enum BridgeError: LocalizedError {
    case speechSetup
    case missingTranslation
    case translationFailed
    case invalidAudio
    case translationQueueFull

    var errorDescription: String? {
        switch self {
        case .speechSetup:
            "普通话语音识别未能启动。请检查 macOS 的语音识别语言资源。"
        case .missingTranslation:
            "请在 macOS 系统设置中下载离线翻译语言包「普通话（简体）」和「英语（美国）」，然后重试。"
        case .translationFailed:
            "本机翻译失败。请确认中英文翻译语言包已下载，然后重试。"
        case .invalidAudio:
            "麦克风音频格式有误。请重新开始。"
        case .translationQueueFull:
            "本机翻译处理积压。请重新开始。"
        }
    }
}

private func fail(_ error: Error) -> Never {
    send(Message(type: "error", message: (error as? SpeechAssetError)?.errorDescription ?? (error as? BridgeError)?.errorDescription
                 ?? "本机语音识别中断。请重新开始。"))
    exit(EXIT_FAILURE)
}

private func readPCM() async throws -> Data? {
    try await withCheckedThrowingContinuation { (reply: CheckedContinuation<Data?, Error>) in
        DispatchQueue.global(qos: .userInitiated).async {
            var bytes = Data(count: 6_400)
            let size = bytes.withUnsafeMutableBytes { destination in
                var count: Int
                repeat {
                    count = Darwin.read(STDIN_FILENO, destination.baseAddress, destination.count)
                } while count == -1 && errno == EINTR
                return count
            }
            if size > 0 {
                reply.resume(returning: bytes.prefix(size))
            } else if size == 0 {
                reply.resume(returning: nil)
            } else {
                reply.resume(throwing: POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO))
            }
        }
    }
}

private struct PauseCandidate: Sendable {
    let boundary: CMTime
    let quietMilliseconds: Int
}

private struct TimedToken: Sendable {
    let text: String
    let start: Double
    let end: Double
}

private struct ResultTiming: Sendable {
    let start: Double
    let end: Double
    let tokens: [TimedToken]
}

private struct SpeechPauses {
    // Measure over 20 ms so the result is independent of the browser's packet sizes.
    private let window = 320
    private let voicedWindowsNeeded = 10
    private let candidateWindows = [18, 26, 38, 44, 50, 80]
    private var power: Int64 = 0
    private var samplesInWindow = 0
    private var voicedWindows = 0
    private var quietWindows = 0
    private var totalSamples: Int64 = 0
    private var quietStart: Int64?
    private var noiseLevel = 32.0
    private var speechLevel = 0.0
    private var armed = false
    private var hasSignal = false

    var hasInputSignal: Bool { hasSignal }

    mutating func observe(_ samples: UnsafeBufferPointer<Int16>,
                          boundaries: AsyncStream<PauseCandidate>.Continuation) {
        for sample in samples {
            let value = Int64(sample)
            if value > 8 || value < -8 { hasSignal = true }
            power += value * value
            samplesInWindow += 1
            totalSamples += 1
            guard samplesInWindow == window else { continue }

            let rms = sqrt(Double(power) / Double(window))
            power = 0
            samplesInWindow = 0

            let speechThreshold = max(45.0, noiseLevel * 2.2)
            let quietThreshold: Double
            if armed {
                let relativeThreshold = noiseLevel + max(0, speechLevel - noiseLevel) * 0.20
                quietThreshold = max(40.0, min(relativeThreshold, max(90.0, speechThreshold * 2.0)))
            } else {
                quietThreshold = speechThreshold
            }

            if rms >= quietThreshold {
                voicedWindows = min(voicedWindows + 1, voicedWindowsNeeded)
                quietWindows = 0
                quietStart = nil
                speechLevel = speechLevel == 0 ? rms : speechLevel * 0.92 + rms * 0.08
                if voicedWindows == voicedWindowsNeeded { armed = true }
                continue
            }

            // Learn the ambient floor only from non-speech windows. Slow upward
            // movement adapts to room noise without teaching the gate that speech is noise.
            let adjustment = rms < noiseLevel ? 0.08 : 0.015
            noiseLevel = min(1_200, max(8, noiseLevel * (1 - adjustment) + rms * adjustment))

            guard armed else {
                voicedWindows = max(0, voicedWindows - 1)
                continue
            }

            quietWindows += 1
            if quietWindows == 1 { quietStart = totalSamples - Int64(window) }
            if candidateWindows.contains(quietWindows), let quietStart {
                // Keep the cut 200 ms inside the pause. At the earliest candidate,
                // the analyzer has already received audio beyond this point.
                let cut = quietStart + Int64(10 * window)
                boundaries.yield(PauseCandidate(
                    boundary: CMTime(value: cut, timescale: 16_000),
                    quietMilliseconds: quietWindows * 20
                ))
            }
        }
    }
}

private actor PCMInput {
    private let format: AVAudioFormat
    private let converter: AnalyzerInputConverter
    private let boundaries: AsyncStream<PauseCandidate>.Continuation
    private var pauses = SpeechPauses()
    private var leftover: UInt8?
    private var samplePosition: AVAudioFramePosition = 0
    private var converted: [AnalyzerInput] = []
    private var finished = false

    init(format: AVAudioFormat, analyzerFormat: AVAudioFormat,
         boundaries: AsyncStream<PauseCandidate>.Continuation) {
        self.format = format
        self.converter = AnalyzerInputConverter(analyzerFormat: analyzerFormat)
        self.boundaries = boundaries
    }

    var hasInputSignal: Bool { pauses.hasInputSignal }

    func next() async throws -> AnalyzerInput? {
        while converted.isEmpty {
            guard !finished else { return nil }
            guard var bytes = try await readPCM() else {
                guard leftover == nil else { throw BridgeError.invalidAudio }
                finished = true
                converted = try converter.flush()
                continue
            }

            // Pipe reads may end between the two bytes of a sample.
            if let leftover {
                bytes.insert(leftover, at: 0)
                self.leftover = nil
            }
            if !bytes.count.isMultiple(of: 2) {
                leftover = bytes.removeLast()
            }
            if bytes.isEmpty { continue }

            let sampleCount = AVAudioFrameCount(bytes.count / 2)
            guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: sampleCount),
                  let samples = buffer.int16ChannelData else {
                throw BridgeError.invalidAudio
            }
            bytes.copyBytes(to: UnsafeMutableRawBufferPointer(start: samples[0], count: bytes.count))
            buffer.frameLength = sampleCount
            pauses.observe(UnsafeBufferPointer(start: samples[0], count: Int(sampleCount)),
                           boundaries: boundaries)
            let timestamp = AVAudioTime(sampleTime: samplePosition, atRate: format.sampleRate)
            converted = try converter.convert(buffer, at: timestamp)
            samplePosition += AVAudioFramePosition(sampleCount)
        }
        return converted.removeFirst()
    }
}

private struct CaptionSections {
    private static let sentenceEnds = Set("。！？!?；;")
    private static let closingMarks = Set("”’」』）》】〕")
    static func split(_ text: String, softOffsets: Set<Int> = []) -> [String] {
        var sections: [String] = []
        var start = text.startIndex
        var index = start
        var offset = 0
        while index < text.endIndex {
            let next = text.index(after: index)
            offset += 1
            guard sentenceEnds.contains(text[index]) || softOffsets.contains(offset) else {
                index = next
                continue
            }
            var end = next
            if sentenceEnds.contains(text[index]) {
                while end < text.endIndex,
                      sentenceEnds.contains(text[end]) || closingMarks.contains(text[end]) {
                    end = text.index(after: end)
                    offset += 1
                }
            }
            let sentence = text[start..<end].trimmingCharacters(in: .whitespacesAndNewlines)
            if !sentence.isEmpty { sections.append(sentence) }
            start = end
            index = end
        }
        let tail = text[start...].trimmingCharacters(in: .whitespacesAndNewlines)
        if !tail.isEmpty { sections.append(tail) }
        return sections
    }
}

private enum FinalizationPolicy {
    private static let sentenceEnds = Set("。！？!?；;")
    private static let closingMarks = Set("”’」』》〉】〕")
    private static let unfinishedCharacters = Set("和与或而并但却把被给向对在从到为是有要会能可让说想")
    private static let unfinishedWords = ["因为", "虽然", "如果", "假如", "要是", "只要", "除非", "不但", "以及", "然后", "接着", "希望", "准备", "建议"]
    private static let dependentOpeners = ["如果", "假如", "要是", "只要", "除非", "因为", "虽然", "当", "等到", "为了", "关于"]
    private static let softUnfinishedCharacters = Set("这那每本该此的地得")
    private static let softUnfinishedWords = ["打开", "关闭", "保存", "检查", "更新", "刷新", "选择", "设置", "修改", "调整", "确认"]
    private static let dependentMainClauseMarkers = ["可以", "应该", "就", "那么", "则", "请", "我们", "我会", "你可以", "您可以"]
    private static let softContinuationOpeners = [
        "的", "地", "得", "着", "了", "过", "要", "也", "又", "还", "才", "就", "会", "能", "可以", "份", "个", "张", "页", "项", "种", "台", "件",
        "不能", "不会", "不是", "并", "而", "和", "与", "或", "但", "但是", "却", "把", "被", "给",
        "向", "对", "在", "从", "到", "为", "让", "说", "想"
    ]

    static func requiredQuietMilliseconds(for source: String) -> Int? {
        var text = source.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }

        while let last = text.last, closingMarks.contains(last) {
            text.removeLast()
        }
        var hasTerminal = false
        while let last = text.last, sentenceEnds.contains(last) {
            hasTerminal = true
            text.removeLast()
        }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }

        if let last = text.last, unfinishedCharacters.contains(last) { return 1_600 }
        if unfinishedWords.contains(where: { text.hasSuffix($0) }) { return 1_600 }
        if !text.contains(where: { "，,；;。！？!?".contains($0) }),
           dependentOpeners.contains(where: { text.hasPrefix($0) }) {
            return 1_600
        }
        if hasTerminal { return 760 }
        return 1_000
    }

    static func allowsSoftBoundary(left: String, right: String) -> Bool {
        var left = left.trimmingCharacters(in: .whitespacesAndNewlines)
        let right = right.trimmingCharacters(in: .whitespacesAndNewlines)
        guard left.count >= 4, right.count >= 2 else { return false }

        while let last = left.last, closingMarks.contains(last) {
            left.removeLast()
        }
        while let last = left.last, sentenceEnds.contains(last) {
            left.removeLast()
        }
        while let last = left.last, "，,、：:".contains(last) {
            left.removeLast()
        }
        left = left.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !left.isEmpty else { return false }

        if let last = left.last, unfinishedCharacters.contains(last) { return false }
        if let last = left.last, softUnfinishedCharacters.contains(last) { return false }
        if unfinishedWords.contains(where: { left.hasSuffix($0) }) { return false }
        if softUnfinishedWords.contains(where: { left.hasSuffix($0) }) { return false }
        if let opener = dependentOpeners.first(where: { left.hasPrefix($0) }),
           !left.contains(where: { "，,；;。！？!?".contains($0) }) {
            let remainder = String(left.dropFirst(opener.count))
            guard dependentMainClauseMarkers.contains(where: { remainder.contains($0) }) else {
                return false
            }
        }
        if let first = right.first, "，,、：:；;".contains(first) { return false }
        if softContinuationOpeners.contains(where: { right.hasPrefix($0) }) { return false }
        return true
    }
}

private struct TranslationJob: Sendable {
    let sections: [String]
    let final: Bool
    let segmentId: Int
    let revision: Int
}

private actor Captions {
    private struct PauseObservation: Sendable {
        let boundary: Double
    }

    private static let minimumSoftQuietMilliseconds = 360
    private let notify: AsyncStream<Void>.Continuation
    private var segmentId = 1
    private var revision = 0
    private var previousSource: [String] = []
    private var latestSource = ""
    private var previousQueuedPreview: [String] = []
    private var pendingFinals: [TranslationJob] = []
    private var pendingPreview: TranslationJob?
    private var finalizationRequested = false
    private var pauseObservations: [PauseObservation] = []
    private var lastFinalEnd = 0.0

    init(notify: AsyncStream<Void>.Continuation) {
        self.notify = notify
    }

    func observePause(_ candidate: PauseCandidate) {
        guard candidate.quietMilliseconds >= Self.minimumSoftQuietMilliseconds else { return }
        let boundary = candidate.boundary.seconds
        guard boundary > lastFinalEnd + 0.02 else { return }

        guard !pauseObservations.contains(where: { abs($0.boundary - boundary) < 0.02 }) else { return }
        pauseObservations.append(PauseObservation(boundary: boundary))
    }

    private func timedOffset(for boundary: Double, in text: String,
                             timing: ResultTiming) -> Int? {
        let combined = timing.tokens.map(\.text).joined()
        guard combined == text else { return nil }

        var offset = 0
        for token in timing.tokens {
            let nextOffset = offset + token.text.count
            guard token.end >= boundary else {
                offset = nextOffset
                continue
            }
            guard token.start <= boundary + 0.40 else { return nil }
            if token.text.allSatisfy({ "。！？!?;；，,”’」』》〉】〕".contains($0) }) {
                return nextOffset
            }
            return offset
        }
        return nil
    }

    private func validSoftOffset(_ offset: Int, in text: String) -> Bool {
        guard offset > 0, offset < text.count else { return false }
        let boundary = text.index(text.startIndex, offsetBy: offset)
        return FinalizationPolicy.allowsSoftBoundary(
            left: String(text[..<boundary]),
            right: String(text[boundary...])
        )
    }

    private func softOffsets(in text: String, timing: ResultTiming, final: Bool) -> Set<Int> {
        guard final else { return [] }
        var offsets = Set<Int>()
        let observations = pauseObservations.filter {
            $0.boundary >= timing.start - 0.05 && $0.boundary <= timing.end + 0.30
        }

        for observation in observations {
            if let offset = timedOffset(for: observation.boundary, in: text, timing: timing),
               validSoftOffset(offset, in: text) {
                offsets.insert(offset)
            }
        }
        return offsets
    }

    func receive(_ text: String, timing: ResultTiming, final: Bool) throws {
        let sections = CaptionSections.split(
            text,
            softOffsets: softOffsets(in: text, timing: timing, final: final)
        )
        let display = sections.joined(separator: "\n\n")
        if final {
            lastFinalEnd = max(lastFinalEnd, timing.end)
            pauseObservations.removeAll { $0.boundary <= lastFinalEnd + 0.02 }
            guard !sections.isEmpty || !previousSource.isEmpty else {
                latestSource = ""
                finalizationRequested = false
                return
            }
            revision += 1
            let job = TranslationJob(sections: sections, final: true,
                                     segmentId: segmentId, revision: revision)

            previousSource = []
            latestSource = ""
            previousQueuedPreview = []
            pendingPreview = nil
            finalizationRequested = false

            send(Message(type: "source", text: display, final: true,
                         segmentId: job.segmentId, revision: job.revision))
            segmentId += 1
            revision = 0
            if sections.isEmpty {
                send(Message(type: "translation", text: "", final: true,
                             segmentId: job.segmentId, revision: job.revision))
                return
            }
            guard pendingFinals.count < 8 else { throw BridgeError.translationQueueFull }
            pendingFinals.append(job)
            notify.yield(())
            return
        }

        if sections != previousSource {
            revision += 1
            previousSource = sections
            latestSource = text
            send(Message(type: "source", text: display, final: false,
                         segmentId: segmentId, revision: revision))
            if sections.isEmpty {
                previousQueuedPreview = []
                pendingPreview = nil
                send(Message(type: "translation", text: "", final: false,
                             segmentId: segmentId, revision: revision))
            }
        } else {
            latestSource = text
        }

        guard !sections.isEmpty, sections != previousQueuedPreview,
              text.count >= 4 || text.contains(where: { "。！？".contains($0) }) else { return }

        previousQueuedPreview = sections
        // Only the newest draft waits while a translation is running. Every source
        // revision gets a trailing chance, so a burst cannot strand an older preview.
        pendingPreview = TranslationJob(sections: sections, final: false,
                                        segmentId: segmentId, revision: revision)
        notify.yield(())
    }

    func requestFinalization(after quietMilliseconds: Int) -> Bool {
        guard !finalizationRequested,
              let needed = FinalizationPolicy.requiredQuietMilliseconds(for: latestSource),
              quietMilliseconds >= needed else { return false }
        finalizationRequested = true
        return true
    }

    func take() -> TranslationJob? {
        if !pendingFinals.isEmpty { return pendingFinals.removeFirst() }
        defer { pendingPreview = nil }
        return pendingPreview
    }

    func publish(_ text: String, for job: TranslationJob) {
        if !job.final {
            guard job.segmentId == segmentId else { return }
            if job.revision == revision, job.sections == previousSource {
                send(Message(type: "translation", text: text, final: false,
                             segmentId: job.segmentId, revision: job.revision))
                return
            }

            // A progressive result may only be reused when the current source is a
            // proven append-only extension. Retag it to the current source revision;
            // incompatible ASR corrections are discarded.
            guard job.sections.count == previousSource.count,
                  job.sections.dropLast().elementsEqual(previousSource.prefix(job.sections.count - 1)),
                  let draftTail = job.sections.last,
                  previousSource[job.sections.count - 1].hasPrefix(draftTail) else { return }
            send(Message(type: "translation", text: text, final: false,
                         segmentId: job.segmentId, revision: revision,
                         translatedRevision: job.revision))
            return
        }
        send(Message(type: "translation", text: text, final: job.final,
                     segmentId: job.segmentId, revision: job.revision))
    }
}

private func createTranslationSession() -> TranslationSession {
    let source = Locale.Language(identifier: "zh-Hans")
    let target = Locale.Language(identifier: "en-US")
    return TranslationSession(installedSource: source, target: target, preferredStrategy: .lowLatency)
}

private func run(checkOnly: Bool, prepare: Bool) async throws {
    let transcriber = try await MandarinSpeech.transcriber(progressive: true, install: prepare)
    let session = createTranslationSession()
    guard await session.isReady else { throw BridgeError.missingTranslation }
    let analyzer = SpeechAnalyzer(modules: [transcriber])
    guard let inputFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1,
                                          interleaved: true),
          let analyzerFormat = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber],
                                                                              considering: inputFormat) else {
        throw BridgeError.invalidAudio
    }
    do {
        try await analyzer.prepareToAnalyze(in: analyzerFormat)
    } catch {
        throw BridgeError.speechSetup
    }

    if prepare {
        print("Mandarin speech and Chinese–English translation assets are ready.")
        return
    }
    send(Message(type: "ready"))
    if checkOnly { return }

    let (pauses, boundaries) = AsyncStream<PauseCandidate>.makeStream(bufferingPolicy: .bufferingNewest(8))
    let pcm = PCMInput(format: inputFormat, analyzerFormat: analyzerFormat, boundaries: boundaries)
    let input = AsyncThrowingStream<AnalyzerInput, Error>(unfolding: { try await pcm.next() })
    let (wakeups, notify) = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
    let captions = Captions(notify: notify)
    let pauseFinalizer = Task {
        for await candidate in pauses {
            await captions.observePause(candidate)
            if await captions.requestFinalization(after: candidate.quietMilliseconds) {
                try await analyzer.finalize(through: candidate.boundary)
            }
        }
    }

    let translator = Task {
        var previousTranslations: [String: String] = [:]
        for await _ in wakeups {
            while let job = await captions.take() {
                do {
                    var translations: [String] = []
                    var used: [String: String] = [:]
                    for section in job.sections {
                        let translation: String
                        if let cached = used[section] ?? previousTranslations[section] {
                            translation = cached
                        } else {
                            translation = try await session.translate(section).targetText
                        }
                        used[section] = translation
                        translations.append(translation)
                    }
                    previousTranslations = used
                    await captions.publish(translations.joined(separator: "\n\n"), for: job)
                } catch {
                    fail(BridgeError.translationFailed)
                }
            }
        }
    }

    let results = Task {
        do {
            for try await result in transcriber.results {
                guard await pcm.hasInputSignal else { continue }
                let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                let tokens = result.text.runs.compactMap { run -> TimedToken? in
                    guard let range: CMTimeRange = run.audioTimeRange else { return nil }
                    return TimedToken(
                        text: String(result.text[run.range].characters),
                        start: range.start.seconds,
                        end: range.end.seconds
                    )
                }
                let timing = ResultTiming(
                    start: result.range.start.seconds,
                    end: result.range.end.seconds,
                    tokens: tokens
                )
                try await captions.receive(text, timing: timing, final: result.isFinal)
            }
        } catch is CancellationError {
            return
        } catch {
            fail(error)
        }
    }

    do {
        let last = try await analyzer.analyzeSequence(input)
        boundaries.finish()
        try await pauseFinalizer.value
        if let last {
            try await analyzer.finalizeAndFinish(through: last)
        } else {
            results.cancel()
            await analyzer.cancelAndFinishNow()
        }
    } catch {
        boundaries.finish()
        pauseFinalizer.cancel()
        results.cancel()
        await analyzer.cancelAndFinishNow()
        throw error
    }

    await results.value
    notify.finish()
    await translator.value
    send(Message(type: "done"))
}

@main
struct SpeechBridge {
    static func main() async {
        do {
            try await run(checkOnly: CommandLine.arguments.contains("--check"),
                          prepare: CommandLine.arguments.contains("--prepare"))
        } catch {
            fail(error)
        }
    }
}

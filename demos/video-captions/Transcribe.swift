import AVFoundation
import CoreMedia
import Foundation
import Speech

private struct Span: Encodable {
    let start: Double
    let end: Double
    let text: String
}

private func transcribe(_ url: URL, with module: SpeechTranscriber) async throws -> [[Span]] {
    let file = try AVAudioFile(forReading: url)
    let analyzer = SpeechAnalyzer(modules: [module])
    let readResults = Task {
        var phrases: [[Span]] = []
        for try await result in module.results where result.isFinal {
            let spans = result.text.runs.compactMap { run -> Span? in
                guard let range = run.audioTimeRange else { return nil }
                return Span(start: range.start.seconds, end: range.end.seconds,
                            text: String(result.text[run.range].characters))
            }
            let text = String(result.text.characters)
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
            if !spans.isEmpty && spans.map(\.text).joined() == text {
                phrases.append(spans)
            } else {
                phrases.append([Span(start: result.range.start.seconds, end: result.range.end.seconds, text: text)])
            }
        }
        return phrases
    }
    do {
        if let last = try await analyzer.analyzeSequence(from: file) {
            try await analyzer.finalizeAndFinish(through: last)
        } else {
            await analyzer.cancelAndFinishNow()
        }
        return try await readResults.value
    } catch {
        readResults.cancel()
        await analyzer.cancelAndFinishNow()
        throw error
    }
}

@main
struct Transcribe {
    static func main() async {
        do {
            let arguments = CommandLine.arguments.dropFirst()
            guard arguments.count == 1, let argument = arguments.first else {
                FileHandle.standardError.write(Data("Usage: file AUDIO.wav | --prepare | --check\n".utf8))
                exit(2)
            }
            let module = try await MandarinSpeech.transcriber(progressive: false, install: argument == "--prepare")
            if argument == "--prepare" || argument == "--check" {
                print("Mandarin speech assets are ready.")
                return
            }
            let phrases = try await transcribe(URL(fileURLWithPath: argument), with: module)
            let data = try JSONEncoder().encode(phrases)
            FileHandle.standardOutput.write(data)
        } catch {
            FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
            exit(1)
        }
    }
}

import Foundation
import Speech

enum SpeechAssetError: LocalizedError {
    case unsupported
    case notInstalled

    var errorDescription: String? {
        switch self {
        case .unsupported:
            "Mandarin SpeechTranscriber is unavailable on this Mac."
        case .notInstalled:
            "Mandarin speech assets are missing. Run this demo with --prepare while online."
        }
    }
}

enum MandarinSpeech {
    static func transcriber(progressive: Bool, install: Bool = false) async throws -> SpeechTranscriber {
        guard SpeechTranscriber.isAvailable,
              let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Locale(identifier: "zh-CN")) else {
            throw SpeechAssetError.unsupported
        }
        let module = progressive
            ? SpeechTranscriber(locale: locale, preset: .timeIndexedProgressiveTranscription)
            : SpeechTranscriber(locale: locale, transcriptionOptions: [], reportingOptions: [],
                                attributeOptions: [.audioTimeRange])

        if await AssetInventory.status(forModules: [module]) != .installed {
            guard install else { throw SpeechAssetError.notInstalled }
            if let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) {
                try await request.downloadAndInstall()
            }
            guard await AssetInventory.status(forModules: [module]) == .installed else {
                throw SpeechAssetError.notInstalled
            }
        }
        return module
    }
}

import Speech
import AVFoundation
import SwiftUI

struct DictationTextBuffer {
    let original: String
    func combining(_ recognized: String) -> String {
        guard !recognized.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return original }
        guard !original.isEmpty else { return recognized }
        return original + (original.hasSuffix("\n") ? "" : "\n") + recognized
    }
}

@MainActor final class JournalDictation: ObservableObject {
    enum Phase { case idle, preparing, recording, finishing }
    @Published private(set) var phase = Phase.idle
    @Published private(set) var transcript = ""
    @Published var errorMessage: String?
    var isRecording: Bool { phase == .recording }
    var isBusy: Bool { phase != .idle }
    var statusText: String {
        switch phase {
        case .idle: return "转写可修改，确认后再发送。"
        case .preparing: return "正在准备语音输入…"
        case .recording: return "正在听您讲述，点击停止结束录音。"
        case .finishing: return "正在完成转写…"
        }
    }
    private var engine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var recognition: SFSpeechRecognitionTask?
    private var finishTimeout: Task<Void, Never>?
    private var hasTap = false
    private var operation = UUID()

    func start(existingText: String = "") async {
        guard !isBusy else { return }
        let id = UUID(); operation = id; errorMessage = nil; phase = .preparing
        let buffer = DictationTextBuffer(original: existingText)
        transcript = existingText
        let permission = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard operation == id else { return }
        guard permission == .authorized else {
            cancel(); errorMessage = "请在系统设置中允许语音识别，或使用键盘输入。已有文字会保留。"; return
        }
        let microphone = await AVAudioApplication.requestRecordPermission()
        guard operation == id else { return }
        guard microphone else { cancel(); errorMessage = "请在系统设置中允许麦克风，或使用键盘输入。"; return }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN")), recognizer.isAvailable else {
            cancel(); errorMessage = "普通话语音识别暂不可用，请检查网络或使用键盘输入。"; return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true)
            let engine = AVAudioEngine(); self.engine = engine
            let request = SFSpeechAudioBufferRecognitionRequest(); self.request = request
            request.shouldReportPartialResults = true
            let input = engine.inputNode; let format = input.outputFormat(forBus: 0)
            guard format.channelCount > 0, format.sampleRate > 0 else { throw APIError.server("当前设备没有可用的麦克风。") }
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { audio, _ in request.append(audio) }
            hasTap = true
            recognition = recognizer.recognitionTask(with: request) { [weak self] result, error in
                let text = result?.bestTranscription.formattedString
                let final = result?.isFinal == true
                let failed = error != nil
                Task { @MainActor in
                    guard let self, self.operation == id else { return }
                    if let text { self.transcript = buffer.combining(text) }
                    if final || failed {
                        let wasRecording = self.phase == .recording
                        self.cancel()
                        if failed && wasRecording {
                            self.errorMessage = "语音识别中断。已识别文字会保留，请检查、修改后发送，或再次录音。"
                        } else if final && text?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false {
                            self.errorMessage = "没有识别到清楚的语音，请再次录音或使用键盘输入。"
                        }
                    }
                }
            }
            engine.prepare(); try engine.start(); phase = .recording
        } catch { cancel(); errorMessage = "无法开始录音，请检查麦克风权限或使用键盘输入。" }
    }

    /// Stop audio, allow a final recognition result, then release resources.
    func stop() {
        guard phase == .recording else { cancel(); return }
        phase = .finishing; stopAudio(); request?.endAudio()
        let id = operation
        finishTimeout = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(3)) } catch { return }
            guard let self, self.operation == id else { return }
            self.cancel()
            self.errorMessage = "最终转写未及时返回，已保留当前文字。请核对后发送，或再次录音。"
        }
    }
    func cancel() {
        operation = UUID(); phase = .idle
        finishTimeout?.cancel(); finishTimeout = nil
        stopAudio(); request?.endAudio(); recognition?.cancel()
        recognition = nil; request = nil; engine = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    private func stopAudio() {
        engine?.stop()
        if hasTap { engine?.inputNode.removeTap(onBus: 0); hasTap = false }
    }
}

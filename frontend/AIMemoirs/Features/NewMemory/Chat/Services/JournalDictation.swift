import Speech
import AVFoundation
import SwiftUI

@MainActor final class JournalDictation: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var transcript = ""
    @Published var errorMessage: String?
    private var engine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var recognition: SFSpeechRecognitionTask?
    private var hasTap = false
    private var operation = UUID()

    func start() async {
        guard !isRecording else { return }
        let id = UUID(); operation = id; errorMessage = nil
        let permission = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard operation == id else { return }
        guard permission == .authorized else { errorMessage = "请在系统设置中允许语音识别，或使用键盘输入。"; return }
        let microphone = await AVAudioApplication.requestRecordPermission()
        guard operation == id else { return }
        guard microphone else { errorMessage = "请在系统设置中允许麦克风，或使用键盘输入。"; return }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN")), recognizer.isAvailable else {
            errorMessage = "语音识别暂不可用，请使用键盘输入。"; return
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
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
            hasTap = true; transcript = ""
            recognition = recognizer.recognitionTask(with: request) { [weak self] result, error in
                let text = result?.bestTranscription.formattedString
                let finished = result?.isFinal == true || error != nil
                Task { @MainActor in
                    guard let self, self.operation == id else { return }
                    if let text { self.transcript = text }
                    if finished { self.stop() }
                }
            }
            engine.prepare(); try engine.start(); isRecording = true
        } catch { stop(); errorMessage = error.localizedDescription }
    }
    func stop() {
        operation = UUID(); isRecording = false
        engine?.stop()
        if hasTap { engine?.inputNode.removeTap(onBus: 0); hasTap = false }
        request?.endAudio(); recognition?.cancel()
        recognition = nil; request = nil; engine = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}

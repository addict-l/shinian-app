import SwiftUI

struct CareMicButton: View {
    let phase: JournalDictation.Phase
    var disabled = false
    let action: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Button(action: action) {
            TimelineView(.animation(minimumInterval: 1.0 / 20, paused: reduceMotion || phase != .recording)) { context in
                let pulse = reduceMotion || phase != .recording ? 0 : (sin(context.date.timeIntervalSinceReferenceDate * 4) + 1) / 2
                ZStack {
                    Circle().fill(CareTheme.soft.opacity(0.6)).frame(width: 158 + pulse * 8, height: 158 + pulse * 8)
                    Circle().fill(CareTheme.soft).frame(width: 146, height: 146)
                    Circle().fill(RadialGradient(colors: [Color(hex: 0xD98159), CareTheme.accent], center: .topLeading, startRadius: 2, endRadius: 132))
                        .frame(width: 132, height: 132)
                    if phase == .preparing {
                        ProgressView().tint(.white).controlSize(.large)
                    } else if phase == .recording || phase == .finishing {
                        RoundedRectangle(cornerRadius: 9).fill(.white).frame(width: 36, height: 36)
                    } else {
                        Image(systemName: "mic").font(.system(size: 48, weight: .regular)).foregroundStyle(.white)
                    }
                }.frame(width: 174, height: 174).accessibilityHidden(true)
            }
        }.buttonStyle(CarePressStyle()).disabled(disabled || phase == .finishing)
            .opacity(phase == .preparing || disabled ? 0.7 : 1)
            .accessibilityLabel(phase == .recording ? "停止录音" : phase == .preparing ? "取消准备" : phase == .finishing ? "正在转成文字" : "开始语音输入")
    }
}

struct CareRecordingIndicator: View {
    let startedAt: Date
    var body: some View {
        TimelineView(.periodic(from: startedAt, by: 1)) { context in
            let seconds = max(0, Int(context.date.timeIntervalSince(startedAt)))
            HStack(spacing: 7) {
                Circle().fill(CareTheme.recordDot).frame(width: 8, height: 8).accessibilityHidden(true)
                Text("正在听您说 · \(seconds / 60):\(String(format: "%02d", seconds % 60))")
                    .font(CareTheme.font(18, bold: true))
            }.foregroundStyle(CareTheme.recordInk).padding(.horizontal, 14).padding(.vertical, 8)
                .background(CareTheme.recordSoft, in: Capsule()).accessibilityElement(children: .combine)
        }
    }
}

private struct CareVoiceWave: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(minimumInterval: 0.08, paused: reduceMotion)) { context in
            HStack(spacing: 4) {
                ForEach(0..<19, id: \.self) { index in
                    let phase = reduceMotion ? Double(index) : context.date.timeIntervalSinceReferenceDate * 5 + Double(index) * 1.7
                    Capsule().fill(CareTheme.accentTop.opacity(0.75)).frame(width: 4, height: 7 + abs(sin(phase)) * 22)
                }
            }.frame(height: 30)
        }.accessibilityHidden(true)
    }
}

/// 显式开始/停止录音、核对文字、手动发送；继续复用现有转写服务。
struct CareNarrationInput: View {
    @Binding var text: String
    @ObservedObject var dictation: JournalDictation
    var disabled = false
    var retrying = false
    var permitsEmpty = false
    var inputIdentifier = "chat.input"
    var sendIdentifier = "chat.send"
    var voiceIdentifier = "chat.dictation"
    var pendingText: String? = nil
    var photoContent: AnyView? = nil
    let onSend: () -> Void
    @State private var writing = false
    @State private var startedAt = Date()
    @FocusState private var focused: Bool
    @Environment(\.dynamicTypeSize) private var typeSize
    private var hasText: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    private var reviewing: Bool { hasText || writing || permitsEmpty || retrying }
    private var lockedText: String {
        if let pendingText, !pendingText.isEmpty { return pendingText }
        return text
    }
    var body: some View {
        VStack(spacing: 14) {
            if dictation.isBusy {
                liveTranscript
                if dictation.phase == .recording { CareRecordingIndicator(startedAt: startedAt) }
                CareMicButton(phase: dictation.phase, disabled: disabled, action: toggleVoice)
                    .accessibilityIdentifier(voiceIdentifier)
                Text(dictation.phase == .preparing ? "正在准备…" : dictation.phase == .finishing ? "正在把话变成文字…" : "说完了，再按一下")
                    .font(CareTheme.font(24, bold: true)).multilineTextAlignment(.center)
                    .accessibilityIdentifier("chat.dictationStatus")
                if dictation.phase == .recording { CareVoiceWave() }
            } else if reviewing {
                transcriptCard
                CareButton(title: retrying ? "重试这段讲述" : "发送这段话", symbol: retrying ? "arrow.clockwise" : "arrow.up",
                           disabled: disabled || (!hasText && !retrying && !permitsEmpty)) {
                    focused = false; onSend()
                }.accessibilityIdentifier(sendIdentifier)
                if retrying {
                    Text("文字已锁定，重试成功前不能说下一段。")
                        .font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    if typeSize.isAccessibilitySize { VStack(spacing: 10) { moreVoice; clearButton } }
                    else { HStack(spacing: 12) { moreVoice; clearButton } }
                }
            } else {
                VStack(spacing: 2) {
                    CareMicButton(phase: .idle, disabled: disabled, action: toggleVoice).accessibilityIdentifier(voiceIdentifier)
                    Text("按一下，开始说").font(CareTheme.font(26, bold: true)).multilineTextAlignment(.center)
                    Text("说完再按一下，会变成文字").font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).multilineTextAlignment(.center)
                }.padding(.vertical, 4)
                CareButton(title: "我想打字", symbol: "keyboard", secondary: true, disabled: disabled) {
                    writing = true; focused = true
                }.accessibilityIdentifier(inputIdentifier + ".keyboard")
            }
        }.foregroundStyle(CareTheme.ink)
            .onChange(of: dictation.phase) { _, phase in if phase == .recording { startedAt = Date() } }
            .onChange(of: hasText) { _, value in if !value && !dictation.isBusy && !focused { writing = false } }
    }
    private var liveTranscript: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("正在变成文字…").font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
            Text(text.isEmpty ? "您说的话，会慢慢出现在这里。" : text).font(CareTheme.font()).lineSpacing(6)
                .frame(maxWidth: .infinity, alignment: .leading).lineLimit(4)
        }.padding(18).background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 24))
            .overlay { RoundedRectangle(cornerRadius: 24).stroke(CareTheme.soft, lineWidth: 2) }
    }
    private var transcriptCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                Text(retrying ? "这段话等着重新发送" : "您的讲述").font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
                Spacer(minLength: 4)
                if !retrying {
                    CareMiniButton(title: "改文字") { focused = true }.disabled(disabled)
                }
            }
            if retrying {
                Text(lockedText).font(CareTheme.font()).lineSpacing(6).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                TextField("在这里写下您的回忆", text: $text, axis: .vertical)
                    .font(CareTheme.font()).lineSpacing(6).lineLimit(2...5).focused($focused)
                    .disabled(disabled).accessibilityLabel("讲述文字").accessibilityIdentifier(inputIdentifier)
                    .toolbar {
                        ToolbarItemGroup(placement: .keyboard) {
                            Spacer()
                            Button("收起键盘") { focused = false }.accessibilityIdentifier(inputIdentifier + ".dismissKeyboard")
                        }
                    }
            }
            if let photoContent { photoContent }
        }.padding(18).background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 26))
            .overlay { RoundedRectangle(cornerRadius: 26).stroke(CareTheme.border.opacity(0.7), lineWidth: 1) }
    }
    private var moreVoice: some View {
        CareButton(title: "再说一段", symbol: "mic", secondary: true, disabled: disabled, fontSize: 21, action: toggleVoice)
            .accessibilityIdentifier(voiceIdentifier)
    }
    private var clearButton: some View {
        CareButton(title: "清空重说", symbol: "arrow.clockwise", secondary: true, disabled: disabled, fontSize: 21) {
            text = ""; writing = false; focused = false
        }.accessibilityIdentifier(inputIdentifier + ".clear")
    }
    private func toggleVoice() {
        focused = false
        if dictation.phase == .preparing { dictation.cancel() }
        else if dictation.isRecording { dictation.stop() }
        else { Task { await dictation.start(existingText: text) } }
    }
}

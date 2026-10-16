import SwiftUI

enum JournalCareMode {
    /// 设备上的显示偏好，不随退出家庭清除，也不混入家庭业务缓存。
    static let storageKey = "journal.careMode.enabled"
}

private struct JournalCareModeKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var journalCareMode: Bool {
        get { self[JournalCareModeKey.self] }
        set { self[JournalCareModeKey.self] = newValue }
    }
}

enum CareTheme {
    static let accent = Color(hex: 0x9E4C2D)
    static let paper = Color(hex: 0xF8F3E9)
    static let border = Color(hex: 0xDFD3C3)
    static func font(_ size: CGFloat = 22, bold: Bool = false) -> Font {
        JournalTheme.font(size, medium: bold)
    }
}

struct CareButton: View {
    let title: String
    var symbol: String? = nil
    var secondary = false
    var loading = false
    var disabled = false
    var minimumHeight: CGFloat = 64
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView().tint(secondary ? CareTheme.accent : .white) }
                else if let symbol { Image(systemName: symbol).accessibilityHidden(true) }
                Text(title).fixedSize(horizontal: false, vertical: true)
            }
            .font(CareTheme.font(22, bold: true)).multilineTextAlignment(.center)
            .padding(.horizontal, 14).padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: minimumHeight)
            .foregroundStyle(secondary ? JournalTheme.ink : .white)
            .background(secondary ? JournalTheme.surface : CareTheme.accent, in: RoundedRectangle(cornerRadius: 16))
            .overlay { if secondary { RoundedRectangle(cornerRadius: 16).stroke(CareTheme.border, lineWidth: 1) } }
            .opacity(disabled || loading ? 0.55 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain).disabled(disabled || loading)
    }
}

struct CareToolbar: View {
    let title: String
    var backTitle = "返回"
    var step: String? = nil
    var backIdentifier = "care.back"
    let onBack: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        Group {
        if typeSize.isAccessibilitySize {
            VStack(spacing: 8) {
                HStack {
                    backButton
                    Spacer(minLength: 8)
                    if let step { Text(step).font(CareTheme.font(16)).foregroundStyle(JournalTheme.ink2) }
                }
                Text(title).font(CareTheme.font(20, bold: true)).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity).accessibilityAddTraits(.isHeader)
            }
        } else {
        HStack(spacing: 8) {
            backButton
            Text(title).font(CareTheme.font(20, bold: true)).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
            Text(step ?? "").font(CareTheme.font(16)).foregroundStyle(JournalTheme.ink2)
                .frame(minWidth: 64, alignment: .trailing).accessibilityHidden(step == nil)
        }
        }
        }.foregroundStyle(JournalTheme.ink).padding(.horizontal, 20).padding(.vertical, 4)
    }
    private var backButton: some View {
        Button(action: onBack) {
            Label(backTitle, systemImage: "chevron.left").labelStyle(.titleAndIcon)
                .font(CareTheme.font(18)).frame(minWidth: 64, minHeight: 48, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier(backIdentifier)
    }
}

struct CareHeading: View {
    let title: String
    var subtitle: String? = nil
    var body: some View {
        VStack(spacing: 8) {
            Text(title).font(CareTheme.font(28, bold: true)).accessibilityAddTraits(.isHeader)
            if let subtitle { Text(subtitle).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2) }
        }.multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity)
    }
}

struct CareError: View {
    let message: String
    var retry: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(message, systemImage: "exclamationmark.circle").font(CareTheme.font(20))
                .foregroundStyle(JournalTheme.danger).fixedSize(horizontal: false, vertical: true)
            if let retry { CareButton(title: "再试一次", secondary: true, action: retry) }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
            .accessibilityElement(children: .contain)
    }
}

/// 同一套显式语音、文字、发送操作用于人生问答和故事讲述。
struct CareNarrationInput: View {
    @Binding var text: String
    @ObservedObject var dictation: JournalDictation
    var disabled = false
    var retrying = false
    var permitsEmpty = false
    var inputIdentifier = "chat.input"
    var sendIdentifier = "chat.send"
    var voiceIdentifier = "chat.dictation"
    let onSend: () -> Void
    @State private var writing = false
    @FocusState private var focused: Bool
    private var hasText: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    private var voiceTitle: String {
        switch dictation.phase {
        case .preparing: "取消准备"
        case .recording: "说完了，点这里"
        case .finishing: "正在完成转写…"
        case .idle: hasText || writing ? "再说一段" : "点击说话"
        }
    }
    var body: some View {
        VStack(spacing: 10) {
            if dictation.isBusy {
                Text(dictation.statusText).font(CareTheme.font(18)).foregroundStyle(CareTheme.accent)
                    .multilineTextAlignment(.center).accessibilityIdentifier("chat.dictationStatus")
            }
            if !retrying {
                CareButton(title: voiceTitle, symbol: dictation.isRecording ? "stop.circle.fill" : "mic.fill",
                           secondary: hasText && !dictation.isBusy, disabled: disabled || dictation.phase == .finishing) {
                    focused = false
                    if dictation.phase == .preparing { dictation.cancel() }
                    else if dictation.isRecording { dictation.stop() }
                    else { Task { await dictation.start(existingText: text) } }
                }.accessibilityIdentifier(voiceIdentifier)
            }
            if hasText || writing {
                VStack(alignment: .leading, spacing: 6) {
                    Text("您的讲述，可以修改").font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                    TextField("在这里写下您的回忆", text: $text, axis: .vertical)
                        .font(CareTheme.font()).lineLimit(1...4).padding(14).focused($focused)
                        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                        .overlay { RoundedRectangle(cornerRadius: 14).stroke(CareTheme.border, lineWidth: 1) }
                        .disabled(disabled || retrying || dictation.isBusy)
                        .accessibilityLabel("讲述文字").accessibilityIdentifier(inputIdentifier)
                        .toolbar {
                            ToolbarItemGroup(placement: .keyboard) {
                                Spacer()
                                Button("收起键盘") { focused = false }
                                    .accessibilityIdentifier(inputIdentifier + ".dismissKeyboard")
                            }
                        }
                }
            }
            if hasText || writing || retrying || permitsEmpty {
                CareButton(title: retrying ? "重试这段讲述" : "发送这段话", symbol: "arrow.up",
                           disabled: disabled || dictation.isBusy || (!hasText && !retrying && !permitsEmpty), action: onSend)
                    .accessibilityIdentifier(sendIdentifier)
            }
            if !writing && !retrying {
                Button { writing = true; focused = true } label: {
                    Label("我想打字", systemImage: "keyboard").font(CareTheme.font(18)).frame(minHeight: 48)
                }.buttonStyle(.plain).foregroundStyle(JournalTheme.ink2).disabled(disabled || dictation.isBusy)
                    .accessibilityIdentifier(inputIdentifier + ".keyboard")
            }
        }.onChange(of: hasText) { _, value in if !value { writing = false; focused = false } }
    }
}

struct CareDialogueEntry: Identifiable {
    let id: UUID
    let question: String
    let answer: String?
    var attachments: [ChatAttachment] = []
    static func from(_ turns: [LifeTurn]) -> [CareDialogueEntry] {
        var entries: [CareDialogueEntry] = []
        for turn in turns {
            if turn.role == "assistant" { entries.append(.init(id: turn.id, question: turn.content, answer: nil)) }
            else if let last = entries.last, turn.role == "user" {
                if last.answer == nil { entries[entries.count - 1] = .init(id: last.id, question: last.question, answer: turn.content) }
                else { entries.append(.init(id: turn.id, question: "补充讲述", answer: turn.content)) }
            } else if turn.role == "user" {
                entries.append(.init(id: turn.id, question: "您的讲述", answer: turn.content))
            }
        }
        return entries
    }
    static func chat(_ messages: [ChatMessage]) -> [CareDialogueEntry] {
        var entries: [CareDialogueEntry] = []
        for message in messages {
            if message.sender == .ai { entries.append(.init(id: message.id, question: message.text, answer: nil)) }
            else if let last = entries.last, last.answer == nil {
                entries[entries.count - 1] = .init(id: last.id, question: last.question, answer: message.text, attachments: message.attachments)
            } else { entries.append(.init(id: message.id, question: "补充讲述", answer: message.text, attachments: message.attachments)) }
        }
        return entries
    }
}

struct CareDialogueHistory: View {
    let entries: [CareDialogueEntry]
    var photoAPI: (any ChatAPI)? = nil
    let onClose: () -> Void
    @State private var index = 0
    private var page: Int { min(index, max(0, entries.count - 1)) }
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "刚才聊过的", step: entries.isEmpty ? "0 条" : "\(page + 1) / \(entries.count)", onBack: onClose)
            ScrollView {
                VStack(spacing: 20) {
                    if !entries.isEmpty {
                        Text(entries[page].question).font(CareTheme.font(24, bold: true)).multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity).accessibilityIdentifier("care.history.question")
                        VStack(alignment: .leading, spacing: 10) {
                            Text("您的回答").font(CareTheme.font(18)).foregroundStyle(CareTheme.accent)
                            Text(entries[page].answer ?? "这一个问题还没有回答。").font(CareTheme.font()).lineSpacing(5)
                                .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                            if let photoAPI {
                                ForEach(entries[page].attachments) { attachment in
                                    JournalMessagePhoto(attachment: attachment, api: photoAPI, fit: true)
                                        .frame(maxWidth: .infinity, minHeight: 160).clipShape(RoundedRectangle(cornerRadius: 14))
                                }
                            }
                        }.padding(20).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                    } else { Text("还没有开始讲述。").font(CareTheme.font()).foregroundStyle(JournalTheme.ink2) }
                }.padding(20)
            }
            HStack(spacing: 12) {
                CareButton(title: "上一条", secondary: true, disabled: page == 0) { index = page - 1 }
                    .accessibilityIdentifier("care.history.previous")
                CareButton(title: page == entries.count - 1 ? "返回核对" : "下一条", disabled: entries.isEmpty) {
                    if page == entries.count - 1 { onClose() } else { index = page + 1 }
                }.accessibilityIdentifier("care.history.next")
            }.padding(20)
        }.background(CareTheme.paper.ignoresSafeArea())
    }
}

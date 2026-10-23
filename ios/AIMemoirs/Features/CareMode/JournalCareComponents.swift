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
    var person: FamilyMember? = nil
    let onClose: () -> Void
    @State private var index = 0
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    private var page: Int { min(index, max(0, entries.count - 1)) }
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "刚才聊过的", step: entries.isEmpty ? "0 条" : "\(page + 1) / \(entries.count)", onBack: onClose)
            if !entries.isEmpty { CareProgressBar(current: page + 1, total: entries.count).padding(.horizontal, 20).padding(.bottom, 12) }
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if !entries.isEmpty {
                        HStack(alignment: .top, spacing: 10) {
                            CareIconTile(symbol: "sparkles", size: 44)
                            VStack(alignment: .leading, spacing: 12) {
                                Text("回忆助手问").font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
                                Text(entries[page].question).font(CareTheme.font(23, bold: true))
                                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("care.history.question")
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(18).journalCard(radius: 24)
                        }
                        HStack(alignment: .top, spacing: 10) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("您的回答").font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
                                Text(entries[page].answer ?? "这一个问题还没有回答。").font(CareTheme.font()).lineSpacing(7)
                                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                                if let photoAPI {
                                    ForEach(entries[page].attachments) { attachment in
                                        JournalMessagePhoto(attachment: attachment, api: photoAPI, fit: true)
                                            .frame(maxWidth: .infinity, minHeight: 160).clipShape(RoundedRectangle(cornerRadius: 18))
                                    }
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(18).journalCard(radius: 24, fill: CareTheme.soft)
                            if let person { JournalAvatar(person: person, size: 44) }
                            else { CareIconTile(symbol: "person", tone: .sage, size: 44) }
                        }.padding(.leading, typeSize.isAccessibilitySize ? 0 : 28)
                    } else { Text("还没有开始讲述。").font(CareTheme.font()).foregroundStyle(CareTheme.ink2) }
                }.padding(20).id(page)
            }.scrollIndicators(.hidden)
        }.safeAreaInset(edge: .bottom, spacing: 0) {
            Group {
                if typeSize.isAccessibilitySize && verticalSizeClass != .compact { VStack(spacing: 10) { previous; next } }
                else { HStack(spacing: 12) { previous; next } }
            }.careDock()
        }.carePage()
    }
    private var previous: some View {
        CareButton(title: "上一条", symbol: "chevron.left", secondary: true, disabled: page == 0, fontSize: 21) { index = page - 1 }
            .accessibilityIdentifier("care.history.previous")
    }
    private var next: some View {
        CareButton(title: page == entries.count - 1 ? "返回核对" : "下一条", symbol: "chevron.right", disabled: entries.isEmpty, fontSize: 21) {
            if page == entries.count - 1 { onClose() } else { index = page + 1 }
        }.accessibilityIdentifier("care.history.next")
    }
}

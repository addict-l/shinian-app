import SwiftUI

/// 通用人物行；无回调时可由外层手势组件接管点击。
struct JournalPersonRow: View {
    let person: FamilyMember
    var memoryCount: Int? = nil
    var showsChat = true
    var action: (() -> Void)? = nil
    var body: some View {
        HStack(spacing: 12) {
            JournalAvatar(person: person, size: 52)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(person.relationship.isEmpty ? person.name : person.relationship)
                        .font(JournalTheme.font(16.5, medium: true)).foregroundStyle(JournalTheme.ink)
                    if !person.relationship.isEmpty {
                        Text(person.name).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }
                }
                Text(detail).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineLimit(1)
            }
            Spacer(minLength: 0)
            if showsChat {
                DesignIcon("chat", size: 18).foregroundStyle(JournalTheme.accentDeep)
                    .frame(width: 34, height: 34).background(JournalTheme.soft, in: Circle())
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .journalCard()
        .contentShape(RoundedRectangle(cornerRadius: JournalTheme.cardRadius))
        .modifier(OptionalTapModifier(action: action))
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("members.card.\(person.name)")
    }
    private var detail: String {
        if let memoryCount { return memoryCount == 0 ? "还没有回忆" : "\(memoryCount) 段回忆" }
        return person.journalIdentity
    }
}

private struct OptionalTapModifier: ViewModifier {
    let action: (() -> Void)?
    func body(content: Content) -> some View {
        if let action {
            content.onTapGesture(perform: action)
        } else {
            content
        }
    }
}

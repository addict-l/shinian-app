import SwiftUI

/// 通用人物行；无回调时可由外层手势组件接管点击。
struct JournalPersonRow: View {
    let person: FamilyMember
    var action: (() -> Void)? = nil
    var body: some View {
        HStack(spacing: 16) {
            JournalAvatar(person: person)
            VStack(alignment: .leading, spacing: 7) {
                Text(person.name).font(JournalTheme.font(16, medium: true)).foregroundStyle(JournalTheme.ink)
                Text(person.journalIdentity).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(JournalTheme.muted)
        }
        .padding(.horizontal, 17).frame(minHeight: 84)
        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
        .contentShape(RoundedRectangle(cornerRadius: 18))
        .modifier(OptionalTapModifier(action: action))
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("members.card.\(person.name)")
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

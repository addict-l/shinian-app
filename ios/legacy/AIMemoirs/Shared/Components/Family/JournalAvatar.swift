import SwiftUI

/// 人物身份文字头像，用于列表与人物详情。
struct JournalAvatar: View {
    let person: FamilyMember
    var size: CGFloat = 48
    var body: some View {
        Text(String((person.relationship.isEmpty ? person.name : person.relationship).prefix(1)))
            .font(JournalTheme.font(size * 0.375, medium: true)).foregroundStyle(JournalTheme.accent)
            .frame(width: size, height: size).background(JournalTheme.soft, in: Circle())
            .accessibilityHidden(true)
    }
}

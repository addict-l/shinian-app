import SwiftUI

/// 统一空状态展示。
struct JournalEmptyState: View {
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "book.closed").font(.system(size: 26, weight: .light)).foregroundStyle(JournalTheme.accent)
                .frame(width: 64, height: 64).background(JournalTheme.soft, in: Circle())
            Text(title).font(JournalTheme.story(19)).padding(.top, 4)
            Text(message).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                .multilineTextAlignment(.center).lineSpacing(4)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 44)
    }
}

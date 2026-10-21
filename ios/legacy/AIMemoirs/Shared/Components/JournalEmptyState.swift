import SwiftUI

/// 统一空状态展示。
struct JournalEmptyState: View {
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "book.closed").font(.system(size: 32, weight: .light)).foregroundStyle(JournalTheme.accent)
            Text(title).font(JournalTheme.font(18, medium: true))
            Text(message).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 48)
    }
}

import SwiftUI

/// 统一可重试错误展示，请求逻辑由调用方注入。
struct JournalError: View {
    let message: String
    var retryTitle = "重新加载"
    let retry: () -> Void
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "cloud.drizzle").font(.system(size: 16)).foregroundStyle(JournalTheme.roseInk)
                .frame(width: 34, height: 34).background(JournalTheme.roseSoft, in: Circle()).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 6) {
                Text(message).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.secondaryInk)
                    .fixedSize(horizontal: false, vertical: true)
                Button(retryTitle, action: retry).font(JournalTheme.font(13, medium: true)).foregroundStyle(JournalTheme.accent).frame(minHeight: 44)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        .journalCard(radius: 18)
    }
}

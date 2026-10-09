import SwiftUI

/// 统一可重试错误展示，请求逻辑由调用方注入。
struct JournalError: View {
    let message: String
    let retry: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(message).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
            Button("重新加载", action: retry).font(JournalTheme.font(13, medium: true))
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
    }
}

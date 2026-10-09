import SwiftUI

/// 通用搜索输入框，搜索规则由使用页面负责。
struct JournalSearch: View {
    let prompt: String
    @Binding var text: String
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "magnifyingglass").font(.system(size: 17)).foregroundStyle(JournalTheme.muted)
            TextField(prompt, text: $text).font(JournalTheme.font(14))
                .autocorrectionDisabled().submitLabel(.search)
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .foregroundStyle(JournalTheme.muted).accessibilityLabel("清除搜索")
            }
        }
        .padding(.horizontal, 16).frame(height: 50)
        .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
    }
}

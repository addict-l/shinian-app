import SwiftUI

/// 通用搜索输入框，搜索规则由使用页面负责。
struct JournalSearch: View {
    let prompt: String
    @Binding var text: String
    var body: some View {
        HStack(spacing: 10) {
            DesignIcon("search").foregroundStyle(JournalTheme.muted)
            TextField("", text: $text, prompt: Text(prompt).foregroundStyle(JournalTheme.muted))
                .font(JournalTheme.font(14)).foregroundStyle(JournalTheme.ink)
                .autocorrectionDisabled().submitLabel(.search)
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .foregroundStyle(JournalTheme.muted).accessibilityLabel("清除搜索")
            }
        }
        .padding(.horizontal, 16).frame(height: 46)
        .background(JournalTheme.surface, in: Capsule())
        .overlay { Capsule().stroke(JournalTheme.line, lineWidth: 1) }
    }
}

import SwiftUI

/// 草稿编辑页面只持有文本绑定；生成请求仍使用聊天页面的同一个会话。
struct JournalDraftEditorView: View {
    @Binding var text: String
    let loading: Bool
    let error: String?
    let onCancel: () -> Void
    let onUpdate: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text("修改内容后，AI 将根据你的修订生成新草稿，供你再次确认。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                TextEditor(text: $text).font(JournalTheme.font(16)).scrollContentBackground(.hidden)
            }.padding(24).background(JournalTheme.paper).navigationTitle("编辑回忆").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消", action: onCancel) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("更新草稿") {
                            onUpdate()
                        }.disabled(loading || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
                .overlay(alignment: .bottom) { if let error = error { Text(error).font(JournalTheme.font(12)).foregroundStyle(.red).padding() } }
        }.interactiveDismissDisabled(loading)
    }
}

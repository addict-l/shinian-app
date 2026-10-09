import SwiftUI

/// 保存前预览：展示草稿与保存状态，返回、编辑和保存通过回调交由聊天流程处理。
struct JournalMemoryReviewView: View {
    let draft: GeneratedMemory
    let imageData: Data?
    let identity: String
    @ObservedObject var saveModel: MemorySaveViewModel
    let onBack: () -> Void
    let onEdit: () -> Void
    let onSave: () async -> Void

    var body: some View {
        NavigationStack {
            JournalStoryContent(memory: draft.memory.copy(imageData: imageData ?? draft.memory.imageData), identity: identity, dateText: draft.preview.date, location: draft.preview.location, isDraft: true)
                .journalPage().navigationTitle("回忆预览").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(action: onBack) { Image(systemName: "chevron.left") }.disabled(saveModel.isSaving).accessibilityLabel("返回对话") }
                    ToolbarItem(placement: .topBarTrailing) { Button("编辑", action: onEdit).disabled(saveModel.isSaving) }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    VStack(spacing: 14) {
                        if let error = saveModel.errorMessage { Text(error).font(JournalTheme.font(12)).foregroundStyle(.red) }
                        JournalButton(title: "保存这段回忆", loading: saveModel.isSaving) {
                            Task { await onSave() }
                        }.accessibilityIdentifier("memory.save")
                        Text("只在你确认后，成为正式回忆").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                    }.padding(.horizontal, 24).padding(.top, 20).padding(.bottom, 10)
                        .background(JournalTheme.surface.ignoresSafeArea(edges: .bottom))
                        .overlay(alignment: .top) { JournalTheme.line.frame(height: 1) }
                }
        }.preferredColorScheme(.light).interactiveDismissDisabled(saveModel.isSaving)
    }
}

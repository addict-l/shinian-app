import SwiftUI

/// Presentation and its content have one lifetime: a cover always receives a draft.
struct JournalDraftPresentation: Identifiable {
    let id = UUID()
    let draft: GeneratedMemory
    let imageData: Data?
}

/// Owns edits and save state until dismissal finishes, independently of the chat.
struct JournalDraftPreviewView: View {
    let identity: String
    let api: any MemoryAPI
    let imageData: Data?
    let onBack: () -> Void
    let onSaved: () async -> Void
    @State private var draft: GeneratedMemory
    @StateObject private var saveModel: MemorySaveViewModel
    @State private var showingEdit = false
    @State private var confirmRegeneration = false
    @State private var regenerating = false
    @State private var regenerateLatest: GeneratedMemory?

    init(presentation: JournalDraftPresentation, identity: String, api: any MemoryAPI,
         onBack: @escaping () -> Void, onSaved: @escaping () async -> Void) {
        self.identity = identity; self.api = api; self.imageData = presentation.imageData
        self.onBack = onBack; self.onSaved = onSaved
        _draft = State(initialValue: presentation.draft)
        _saveModel = StateObject(wrappedValue: MemorySaveViewModel(api: api))
    }

    var body: some View {
        JournalMemoryReviewView(draft: draft, imageData: imageData, identity: identity,
            saveModel: saveModel, onBack: onBack,
            onEdit: { showingEdit = true },
            onRegenerate: { confirmRegeneration = true },
            onSave: {
                guard await saveModel.save(draft) else { return }
                await onSaved()
            })
            .alert("重新生成草稿？", isPresented: $confirmRegeneration) {
                Button("保留当前草稿", role: .cancel) {}
                Button("确认重新生成", role: .destructive) { Task { await regenerate() } }
            } message: { Text("AI 将根据当前讲述重新整理，并替换草稿的标题和正文。手改标题和正文也会被替换；已确认的手改时间会保留，新文字将再次提示校对。") }
            .alert("草稿已在其他设备更新", isPresented: Binding(get: { regenerateLatest != nil }, set: { if !$0 { regenerateLatest = nil } })) {
                Button("保留当前预览", role: .cancel) { regenerateLatest = nil }
                Button("读取最新草稿") {
                    if let latest = regenerateLatest { draft = latest }
                    regenerateLatest = nil
                }
            } message: { Text("请读取最新草稿并核对后，再决定是否重新生成。") }
            .sheet(isPresented: $showingEdit) {
                JournalDraftEditorView(draft: draft, api: api, onCancel: { showingEdit = false },
                    onUpdated: { updated in draft = updated; showingEdit = false })
            }
    }

    private func regenerate() async {
        guard !regenerating else { return }
        regenerating = true; saveModel.isSaving = true; saveModel.errorMessage = nil
        defer { regenerating = false; saveModel.isSaving = false }
        do {
            draft = try await api.regenerateDraft(draft)
            if draft.timeReviewFrom != nil { showingEdit = true }
        }
        catch {
            saveModel.errorMessage = error.localizedDescription
            if isVersionConflict(error) { regenerateLatest = try? await api.getDraft(id: draft.draftID) }
        }
    }
}

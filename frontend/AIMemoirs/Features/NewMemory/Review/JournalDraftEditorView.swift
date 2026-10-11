import SwiftUI

/// Direct edits never create a chat message or invoke the language model.
struct JournalDraftEditorView: View {
    let draft: GeneratedMemory
    let api: any MemoryAPI
    let onCancel: () -> Void
    let onUpdated: (GeneratedMemory) -> Void
    @State private var title: String
    @State private var text: String
    @State private var busy = false
    @State private var error: String?
    @State private var latest: GeneratedMemory?
    @State private var discard = false
    @State private var overwrite = false
    @FocusState private var focused: String?
    init(draft: GeneratedMemory, api: any MemoryAPI, onCancel: @escaping () -> Void, onUpdated: @escaping (GeneratedMemory) -> Void) {
        self.draft = draft; self.api = api; self.onCancel = onCancel; self.onUpdated = onUpdated
        _title = State(initialValue: draft.memory.title); _text = State(initialValue: draft.memory.content)
    }
    private var changed: Bool { title != draft.memory.title || text != draft.memory.content }
    var body: some View {
        NavigationStack {
            Form {
                Section("标题") { TextField("回忆标题", text: $title).focused($focused, equals: "title").accessibilityIdentifier("draft.title") }
                Section("正文") { TextEditor(text: $text).focused($focused, equals: "body").frame(minHeight: 240).accessibilityIdentifier("draft.body") }
                Section { Text("你的修改会直接保留，确认保存后成为正式回忆。").foregroundStyle(JournalTheme.muted) }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                if let latest {
                    Section("最新草稿 · 本机修改仍保留在上方") {
                        Text(latest.memory.title).font(.headline)
                        Text(latest.memory.content)
                        Button("核对后保存本机修改") { overwrite = true }.accessibilityIdentifier("draft.resolveConflict")
                    }
                }
            }.scrollDismissesKeyboard(.interactively).scrollContentBackground(.hidden).background(JournalTheme.paper)
                .navigationTitle("编辑草稿").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { if changed { discard = true } else { onCancel() } }.disabled(busy) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保留修改") { focused = nil; Task { await save(draft) } }
                            .disabled(busy || latest != nil || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.count > 200 || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("draft.keepEdits")
                    }
                }
                .overlay { if busy { ProgressView("正在保留修改…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
                .alert("放弃本次修改？", isPresented: $discard) { Button("继续编辑", role: .cancel) {} ; Button("放弃修改", role: .destructive, action: onCancel) } message: { Text("草稿原有内容会保留。") }
                .alert("保存本机修改到最新草稿？", isPresented: $overwrite) {
                    Button("继续核对", role: .cancel) {}; Button("保存我的修改") { if let latest { Task { await save(latest) } } }
                } message: { Text("将用上方编辑的标题和正文替换最新草稿。其他设备的新修改请先核对。") }
        }.interactiveDismissDisabled(changed || busy)
    }
    private func save(_ base: GeneratedMemory) async {
        busy = true; error = nil
        defer { busy = false }
        do { onUpdated(try await api.editDraft(base, title: title, content: text)) }
        catch {
            self.error = error.localizedDescription
            if isVersionConflict(error) {
                do { latest = try await api.getDraft(id: draft.draftID) }
                catch { self.error = "读取最新草稿失败，修改仍保留。请重试：" + error.localizedDescription }
            }
        }
    }
}

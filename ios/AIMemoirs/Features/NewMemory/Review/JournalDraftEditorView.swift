import SwiftUI

/// Direct edits never create a chat message or invoke the language model.
struct JournalDraftEditorView: View {
    let draft: GeneratedMemory
    let api: any MemoryAPI
    let onCancel: () -> Void
    let onUpdated: (GeneratedMemory) -> Void
    @State private var title: String
    @State private var text: String
    @State private var time: InformationDimension
    @State private var timeAnchor: InformationDimension
    @State private var timeInput: TimePreviewInput?
    @State private var busy = false
    @State private var error: String?
    @State private var latest: GeneratedMemory?
    @State private var discard = false
    @State private var overwrite = false
    @FocusState private var focused: String?
    @Environment(\.journalCareMode) private var care
    init(draft: GeneratedMemory, api: any MemoryAPI, onCancel: @escaping () -> Void, onUpdated: @escaping (GeneratedMemory) -> Void) {
        self.draft = draft; self.api = api; self.onCancel = onCancel; self.onUpdated = onUpdated
        _title = State(initialValue: draft.memory.title); _text = State(initialValue: draft.memory.content)
        _time = State(initialValue: MemoryEdit(draft.memory).time)
        _timeAnchor = State(initialValue: draft.timeReviewFrom ?? MemoryEdit(draft.memory).time)
    }
    private var changed: Bool { title != draft.memory.title || text != draft.memory.content || time != MemoryEdit(draft.memory).time }
    var body: some View {
        NavigationStack {
            Form {
                Section("标题") { TextField("回忆标题", text: $title).focused($focused, equals: "title").accessibilityIdentifier("draft.title") }
                Section("正文") { TextEditor(text: $text).focused($focused, equals: "body").frame(minHeight: 240).accessibilityIdentifier("draft.body") }
                Section("时间") {
                    TimeDimensionEditor(value: $time, identifier: "draft.time")
                    Button { openTimePreview() } label: { Label("核对标题与正文中的时间", systemImage: "text.badge.checkmark").frame(minHeight: 44) }
                        .disabled(!timeValid || busy || latest != nil).accessibilityIdentifier("draft.timePreview")
                    Text("修改时间后，可逐项选择对应文字。原聊天会保留；重新生成也会保留已确认的手改时间。")
                        .font(.footnote).foregroundStyle(JournalTheme.ink2)
                }
                Section { Text("你的修改会直接保留，确认保存后成为正式回忆。").foregroundStyle(JournalTheme.muted) }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                if let latest {
                    Section("最新草稿 · 本机修改仍保留在上方") {
                        Text(latest.memory.title).font(.headline)
                        Text(latest.memory.content)
                        Text("时间：" + latest.memory.dateLabel)
                        Button("核对后保存本机修改") { overwrite = true }.accessibilityIdentifier("draft.resolveConflict")
                    }
                }
            }.disabled(busy).scrollDismissesKeyboard(.interactively).scrollContentBackground(.hidden).background(JournalTheme.paper)
                .navigationTitle("编辑草稿").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") { if changed { discard = true } else { onCancel() } }.disabled(busy) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保留修改") { focused = nil; Task { await save(draft) } }
                            .disabled(busy || latest != nil || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !timeValid || title.count > 200 || text.count > 100000 || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("draft.keepEdits")
                    }
                }
                .overlay { if busy { ProgressView("正在保留修改…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
                .alert("放弃本次修改？", isPresented: $discard) { Button("继续编辑", role: .cancel) {} ; Button("放弃修改", role: .destructive, action: onCancel) } message: { Text("草稿原有内容会保留。") }
                .alert("保存本机修改到最新草稿？", isPresented: $overwrite) {
                    Button("继续核对", role: .cancel) {}; Button("保存我的修改") { if let latest { Task { await save(latest) } } }
                } message: { Text("将用上方编辑的标题、正文和时间替换最新草稿。其他设备的新修改请先核对。") }
        }.font(care ? CareTheme.font() : .body).environment(\.defaultMinListRowHeight, care ? 64 : 44)
            .interactiveDismissDisabled(changed || busy)
            .sheet(item: $timeInput) { input in
                    TimeLinkageSheet(input: input, load: { try await api.previewDraftTime(latest ?? draft, input: input) }, apply: { captured, preview, selected in
                        guard title == captured.title, text == captured.content, time == captured.newTime else { throw APIError.server("编辑内容已变化，请重新核对时间。") }
                        let result = try preview.applying(selected, to: captured)
                        title = result.0; text = result.1; timeAnchor = time
                    })
            }
            .task { if draft.timeReviewFrom != nil { openTimePreview() } }
    }
    private var timeValid: Bool { time.status == .missing || !(time.value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    private func openTimePreview() {
        focused = nil
        timeInput = TimePreviewInput(title: title, content: text, oldTime: timeAnchor, newTime: time)
    }
    private func save(_ base: GeneratedMemory) async {
        busy = true; error = nil
        defer { busy = false }
        do { onUpdated(try await api.editDraft(base, title: title, content: text, time: time)) }
        catch {
            self.error = error.localizedDescription
            if isVersionConflict(error) {
                do { latest = try await api.getDraft(id: draft.draftID) }
                catch { self.error = "读取最新草稿失败，修改仍保留。请重试：" + error.localizedDescription }
            }
        }
    }
}

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
        Group {
            if care { careBody } else { ordinaryBody }
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
    private var ordinaryBody: some View {
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
        }
    }
    private var careBody: some View {
        NavigationStack {
            VStack(spacing: 0) {
                CareToolbar(title: "修改草稿", backTitle: "取消") {
                    if changed { discard = true } else { onCancel() }
                }.disabled(busy)
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        VStack(alignment: .leading, spacing: 12) {
                            careSectionTitle("标题")
                            TextField("回忆标题", text: $title).focused($focused, equals: "title")
                                .font(CareTheme.font(24)).foregroundStyle(CareTheme.ink)
                                .accessibilityIdentifier("draft.title")
                                .padding(.horizontal, 18).padding(.vertical, 16).frame(minHeight: 68)
                                .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                                .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
                        }
                        VStack(alignment: .leading, spacing: 12) {
                            careSectionTitle("正文")
                            TextEditor(text: $text).focused($focused, equals: "body")
                                .font(CareTheme.font(22)).foregroundStyle(CareTheme.ink).lineSpacing(8)
                                .frame(minHeight: 260).scrollContentBackground(.hidden).padding(12)
                                .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                                .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
                                .accessibilityIdentifier("draft.body")
                        }
                        careTimeSection
                        Text("你的修改会直接保留，确认保存后成为正式回忆。")
                            .font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
                            .fixedSize(horizontal: false, vertical: true)
                        if let error { CareError(message: error) }
                        if let latest { careConflict(latest) }
                    }.padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 20)
                }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively).disabled(busy)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                CareButton(title: "保留修改", symbol: "checkmark", loading: busy, disabled: cannotKeepEdits) {
                    focused = nil; Task { await save(draft) }
                }.accessibilityIdentifier("draft.keepEdits").careDock()
            }
            .carePage().tint(CareTheme.accent).toolbar(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("收起键盘") { focused = nil }.accessibilityIdentifier("draft.dismissKeyboard")
                }
            }
            .overlay { if busy { CareBusyOverlay(text: "正在保留修改…") } }
            .alert("放弃本次修改？", isPresented: $discard) { Button("继续编辑", role: .cancel) {} ; Button("放弃修改", role: .destructive, action: onCancel) } message: { Text("草稿原有内容会保留。") }
            .alert("保存本机修改到最新草稿？", isPresented: $overwrite) {
                Button("继续核对", role: .cancel) {}; Button("保存我的修改") { if let latest { Task { await save(latest) } } }
            } message: { Text("将用上方编辑的标题、正文和时间替换最新草稿。其他设备的新修改请先核对。") }
        }
    }
    private var cannotKeepEdits: Bool {
        busy || latest != nil || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !timeValid || title.count > 200 || text.count > 100000 || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    private func careSectionTitle(_ title: String) -> some View {
        Text(title).font(CareTheme.font(22, bold: true)).foregroundStyle(CareTheme.ink).accessibilityAddTraits(.isHeader)
    }
    private var careTimeSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            careSectionTitle("时间")
            VStack(alignment: .leading, spacing: 14) {
                Picker("记录方式", selection: Binding(get: { time.status }, set: { status in
                    time.status = status
                    if status == .missing { time.value = nil }
                    else if status == .unknown { time.value = "记不清了" }
                    else if status == .withheld { time.value = "暂时不想说" }
                    else if time.value == nil { time.value = "" }
                })) {
                    Text("确定").tag(InformationStatus.known); Text("大概记得").tag(InformationStatus.approximate)
                    Text("记不清").tag(InformationStatus.unknown); Text("暂时不想说").tag(InformationStatus.withheld)
                    Text("待补充").tag(InformationStatus.missing)
                }.font(CareTheme.font(20)).accessibilityIdentifier("draft.time.status")
                if time.status != .missing {
                    TextField("例如：2008年夏天，或 2008-06-01", text: Binding(get: { time.value ?? "" }, set: { time.value = $0 }))
                        .font(CareTheme.font(20)).focused($focused, equals: "time")
                        .submitLabel(.done).onSubmit { focused = nil }
                        .accessibilityIdentifier("draft.time")
                        .padding(14).frame(minHeight: 64).background(CareTheme.paper, in: RoundedRectangle(cornerRadius: 18))
                        .overlay { RoundedRectangle(cornerRadius: 18).stroke(CareTheme.border, lineWidth: 1) }
                }
                if time.user_edited == true {
                    Label("用户修改的时间", systemImage: "pencil").font(CareTheme.font(17)).foregroundStyle(CareTheme.ink2)
                }
                CareButton(title: "核对标题与正文中的时间", symbol: "text.badge.checkmark", secondary: true,
                           disabled: !timeValid || busy || latest != nil, action: openTimePreview)
                    .accessibilityIdentifier("draft.timePreview")
                Text("修改时间后，可逐项选择对应文字。原聊天会保留；重新生成也会保留已确认的手改时间。")
                    .font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true)
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading).journalCard(radius: 22, fill: CareTheme.surface)
        }
    }
    private func careConflict(_ latest: GeneratedMemory) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            careSectionTitle("最新草稿 · 本机修改仍保留在上方")
            Text(latest.memory.title).font(CareTheme.font(22, bold: true))
            Text(latest.memory.content).font(CareTheme.font(22)).lineSpacing(8)
            Text("时间：" + latest.memory.dateLabel).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
            CareButton(title: "核对后保存本机修改", symbol: "checkmark", secondary: true) { overwrite = true }
                .accessibilityIdentifier("draft.resolveConflict")
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading).journalCard(radius: 22, fill: CareTheme.surface)
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

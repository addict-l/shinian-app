import SwiftUI
import PhotosUI

struct JournalMemoryEditorView: View {
    @StateObject private var model: MemoryEditorModel
    private let api: any MemoryAPI
    let onCancel: () -> Void
    let onSaved: (MemoryEvent) -> Void
    @State private var items: [PhotosPickerItem] = []
    @State private var reading = false
    @State private var discard = false
    @State private var resolve = false
    @FocusState private var focused: String?
    init(memory: MemoryEvent, api: any MemoryAPI, onCancel: @escaping () -> Void, onSaved: @escaping (MemoryEvent) -> Void) {
        self.api = api; self.onCancel = onCancel; self.onSaved = onSaved
        _model = StateObject(wrappedValue: MemoryEditorModel(memory: memory, api: api))
    }
    var body: some View {
        NavigationStack {
            Form {
                Section("标题") { TextField("回忆标题", text: $model.edit.title).focused($focused, equals: "title").accessibilityIdentifier("memory.editTitle") }
                Section("正文") { TextEditor(text: $model.edit.content).focused($focused, equals: "body").frame(minHeight: 220).accessibilityIdentifier("memory.editBody") }
                dimension("时间", value: $model.edit.time, id: "time")
                dimension("地点", value: $model.edit.place, id: "place")
                dimension("感受", value: $model.edit.feeling, id: "feeling")
                Section("照片") {
                    ForEach(model.selected) { photo in
                        HStack {
                            MemoryPhotoView(attachment: photo, api: api).frame(width: 80, height: 80).clipped()
                            Spacer()
                            Button("移除", role: .destructive) { model.remove(id: photo.id) }.frame(minHeight: 44)
                                .accessibilityLabel("移除已保存照片").accessibilityIdentifier("memory.removePhoto.\(photo.id)")
                        }
                    }
                    ForEach(model.added) { photo in
                        HStack {
                            if let image = UIImage(data: photo.data) { Image(uiImage: image).resizable().scaledToFill().frame(width: 80, height: 80).clipped() }
                            Text("新照片"); Spacer()
                            Button("移除", role: .destructive) { model.remove(id: photo.id) }.frame(minHeight: 44)
                        }
                    }
                    PhotosPicker(selection: $items, maxSelectionCount: 9, selectionBehavior: .ordered, matching: .images) {
                        Label("添加照片", systemImage: "plus").frame(minHeight: 44)
                    }.accessibilityIdentifier("memory.addPhotos")
                    Text("照片和文字会在保存修改后一起更新。原始聊天中的照片会保留，整段删除时一并清除。").font(.footnote).foregroundStyle(JournalTheme.muted)
                }
                if let error = model.error {
                    Section { Text(error).foregroundStyle(.red); Button("读取最新版本（保留本机修改）") { Task { await model.readLatest() } } }
                }
                if let latest = model.latest {
                    Section("最新版本 · 本机修改仍保留在上方") {
                        Text(latest.title).font(.headline); Text(latest.content)
                        Text("时间：\(latest.dateLabel)\n地点：\(latest.location ?? "待补充")\n感受：\(latest.information.feeling.value ?? "待补充")\n照片：\(latest.mediaAssets.count) 张")
                        Text("核对后保存会使用本机文字、信息和照片选择，替换此最新版本。")
                        Button("核对后保存本机修改") { resolve = true }.accessibilityIdentifier("memory.resolveConflict")
                    }
                }
            }.disabled(model.busy || reading).scrollDismissesKeyboard(.interactively).scrollContentBackground(.hidden).background(JournalTheme.paper)
                .navigationTitle("编辑回忆").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("取消") {
                        if model.changed { discard = true } else { Task { await cancel() } }
                    }.disabled(model.busy || reading) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("保存修改") { focused = nil; Task { if let result = await model.save() { onSaved(result) } } }
                            .disabled(!model.edit.isValid || model.busy || reading || model.latest != nil).accessibilityIdentifier("memory.saveEdits")
                    }
                }
                .overlay { if model.busy || reading { ProgressView(reading ? "正在读取照片…" : "正在处理…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
                .alert("放弃本次修改？", isPresented: $discard) {
                    Button("继续编辑", role: .cancel) {}; Button("放弃修改", role: .destructive) { Task { await cancel() } }
                } message: { Text("已保存的回忆不会改变，这次新选的照片也不会加入回忆。") }
                .alert("用本机修改更新最新版本？", isPresented: $resolve) {
                    Button("继续核对", role: .cancel) {}; Button("保存我的修改") {
                        model.acceptLatestVersion()
                        Task { if let result = await model.save() { onSaved(result) } }
                    }
                } message: { Text("请确认已核对其他设备的修改。若再次发生版本变化，仍会保留本机内容并提示核对。") }
        }.interactiveDismissDisabled(model.changed || model.busy || reading)
            .onChange(of: items) { _, values in
                guard !values.isEmpty else { return }; reading = true
                Task {
                    for item in values {
                        do {
                            guard let data = try await item.loadTransferable(type: Data.self) else { throw APIError.server("无法读取照片") }
                            model.append(try PhotoCompression.compress(data))
                        } catch { model.error = error.localizedDescription }
                    }
                    items = []; reading = false
                }
            }
    }
    private func cancel() async { if await model.cancel() { onCancel() } }
    private func dimension(_ title: String, value: Binding<InformationDimension>, id: String) -> some View {
        Section(title) {
            Picker("记录方式", selection: Binding(get: { value.wrappedValue.status }, set: { status in
                value.wrappedValue.status = status
                value.wrappedValue.source_message_ids = []
                if status == .missing { value.wrappedValue.value = nil }
                else if (value.wrappedValue.value ?? "").isEmpty { value.wrappedValue.value = status == .unknown ? "记不清了" : status == .withheld ? "暂时不想说" : "" }
            })) {
                Text("确定").tag(InformationStatus.known); Text("大概记得").tag(InformationStatus.approximate)
                Text("记不清").tag(InformationStatus.unknown); Text("暂时不想说").tag(InformationStatus.withheld)
                Text("待补充").tag(InformationStatus.missing)
            }
            if value.wrappedValue.status != .missing {
                TextField(title == "时间" ? "例如：2008年夏天，或 2008-06-01" : "写下你的说明", text: Binding(get: { value.wrappedValue.value ?? "" }, set: { value.wrappedValue.value = $0 }))
                    .focused($focused, equals: id).accessibilityIdentifier("memory.edit.\(id)")
            }
        }
    }
}

struct MemoryPhotoView: View {
    let attachment: ChatAttachment
    let api: any MemoryAPI
    @State private var data: Data?
    @State private var error = false
    var body: some View {
        Group {
            if let data, let image = UIImage(data: data) { Image(uiImage: image).resizable().scaledToFit() }
            else if error { Button("重试照片") { Task { await load() } } }
            else { ProgressView() }
        }.task(id: attachment.id) { await load() }
    }
    private func load() async {
        error = false
        do { data = try await api.loadPhoto(attachment) } catch { self.error = true }
    }
}

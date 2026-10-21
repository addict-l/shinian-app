import SwiftUI
import PhotosUI
import PDFKit

struct JournalMemoirView: View {
    @StateObject private var model: MemoirViewModel
    @State private var step = 0
    @State private var coverPicker = false
    @State private var adjustingCover = false
    @State private var cropID: UUID?
    @State private var photoStory: MemoryEvent?
    @State private var resettingOrder = false
    @State private var library: [PhotosPickerItem] = []
    @State private var share: MemoirShareFile?
    @State private var readingPage = 1
    @State private var comparingVersions = false
    @Environment(\.scenePhase) private var scenePhase
    init(person: FamilyMember, api: any MemoirAPI, store: MemoirLocalStore) {
        _model = StateObject(wrappedValue: MemoirViewModel(person: person, api: api, store: store))
    }
    var body: some View {
        VStack(spacing: 0) {
            steps.padding(.horizontal, 24).padding(.vertical, 16)
            HStack(spacing: 8) {
                Image(systemName: model.syncLabel == "已保存" ? "checkmark.circle" : "arrow.triangle.2.circlepath")
                Text(model.syncLabel)
                Spacer()
                if model.syncLabel != "已保存" { Button("重试同步") { Task { await model.load() } }.disabled(model.busy) }
            }.font(JournalTheme.font(12)).foregroundStyle(JournalTheme.accent).padding(.horizontal, 24).padding(.bottom, 12)
            if model.conflict != nil { conflictPanel }
            if let error = model.error {
                Text(error).font(JournalTheme.font(13)).foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 24).padding(.bottom, 12)
                    .accessibilityIdentifier("memoir-error")
            }
            Group {
                if step == 0 { coverStep }
                else if step == 1 { contentStep }
                else { previewStep }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            actions.padding(.horizontal, 24).padding(.vertical, 12).background(JournalTheme.paper)
        }
        .journalPage().navigationTitle("制作回忆录").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .task { await model.load() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await model.load() } } }
        .sheet(isPresented: $coverPicker) { coverPhotos }
        .sheet(isPresented: $adjustingCover) { coverCropEditor }
        .onChange(of: model.settings.coverTemplate) { _, _ in cropID = nil; adjustingCover = false }
        .onChange(of: model.activeCover.map(\.id)) { _, ids in
            if ids.isEmpty { adjustingCover = false }
            if let cropID, !ids.contains(cropID) { self.cropID = nil }
        }
        .sheet(item: $photoStory) { story in photoOptions(story) }
        .sheet(item: $share) { item in MemoirShareView(url: item.url) }
        .sheet(isPresented: $comparingVersions) { comparison }
        .confirmationDialog("恢复时间排序会替换手动调整的顺序。", isPresented: $resettingOrder, titleVisibility: .visible) {
            Button("恢复时间排序") { model.settings.ordering = "time" }
            Button("取消", role: .cancel) { }
        }
        .alert("内容有更新", isPresented: $model.needsNewPreview) {
            Button("重新生成预览") { Task { await model.generatePreview() } }
            Button("稍后", role: .cancel) { }
        } message: { Text("故事或制作设置已变化。请查看重新生成的版本，再分享。当前预览仍保留。") }
    }
    private var steps: some View {
        ViewThatFits(in: .horizontal) {
        HStack(spacing: 12) {
            ForEach(Array(["封面", "内容", "整本预览"].enumerated()), id: \.offset) { index, title in
                HStack(spacing: 8) {
                    Text("\(index + 1)").font(.system(size: 12, weight: .medium)).frame(width: 24, height: 24)
                        .background(index == step ? JournalTheme.accent : JournalTheme.soft, in: Circle())
                        .foregroundStyle(index == step ? JournalTheme.surface : JournalTheme.accent)
                    Text(title).font(JournalTheme.font(13)).foregroundStyle(index == step ? JournalTheme.ink : JournalTheme.muted)
                }.fixedSize(horizontal: true, vertical: false).accessibilityElement(children: .combine).accessibilityAddTraits(index == step ? .isSelected : [])
                if index < 2 { Rectangle().fill(JournalTheme.line).frame(height: 1) }
            }
        }
        Text("第 \(step + 1) / 3 步 · \(["封面", "内容", "整本预览"][step])").font(JournalTheme.font(14, medium: true))
        }
    }
    private var coverStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("为这些故事，做一本书").font(JournalTheme.story(24))
                VStack(alignment: .leading, spacing: 10) {
                    Text("回忆录名称").font(JournalTheme.font(14, medium: true))
                    TextField("例如：陈建国的回忆录", text: $model.settings.title, axis: .vertical)
                        .textFieldStyle(.roundedBorder).accessibilityIdentifier("memoir-title")
                    Text("副标题（选填）").font(JournalTheme.font(14, medium: true)).padding(.top, 6)
                    TextField("写一句想留在封面上的话", text: $model.settings.subtitle, axis: .vertical).textFieldStyle(.roundedBorder)
                    if !model.settings.valid { Text("书名需为 1–200 字，副标题最多 300 字。").font(JournalTheme.font(12)).foregroundStyle(.red) }
                }
                Picker("封面样式", selection: $model.settings.coverTemplate) {
                    ForEach(MemoirCover.allCases, id: \.self) { Text($0.title).tag($0) }
                }.pickerStyle(.segmented).accessibilityIdentifier("memoir-template")
                if model.settings.coverTemplate != .text {
                    JournalButton(title: "选择／更换封面照片", secondary: true) { coverPicker = true }
                        .accessibilityIdentifier("memoir-cover-photos")
                    if model.invalidCover { Text("选择封面照片；原故事照片被删除后，需要重新选择。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.accent) }
                    if !model.activeCover.isEmpty {
                        Button { adjustingCover = true } label: {
                            Label("调整照片取景", systemImage: "crop").frame(maxWidth: .infinity, minHeight: 44)
                        }.foregroundStyle(JournalTheme.accent).accessibilityIdentifier("memoir-cover-crop")
                    }
                }
                VStack(spacing: 16) {
                    coverImage.accessibilityIdentifier("memoir-cover-preview")
                    Text("A5 竖版 · 电子阅读与打印").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                }.padding(.horizontal, 28)
            }.padding(24)
        }.scrollIndicators(.hidden)
    }
    private var coverImage: some View {
        Image(uiImage: MemoirPDFRenderer.coverImage(settings: model.settings, personName: model.person.name, photos: model.thumbnails))
            .resizable().aspectRatio(148 / 210, contentMode: .fit)
            .overlay(Rectangle().stroke(JournalTheme.line, lineWidth: 1))
            .accessibilityLabel("\(model.settings.coverTemplate.title)封面预览，\(model.settings.title)")
    }
    private var coverCropEditor: some View {
        NavigationStack {
            GeometryReader { geometry in
                VStack(spacing: 16) {
                    coverImage
                        .frame(width: max(1, min(geometry.size.width - 48, geometry.size.height * 0.4 * 148 / 210)))
                        .accessibilityIdentifier("memoir-crop-preview")
                        .gesture(DragGesture().onChanged { value in
                            guard let index = cropIndex else { return }
                            var photo = cropStart ?? model.settings.coverPhotos[index]; cropStart = photo
                            photo.x = max(-1, min(1, photo.x + value.translation.width / 120))
                            photo.y = max(-1, min(1, photo.y + value.translation.height / 160))
                            model.settings.coverPhotos[index] = photo
                        }.onEnded { _ in cropStart = nil })
                        .simultaneousGesture(MagnificationGesture().onChanged { value in
                            guard let index = cropIndex else { return }
                            if zoomStart == nil { zoomStart = model.settings.coverPhotos[index].zoom }
                            model.settings.coverPhotos[index].zoom = max(1, min(4, zoomStart! * value))
                        }.onEnded { _ in zoomStart = nil })
                    ScrollView { cropControls.padding(.horizontal, 24).padding(.bottom, 24) }
                }.frame(maxWidth: .infinity).padding(.top, 16)
            }
            .background(JournalTheme.paper).navigationTitle("调整照片取景").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) {
                Button("完成") { adjustingCover = false }.accessibilityIdentifier("memoir-crop-done")
            } }
        }
        .onDisappear { cropStart = nil; zoomStart = nil }
    }
    @State private var cropStart: MemoirCoverPhoto?
    @State private var zoomStart: Double?
    private var cropIndex: Int? { model.settings.coverPhotos.firstIndex { $0.id == (cropID ?? model.activeCover.first?.id) } }
    private var cropControls: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("调整照片取景").font(JournalTheme.font(15, medium: true))
            HStack {
                ForEach(model.activeCover) { photo in
                    Button { cropID = photo.id } label: {
                        thumbnail(photo.id).frame(width: 58, height: 58).clipped()
                            .overlay(RoundedRectangle(cornerRadius: 6).stroke(photo.id == (cropID ?? model.activeCover.first?.id) ? JournalTheme.accent : JournalTheme.line, lineWidth: 2))
                    }.accessibilityLabel("调整第 \((model.activeCover.firstIndex { $0.id == photo.id } ?? 0) + 1) 张封面照片")
                }
            }
            if let index = cropIndex {
                cropSlider("缩放", value: $model.settings.coverPhotos[index].zoom, range: 1...4)
                cropSlider("左右位置", value: $model.settings.coverPhotos[index].x, range: -1...1)
                cropSlider("上下位置", value: $model.settings.coverPhotos[index].y, range: -1...1)
                HStack {
                    Button("重置取景") {
                        model.settings.coverPhotos[index].x = 0; model.settings.coverPhotos[index].y = 0; model.settings.coverPhotos[index].zoom = 1
                    }.frame(minHeight: 44)
                    Spacer()
                    if index > 0 { Button("前移") { model.settings.coverPhotos.swapAt(index, index - 1) }.frame(minWidth: 44, minHeight: 44) }
                    Button("移除") { model.settings.coverPhotos.remove(at: index); cropID = nil }.frame(minHeight: 44)
                }.font(JournalTheme.font(13))
            }
            Text("可在上方封面中拖动或双指缩放，也可使用滑块。故事中的照片不会被裁剪。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
        }
    }
    private func cropSlider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>) -> some View {
        HStack { Text(title).font(JournalTheme.font(12)).frame(width: 64, alignment: .leading); Slider(value: value, in: range).accessibilityLabel(title) }
    }
    private var contentStep: some View {
        List {
            Section {
                Picker("正文字号", selection: $model.settings.textSize) {
                    Text("大字 · 16 pt").tag(16); Text("标准 · 14 pt").tag(14)
                }
                HStack {
                    Text(model.settings.ordering == "manual" ? "手动顺序" : "按故事时间排序")
                    Spacer()
                    Button("恢复时间排序") { resettingOrder = true }.disabled(model.settings.ordering == "time")
                }.font(JournalTheme.font(13))
                Text("全部 \(model.stories.count) 段已保存回忆都会收录。每篇另起页，照片跟在正文之后。")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
            }
            Section {
                ForEach(model.stories) { story in
                    VStack(alignment: .leading, spacing: 10) {
                        Text(story.title).font(JournalTheme.font(16, medium: true))
                        Text(story.dateLabel).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        HStack {
                            Button("照片 \(model.settings.selectedPhotos(story).count)/\(story.mediaAssets.count)") { photoStory = story }.frame(minHeight: 44)
                            Spacer()
                            Button { moveStory(story, offset: -1) } label: { Image(systemName: "arrow.up").frame(width: 44, height: 44) }
                                .accessibilityLabel("上移\(story.title)").disabled(model.stories.first?.id == story.id)
                            Button { moveStory(story, offset: 1) } label: { Image(systemName: "arrow.down").frame(width: 44, height: 44) }
                                .accessibilityLabel("下移\(story.title)").disabled(model.stories.last?.id == story.id)
                        }.buttonStyle(.borderless).font(JournalTheme.font(13))
                    }.padding(.vertical, 8)
                }.onMove { model.moveStory(from: $0, to: $1) }
            } header: {
                HStack { Text("故事与照片"); Spacer(); EditButton() }
            }
        }.scrollContentBackground(.hidden).listStyle(.insetGrouped)
    }
    private func moveStory(_ story: MemoryEvent, offset: Int) {
        guard let i = model.stories.firstIndex(where: { $0.id == story.id }) else { return }
        model.moveStory(from: IndexSet(integer: i), to: offset < 0 ? i - 1 : i + 2)
    }
    private var previewStep: some View {
        VStack(spacing: 12) {
            if let preview = model.preview {
                HStack { Text("第 \(readingPage) / \(preview.pageCount) 页"); Spacer(); Text("双指可缩放") }
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.horizontal, 24)
                MemoirPDFReader(url: preview.url, currentPage: $readingPage).accessibilityIdentifier("memoir-pdf")
            } else {
                Spacer(); Image(systemName: "book.closed").font(.system(size: 40)).foregroundStyle(JournalTheme.accent)
                Text(model.busy ? "正在准备照片与排版…" : "预览整本回忆录").font(JournalTheme.story(22))
                Text("封面、目录、故事和照片会排成同一份 PDF。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted)
                Spacer()
            }
            if !model.failures.isEmpty {
                ScrollView {
                    VStack(alignment: .leading) {
                        ForEach(model.failures) { item in
                            HStack {
                                Text("\(item.label) · 照片未加载").font(JournalTheme.font(12))
                                Spacer()
                                Button(item.cover ? "更换" : "取消选择") {
                                    if item.cover { step = 0; coverPicker = true }
                                    else { model.togglePhoto(item.id) }
                                }.frame(minHeight: 44)
                            }
                        }
                    }.padding(.horizontal, 24)
                }.frame(maxHeight: 140)
            }
        }
    }
    private var actions: some View {
        HStack(spacing: 12) {
            if step > 0 { Button("上一步") { step -= 1 }.font(JournalTheme.font(14)).frame(minWidth: 64, minHeight: 54) }
            if step < 2 {
                JournalButton(title: step == 0 ? "下一步：整理内容" : "生成整本预览", loading: model.busy,
                    disabled: !model.settings.valid || model.snapshot == nil || model.conflict != nil || model.stories.isEmpty) {
                    if step == 0 { step = 1 } else { step = 2; Task { await model.generatePreview() } }
                }
            } else {
                JournalButton(title: model.preview == nil || !model.failures.isEmpty ? "重试生成预览" : "重新生成", secondary: true, loading: model.busy) {
                    Task { await model.generatePreview() }
                }
                if model.preview != nil {
                    JournalButton(title: "分享／存到文件", loading: model.busy, disabled: model.conflict != nil) {
                        Task { if let url = await model.verifiedShareURL() { share = MemoirShareFile(url: url) } }
                    }.accessibilityIdentifier("memoir-share")
                }
            }
        }
    }
    private var conflictPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("另一台设备调整了回忆录").font(JournalTheme.font(15, medium: true))
            if let remote = model.conflict {
                Text("本机：\(model.settings.title) · \(model.settings.coverTemplate.title)\n云端：\(remote.settings.title) · \(remote.settings.coverTemplate.title)").font(JournalTheme.font(13))
                Text("本机顺序：\(orderSummary(model.settings, stories: model.snapshot?.stories ?? []))\n云端顺序：\(orderSummary(remote.settings, stories: remote.stories))")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                Text("封面照片、取景、副标题和照片选择也会使用所选版本。").font(JournalTheme.font(12))
                Button("查看完整差异") { comparingVersions = true; Task { await model.loadThumbnails() } }.frame(minHeight: 44)
            }
            HStack {
                Button("使用云端版本") { model.chooseCloud() }.frame(minHeight: 44)
                Spacer()
                Button("用本机设置覆盖") { Task { await model.chooseLocal() } }.frame(minHeight: 44)
            }.font(JournalTheme.font(13))
        }.padding(16).background(JournalTheme.soft, in: RoundedRectangle(cornerRadius: 14)).padding(.horizontal, 24).padding(.bottom, 12)
    }
    private func orderSummary(_ settings: MemoirSettings, stories: [MemoryEvent]) -> String {
        settings.ordered(stories).prefix(3).map(\.title).joined(separator: " → ") + (stories.count > 3 ? "…" : "")
    }
    private var comparison: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    comparisonVersion("本机设置", settings: model.settings, stories: model.snapshot?.stories ?? [])
                    if let cloud = model.conflict { comparisonVersion("云端设置", settings: cloud.settings, stories: cloud.stories) }
                }.padding(24)
            }.navigationTitle("核对制作设置").toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { comparingVersions = false } } }
        }
    }
    private func comparisonVersion(_ title: String, settings: MemoirSettings, stories: [MemoryEvent]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(JournalTheme.font(20, medium: true))
            Image(uiImage: MemoirPDFRenderer.coverImage(settings: settings, personName: model.person.name, photos: model.thumbnails))
                .resizable().scaledToFit().frame(maxHeight: 300)
            Text("书名：\(settings.title)\n副标题：\(settings.subtitle.isEmpty ? "未填写" : settings.subtitle)\n封面：\(settings.coverTemplate.title)\n正文字号：\(settings.textSize) pt").font(JournalTheme.font(14))
            ForEach(settings.ordered(stories)) { story in
                Text("\((settings.ordered(stories).firstIndex { $0.id == story.id } ?? 0) + 1). \(story.title)\n照片顺序：\(photoOrderLabel(settings, story: story))")
                    .font(JournalTheme.font(13))
            }
            ForEach(settings.coverPhotos) { photo in
                Text("封面第 \((settings.coverPhotos.firstIndex { $0.id == photo.id } ?? 0) + 1) 张：缩放 \(photo.zoom, specifier: "%.2f")，左右 \(photo.x, specifier: "%.2f")，上下 \(photo.y, specifier: "%.2f")")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
            }
        }
    }
    private func photoOrderLabel(_ settings: MemoirSettings, story: MemoryEvent) -> String {
        let labels = settings.selectedPhotos(story).map { photo in String((story.mediaAssets.firstIndex { $0.id == photo.id } ?? 0) + 1) }
        return labels.isEmpty ? "未选照片" : labels.joined(separator: "、")
    }
    @ViewBuilder private func thumbnail(_ id: UUID) -> some View {
        if let image = model.thumbnails[id] { Image(uiImage: image).resizable().scaledToFit() }
        else { Image(systemName: "photo").foregroundStyle(JournalTheme.muted).frame(maxWidth: .infinity, maxHeight: .infinity).background(JournalTheme.soft) }
    }
    private var coverPhotos: some View {
        NavigationStack {
            List {
                Section {
                    PhotosPicker(selection: $library, maxSelectionCount: model.settings.coverTemplate.limit, matching: .images) {
                        Label("从手机相册选择", systemImage: "photo.on.rectangle").frame(minHeight: 44)
                    }.onChange(of: library) { _, items in
                        Task {
                            for item in items {
                                do {
                                    guard let data = try await item.loadTransferable(type: Data.self) else { throw APIError.server("照片无法读取，请重新选择。") }
                                    model.importCover(data)
                                } catch { model.error = error.localizedDescription }
                            }
                            library = []; coverPicker = false
                        }
                    }
                    Text("相册封面照片独立保存，不会自动加入故事。拼贴最多三张。")
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                }
                ForEach(model.stories) { story in
                    Section(story.title) {
                        ForEach(story.mediaAssets) { photo in
                            Button {
                                model.addCover(MemoirCoverPhoto(id: photo.id, sourceMemoryId: story.id))
                                if model.settings.coverTemplate == .photo { coverPicker = false }
                            } label: {
                                HStack { thumbnail(photo.id).frame(width: 72, height: 64); Text("选择这张照片").font(JournalTheme.font(14)); Spacer()
                                    if model.activeCover.contains(where: { $0.id == photo.id }) { Image(systemName: "checkmark.circle.fill") }
                                }
                            }
                        }
                    }
                }
            }.navigationTitle("封面照片").toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { coverPicker = false } } }
        }
    }
    private func photoOptions(_ story: MemoryEvent) -> some View {
        NavigationStack {
            List {
                Section { Text("选中的照片排在这篇故事之后，保留完整画面。取消选择只影响回忆录。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted) }
                ForEach(model.settings.photos(story)) { photo in
                    HStack {
                        thumbnail(photo.id).frame(width: 72, height: 72)
                        VStack(alignment: .leading) {
                        Toggle("收录照片 \((model.settings.photos(story).firstIndex { $0.id == photo.id } ?? 0) + 1)", isOn: Binding(
                            get: { !model.settings.excludedPhotoIds.contains(photo.id) }, set: { _ in model.togglePhoto(photo.id) }))
                            HStack(spacing: 16) {
                                Button("上移") { movePhoto(photo, story: story, offset: -1) }.disabled(model.settings.photos(story).first?.id == photo.id)
                                Button("下移") { movePhoto(photo, story: story, offset: 1) }.disabled(model.settings.photos(story).last?.id == photo.id)
                            }.font(JournalTheme.font(12)).buttonStyle(.borderless).frame(minHeight: 44)
                        }
                    }
                }.onMove { model.movePhoto(story: story, from: $0, to: $1) }
                if story.mediaAssets.isEmpty { Text("这篇故事没有照片，正文仍会完整收录。") }
            }.environment(\.editMode, .constant(.active))
                .navigationTitle("故事照片").toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { photoStory = nil } } }
        }
    }
    private func movePhoto(_ photo: ChatAttachment, story: MemoryEvent, offset: Int) {
        guard let i = model.settings.photos(story).firstIndex(where: { $0.id == photo.id }) else { return }
        model.movePhoto(story: story, from: IndexSet(integer: i), to: offset < 0 ? i - 1 : i + 2)
    }
}
struct MemoirShareFile: Identifiable { let id = UUID(); let url: URL }
struct MemoirShareView: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: [url], applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) { }
}
struct MemoirPDFReader: UIViewRepresentable {
    let url: URL
    @Binding var currentPage: Int
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> PDFView {
        let view = PDFView(); view.autoScales = true; view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical; view.backgroundColor = .clear
        context.coordinator.observe(view); return view
    }
    func updateUIView(_ view: PDFView, context: Context) {
        context.coordinator.parent = self
        if context.coordinator.url != url {
            view.document = PDFDocument(url: url); view.autoScales = true; context.coordinator.url = url
        }
    }
    final class Coordinator {
        var parent: MemoirPDFReader; var url: URL?; var observer: NSObjectProtocol?
        init(_ parent: MemoirPDFReader) { self.parent = parent }
        func observe(_ view: PDFView) {
            observer = NotificationCenter.default.addObserver(forName: .PDFViewPageChanged, object: view, queue: .main) { [weak self, weak view] _ in
                guard let self, let view, let page = view.currentPage, let document = view.document else { return }
                self.parent.currentPage = document.index(for: page) + 1
            }
        }
        deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }
    }
}

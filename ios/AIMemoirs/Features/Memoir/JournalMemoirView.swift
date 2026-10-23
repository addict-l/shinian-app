import SwiftUI
import PhotosUI
import PDFKit

struct JournalMemoirView: View {
    @StateObject private var model: MemoirViewModel
    @State private var step = 0
    @Environment(\.dismiss) private var dismiss
    @State private var coverPicker = false
    @State private var editorPanel: MemoirEditorPanel?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
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
            JournalNavBar(title: "制作回忆录") {
                JournalRoundButton(icon: "x", label: "关闭回忆录") { dismiss() }
            } trailing: { syncStatus }
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            steps.padding(.horizontal, JournalTheme.gutter).padding(.top, 2).padding(.bottom, 14)
            if model.conflict != nil { conflictPanel }
            if let error = model.error {
                Text(error).font(JournalTheme.font(13)).foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 24).padding(.bottom, 12)
                    .accessibilityIdentifier("memoir-error")
                if model.conflict == nil {
                    Button("重试同步") { Task { await model.load() } }.frame(minHeight: 44).accessibilityIdentifier("memoir-sync-retry")
                }
            }
            Group {
                if step == 0 { coverStep }
                else if step == 1 { contentStep }
                else { previewStep }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            actions.padding(.horizontal, 24).padding(.vertical, 12).background(JournalTheme.paper)
        }
        .journalPage()
        .task { await model.load() }
        .onChange(of: model.preview?.url) { _, _ in readingPage = 1 }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await model.load() } } }
        .sheet(isPresented: $coverPicker) { coverPhotos }
        .sheet(item: $editorPanel) { panel in editor(panel) }
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
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                Text("第 \(step + 1) 步 · \(["封面", "故事与照片", "整本预览"][step])")
                    .font(.headline).frame(maxWidth: .infinity, alignment: .leading)
            } else {
                HStack(spacing: 8) {
                    ForEach(0..<3) { index in
                        if index > 0 { Rectangle().fill(JournalTheme.line).frame(maxWidth: 24).frame(height: 1).accessibilityHidden(true) }
                        HStack(spacing: 6) {
                            Text(String(index + 1)).font(JournalTheme.font(11, medium: true))
                                .frame(width: 23, height: 23)
                                .foregroundStyle(index == step ? JournalTheme.surface : JournalTheme.ink2)
                                .background(index == step ? JournalTheme.accentDeep : JournalTheme.paper, in: Circle())
                                .overlay { Circle().stroke(index == step ? JournalTheme.accentDeep : JournalTheme.line, lineWidth: 1) }
                            Text(["封面", "故事与照片", "整本预览"][index]).font(JournalTheme.font(12, medium: index == step))
                                .foregroundStyle(index == step ? JournalTheme.accentDeep : JournalTheme.ink2)
                        }.accessibilityElement(children: .combine).accessibilityAddTraits(index == step ? .isSelected : [])
                    }
                }.frame(maxWidth: .infinity).frame(minHeight: 44)
            }
        }.accessibilityIdentifier("memoir-stepper")
    }
    private var coverStep: some View {
        ScrollView {
            VStack(spacing: 0) {
                bookCover.padding(.top, 20)
                Text(model.person.name + "的回忆录 · A5 竖版")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
                    .multilineTextAlignment(.center).padding(.top, 20).padding(.bottom, 30)
                VStack(spacing: 0) {
                    MemoirSettingRow(icon: "book", title: "封面样式", value: model.settings.coverTemplate.editorTitle) { editorPanel = .style }
                        .accessibilityIdentifier("memoir-edit-style")
                    rowDivider
                    MemoirSettingRow(icon: "image", title: "封面照片", detail: model.settings.coverTemplate == .text ? "素雅封面使用纯文字" : "更换照片与调整取景") { coverPicker = true }
                        .accessibilityIdentifier("memoir-cover-photos")
                    rowDivider
                    MemoirSettingRow(icon: "edit", title: "书名与副标题", detail: model.settings.title) { editorPanel = .name }
                        .accessibilityIdentifier("memoir-edit-name")
                }.background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                    .overlay { RoundedRectangle(cornerRadius: 18).stroke(JournalTheme.line, lineWidth: 1) }
                    .accessibilityElement(children: .contain).accessibilityIdentifier("memoir-editing-group")
                if model.invalidCover {
                    Text("请选择可用的封面照片，或改用素雅封面。")
                        .font(.footnote).foregroundStyle(JournalTheme.ink2).padding(.top, 12)
                }
                if model.stories.isEmpty && !model.busy {
                    Text("先保存一段回忆，就可以制作这本书。")
                        .font(.footnote).foregroundStyle(JournalTheme.ink2).padding(.top, 12)
                }
            }.padding(.horizontal, 24).padding(.bottom, 24)
        }.scrollIndicators(.hidden)
    }
    private var rowDivider: some View { JournalTheme.line.frame(height: 1).padding(.horizontal, 18) }
    private var syncStatus: some View {
        HStack(spacing: 4) {
            if model.busy { ProgressView().controlSize(.mini) }
            Text(model.syncLabel).lineLimit(1).minimumScaleFactor(0.8).accessibilityIdentifier("memoir-sync-status")
        }.font(JournalTheme.font(11)).foregroundStyle(JournalTheme.ink2).frame(maxWidth: 92, alignment: .trailing)
    }
    private func editor(_ panel: MemoirEditorPanel) -> some View {
        NavigationStack {
            Group {
                switch panel {
                case .style:
                    ScrollView {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 90), spacing: 16)], spacing: 20) {
                            ForEach([MemoirCover.photo, .collage, .text], id: \.self) { template in
                                Button { model.settings.coverTemplate = template } label: {
                                    VStack(spacing: 12) {
                                        Image(uiImage: MemoirPDFRenderer.coverImage(settings: templateSettings(template), personName: model.person.name, photos: model.thumbnails))
                                            .resizable().aspectRatio(148 / 210, contentMode: .fit)
                                            .overlay { RoundedRectangle(cornerRadius: 4).stroke(model.settings.coverTemplate == template ? JournalTheme.accentDeep : JournalTheme.line, lineWidth: 2) }
                                        HStack(spacing: 4) {
                                            Text(template.editorTitle)
                                            if model.settings.coverTemplate == template { Image(systemName: "checkmark.circle.fill") }
                                        }.font(.subheadline).foregroundStyle(JournalTheme.ink)
                                    }.padding(6)
                                }.buttonStyle(.plain).accessibilityIdentifier("memoir.template.\(template.rawValue)")
                                    .accessibilityAddTraits(model.settings.coverTemplate == template ? .isSelected : [])
                            }
                        }.padding(24)
                        Text("书名、照片和取景设置会保留。素雅封面使用纯文字。").font(.footnote).foregroundStyle(JournalTheme.ink2).padding(.horizontal, 24)
                    }
                case .name:
                    Form {
                        Section("书名") { TextField("回忆录名称", text: $model.settings.title).accessibilityIdentifier("memoir-title") }
                        Section("副标题（选填）") { TextField("写一句想留在封面上的话", text: $model.settings.subtitle).accessibilityIdentifier("memoir-subtitle") }
                        if !model.settings.valid { Section { Text("请填写书名（最多 200 字），副标题最多 300 字。").foregroundStyle(JournalTheme.danger) } }
                    }.scrollDismissesKeyboard(.interactively).scrollContentBackground(.hidden)
                case .reading:
                    Form {
                        Section("正文字号") {
                            Picker("字号", selection: $model.settings.textSize) { Text("大字 · 16 pt").tag(16); Text("标准 · 14 pt").tag(14) }
                                .accessibilityIdentifier("memoir-text-size")
                            Text("字号调整后，需要重新生成整本预览。").font(.footnote).foregroundStyle(JournalTheme.ink2)
                        }
                    }.scrollContentBackground(.hidden)
                }
            }.background(JournalTheme.paper).navigationTitle(panel.title).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { editorPanel = nil } } }
        }
    }
    private func templateSettings(_ template: MemoirCover) -> MemoirSettings { var result = model.settings; result.coverTemplate = template; return result }
    private var bookCover: some View {
        coverImage.frame(width: 200, height: 200 * 210 / 148)
            .overlay(alignment: .trailing) { Color(hex: 0xE2CDB2).opacity(0.5).frame(width: 5) }
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 4, bottomLeadingRadius: 4, bottomTrailingRadius: 14, topTrailingRadius: 14))
            .shadow(color: Color(hex: 0x785028).opacity(0.25), radius: 15, x: 0, y: 18)
            .accessibilityIdentifier("memoir-cover-preview")
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
            Text("可在上方封面中拖动或双指缩放，也可使用滑块。故事中的照片不会被裁剪。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
        }
    }
    private func cropSlider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>) -> some View {
        HStack { Text(title).font(JournalTheme.font(12)).frame(width: 64, alignment: .leading); Slider(value: value, in: range).accessibilityLabel(title) }
    }
    private var contentStep: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                ViewThatFits(in: .horizontal) {
                    HStack { Text("全部 \(model.stories.count) 篇回忆").font(JournalTheme.story(20)); Spacer(); readingSettingsButton }
                    VStack(alignment: .leading, spacing: 8) { Text("全部 \(model.stories.count) 篇回忆").font(JournalTheme.story(20)); readingSettingsButton }
                }
                HStack {
                    Text(model.settings.ordering == "manual" ? "手动顺序" : "按故事时间排序")
                    Spacer(minLength: 8)
                    Button("恢复时间排序") { resettingOrder = true }.buttonStyle(.borderless).frame(minHeight: 44).disabled(model.settings.ordering == "time").accessibilityIdentifier("memoir-restore-order")
                }.font(.subheadline).foregroundStyle(JournalTheme.ink2)
                Text("每篇回忆完整收录。可调整章节和照片的顺序。").font(.footnote).foregroundStyle(JournalTheme.ink2)
                }.padding(.vertical, 8)
            }.listRowBackground(Color.clear).listRowSeparator(.hidden)
            Section {
                ForEach(Array(model.stories.enumerated()), id: \.element.id) { index, story in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .top, spacing: 14) {
                            Text(String(format: "%02d", index + 1)).font(JournalTheme.story(20)).foregroundStyle(JournalTheme.accentDeep).frame(minWidth: 28)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(story.title).font(JournalTheme.story(18)).fixedSize(horizontal: false, vertical: true)
                                Text(story.dateLabel).font(.footnote).foregroundStyle(JournalTheme.ink2)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                        let photos = model.settings.selectedPhotos(story)
                        if !photos.isEmpty {
                            ScrollView(.horizontal) {
                                HStack(spacing: 8) { ForEach(photos) { photo in thumbnail(photo.id).frame(width: 72, height: 56).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 6)).clipped() } }
                            }.scrollIndicators(.hidden).padding(.leading, 42)
                        }
                        ViewThatFits(in: .horizontal) {
                            HStack { storyPhotosButton(story); Spacer(minLength: 0); storyMoveButtons(story) }
                            VStack(alignment: .leading, spacing: 8) { storyPhotosButton(story); storyMoveButtons(story) }
                        }.padding(.leading, 42)
                    }.padding(.vertical, 16).accessibilityElement(children: .contain).accessibilityIdentifier("memoir.chapter.\(story.id)")
                }.onMove { model.moveStory(from: $0, to: $1) }
            } header: { HStack { Text("章节顺序"); Spacer(); EditButton().accessibilityIdentifier("memoir-edit-order") } }
                .listRowBackground(Color.clear)
        }.scrollContentBackground(.hidden).listStyle(.plain).contentMargins(.horizontal, 24)
    }
    private var readingSettingsButton: some View {
        Button("阅读设置 ›") { editorPanel = .reading }.buttonStyle(.borderless).font(.subheadline).frame(minHeight: 44).accessibilityIdentifier("memoir-reading-settings")
    }
    private func storyPhotosButton(_ story: MemoryEvent) -> some View {
        Button { photoStory = story } label: {
            Text(story.mediaAssets.isEmpty ? "没有照片 · 正文完整收录" : "\(model.settings.selectedPhotos(story).count) / \(story.mediaAssets.count) 张照片 · 选择与排序 ›")
                .font(.footnote).foregroundStyle(JournalTheme.ink2).fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
        }.buttonStyle(.borderless).accessibilityIdentifier("memoir-story-photos.\(story.id)")
    }
    private func storyMoveButtons(_ story: MemoryEvent) -> some View {
        HStack(spacing: 4) {
            Button { moveStory(story, offset: -1) } label: { Image(systemName: "arrow.up").frame(width: 44, height: 44) }
                .accessibilityIdentifier("memoir.move-up.\(story.id)").accessibilityLabel("上移\(story.title)").disabled(model.stories.first?.id == story.id)
            Button { moveStory(story, offset: 1) } label: { Image(systemName: "arrow.down").frame(width: 44, height: 44) }
                .accessibilityIdentifier("memoir.move-down.\(story.id)").accessibilityLabel("下移\(story.title)").disabled(model.stories.last?.id == story.id)
        }.buttonStyle(.borderless).foregroundStyle(JournalTheme.ink2)
    }
    private func moveStory(_ story: MemoryEvent, offset: Int) {
        guard let i = model.stories.firstIndex(where: { $0.id == story.id }) else { return }
        model.moveStory(from: IndexSet(integer: i), to: offset < 0 ? i - 1 : i + 2)
    }
    private var previewStep: some View {
        VStack(spacing: 12) {
            if let preview = model.preview {
                HStack {
                    Text("第 \(readingPage) / \(preview.pageCount) 页").accessibilityIdentifier("memoir-page-count")
                    Spacer()
                    Button("重新生成") { Task { await model.generatePreview() } }.frame(minHeight: 44).disabled(model.busy).accessibilityIdentifier("memoir-regenerate")
                }
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2).padding(.horizontal, 24)
                Text("上下翻阅 · 双指缩放").font(.footnote).foregroundStyle(JournalTheme.ink2)
                MemoirPDFReader(url: preview.url, currentPage: $readingPage).accessibilityIdentifier("memoir-pdf")
            } else {
                Spacer(); Image(systemName: "book.closed").font(.system(size: 40)).foregroundStyle(JournalTheme.accent)
                Text(model.busy ? "正在准备照片与排版…" : "预览整本回忆录").font(JournalTheme.story(22))
                Text("封面、目录、故事和照片会排成同一份 PDF。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
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
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { actionButtons }
            VStack(spacing: 8) { actionButtons }
        }
    }
    @ViewBuilder private var actionButtons: some View {
        if step > 0 {
            Button("上一步") { step -= 1 }.font(.subheadline).frame(minWidth: 64, minHeight: 44).accessibilityIdentifier("memoir-back")
        }
        if step < 2 {
            MemoirActionButton(title: step == 0 ? "下一步：整理内容" : "生成整本预览", loading: model.busy,
                disabled: !model.settings.valid || model.invalidCover || model.snapshot == nil || model.conflict != nil || model.stories.isEmpty) {
                if step == 0 { step = 1 } else { step = 2; Task { await model.generatePreview() } }
            }.accessibilityIdentifier(step == 0 ? "memoir-next" : "memoir-generate")
        } else {
            if model.preview == nil || !model.failures.isEmpty {
                MemoirActionButton(title: "重试生成预览", secondary: true, loading: model.busy) { Task { await model.generatePreview() } }
                    .accessibilityIdentifier("memoir-retry-preview")
            }
            if model.preview != nil {
                MemoirActionButton(title: "分享／存到文件", loading: model.busy, disabled: model.conflict != nil) {
                    Task { if let url = await model.verifiedShareURL() { share = MemoirShareFile(url: url) } }
                }.accessibilityIdentifier("memoir-share")
            }
        }
    }
    private var conflictPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("另一台设备调整了回忆录").font(JournalTheme.font(15, medium: true))
            if let remote = model.conflict {
                Text("本机：\(model.settings.title) · \(model.settings.coverTemplate.title)\n云端：\(remote.settings.title) · \(remote.settings.coverTemplate.title)").font(JournalTheme.font(13))
                Text("本机顺序：\(orderSummary(model.settings, stories: model.snapshot?.stories ?? []))\n云端顺序：\(orderSummary(remote.settings, stories: remote.stories))")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
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
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
            }
        }
    }
    private func photoOrderLabel(_ settings: MemoirSettings, story: MemoryEvent) -> String {
        let labels = settings.selectedPhotos(story).map { photo in String((story.mediaAssets.firstIndex { $0.id == photo.id } ?? 0) + 1) }
        return labels.isEmpty ? "未选照片" : labels.joined(separator: "、")
    }
    @ViewBuilder private func thumbnail(_ id: UUID) -> some View {
        if let image = model.thumbnails[id] { Image(uiImage: image).resizable().scaledToFit() }
        else { Image(systemName: "photo").foregroundStyle(JournalTheme.ink2).frame(maxWidth: .infinity, maxHeight: .infinity).background(JournalTheme.soft) }
    }
    private var coverPhotos: some View {
        NavigationStack {
            List {
                Section {
                    coverImage.frame(maxWidth: 170).frame(maxWidth: .infinity).padding(.vertical, 8)
                    if !model.activeCover.isEmpty {
                        Button("调整照片取景") { adjustingCover = true }.frame(minHeight: 44).accessibilityIdentifier("memoir-cover-crop")
                    }
                    if model.settings.coverTemplate == .text {
                        Text("素雅封面使用纯文字。要加入照片，请在封面样式中选择暖纸或拼贴。")
                            .font(.subheadline).foregroundStyle(JournalTheme.ink2)
                    }
                    PhotosPicker(selection: $library, maxSelectionCount: model.settings.coverTemplate.limit, matching: .images) {
                        Label("从手机相册选择", systemImage: "photo.on.rectangle").frame(minHeight: 44)
                    }.disabled(model.settings.coverTemplate == .text).onChange(of: library) { _, items in
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
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
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
                            .disabled(model.settings.coverTemplate == .text)
                            .accessibilityLabel("选择这张照片")
                            .accessibilityIdentifier("memoir.coverPhoto.\(photo.id)")
                        }
                    }
                }
            }.scrollContentBackground(.hidden).background(JournalTheme.paper).navigationTitle("封面照片").navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { coverPicker = false } } }
        }.sheet(isPresented: $adjustingCover) { coverCropEditor }
    }
    private func photoOptions(_ story: MemoryEvent) -> some View {
        NavigationStack {
            List {
                Section { Text("选中的照片排在这篇故事之后，保留完整画面。取消选择只影响回忆录。").font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2) }
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
            }.scrollContentBackground(.hidden).background(JournalTheme.paper).environment(\.editMode, .constant(.active))
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

private extension View {
    /// 回忆录表单输入框与添加人物表单同一套暖白圆角样式。
    func journalMemoirField() -> some View {
        font(JournalTheme.font(15)).padding(.horizontal, 14).padding(.vertical, 12)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
            .overlay { RoundedRectangle(cornerRadius: 16).stroke(JournalTheme.line, lineWidth: 1) }
    }
}

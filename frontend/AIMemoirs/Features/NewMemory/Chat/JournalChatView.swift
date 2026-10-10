import SwiftUI
import PhotosUI

/// 对话页面：协调输入、附件和草稿预览；远端会话与保存状态由独立 ViewModel 管理。
struct JournalChatView: View {
    let person: FamilyMember
    private let chatAPI: any ChatAPI
    let previewScreen: String?
    let onBack: () -> Void
    let onSaved: () async -> Void
    @StateObject private var model: ChatViewModel
    @StateObject private var saveModel: MemorySaveViewModel
    @StateObject private var dictation = JournalDictation()
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var messages: [ChatMessage] = []
    @State private var input = ""
    @State private var photoItems: [PhotosPickerItem] = []
    @State private var readingPhotos = false
    @State private var managingPhotos = false
    @State private var previewPhoto: ChatAttachment?
    @State private var imageData: Data?
    @State private var draft: GeneratedMemory?
    @State private var showingDraft = false
    @State private var showingEdit = false
    @State private var editText = ""
    @State private var mediaError: String?
    @FocusState private var inputFocused: Bool

    init(person: FamilyMember, chatAPI: any ChatAPI, memoryAPI: any MemoryAPI, previewScreen: String?, onBack: @escaping () -> Void, onSaved: @escaping () async -> Void) {
        self.person = person; self.chatAPI = chatAPI; self.previewScreen = previewScreen; self.onBack = onBack; self.onSaved = onSaved
        _model = StateObject(wrappedValue: ChatViewModel(api: chatAPI))
        _saveModel = StateObject(wrappedValue: MemorySaveViewModel(api: memoryAPI))
    }
    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                VStack(spacing: 5) {
                    Text("关于\(person.relationship.isEmpty ? person.name : person.relationship)").font(JournalTheme.font(16, medium: true))
                    Text(person.name).font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                }
                HStack {
                    Button(action: onBack) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                        .foregroundStyle(JournalTheme.ink).accessibilityLabel("返回人物列表").accessibilityIdentifier("newMemory.step.1")
                    Spacer()
                }
            }.frame(minHeight: 77).padding(.horizontal, 12)
            ScrollViewReader { reader in
                ScrollView {
                    VStack(alignment: .leading, spacing: 34) {
                        ForEach(messages) { message in
                            messageView(message).id(message.id)
                        }
                        if model.isLoading { ProgressView(model.progressText).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted) }
                        if let error = model.errorMessage { JournalError(message: error) { Task { if !input.isEmpty || !model.photos.isEmpty { await send() } else if messages.isEmpty { await start() } else { await generate() } } } }
                        if model.canGenerate && model.photos.isEmpty && !model.hasPendingSend {
                            VStack(spacing: 18) {
                                JournalButton(title: "整理成一段回忆", secondary: true, loading: model.isLoading) { Task { await generate() } }
                                    .accessibilityIdentifier("chat.generate")
                                Text("先生成草稿，确认后再保存。").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                            }.padding(.top, 4)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(.horizontal, 24).padding(.top, 28).padding(.bottom, 16)
                }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
                    .onChange(of: messages.count) { _, _ in withAnimation { reader.scrollTo("bottom", anchor: .bottom) } }
            }
            composer.fixedSize(horizontal: false, vertical: true)
        }
        .task { await start() }
        .onDisappear { dictation.stop() }
        .onChange(of: navigation.tab) { _, tab in if tab != .compose { dictation.stop() } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { dictation.stop() } }
        .onChange(of: dictation.transcript) { _, text in input = text }
        .alert("语音输入", isPresented: Binding(get: { dictation.errorMessage != nil }, set: { if !$0 { dictation.errorMessage = nil } })) { Button("确定") { dictation.errorMessage = nil } } message: { Text(dictation.errorMessage ?? "") }
        .onChange(of: photoItems) { _, items in
            guard !items.isEmpty else { return }
            readingPhotos = true
            Task {
                var compressed: [Data] = []
                for item in items {
                    do {
                        guard let data = try await item.loadTransferable(type: Data.self) else { throw APIError.server("照片读取失败，请重新选择。") }
                        compressed.append(try PhotoCompression.compress(data))
                    } catch { mediaError = error.localizedDescription }
                }
                do { try model.appendPhotos(compressed) } catch { mediaError = error.localizedDescription }
                photoItems = []; readingPhotos = false
            }
        }
        .sheet(item: $previewPhoto) { attachment in
            NavigationStack {
                JournalMessagePhoto(attachment: attachment, api: chatAPI, fit: true)
                    .frame(height: 400).padding().navigationTitle("讲述照片")
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("关闭") { previewPhoto = nil } } }
            }
        }
        .sheet(isPresented: $managingPhotos) {
            NavigationStack {
                selectedPhotoStrip.padding().navigationTitle("已选照片")
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { managingPhotos = false } } }
            }
        }
        .alert("照片读取失败", isPresented: Binding(get: { mediaError != nil }, set: { if !$0 { mediaError = nil } })) { Button("确定") { mediaError = nil } } message: { Text(mediaError ?? "") }
        .fullScreenCover(isPresented: $showingDraft) {
            if let draft {
                JournalMemoryReviewView(draft: draft, imageData: imageData,
                    identity: "\(person.relationship) · \(person.name)", saveModel: saveModel,
                    onBack: { showingDraft = false },
                    onEdit: { editText = draft.memory.content; showingEdit = true },
                    onSave: {
                        guard await saveModel.save(draft) else { return }
                        showingDraft = false
                        await onSaved()
                    })
                    .sheet(isPresented: $showingEdit) {
                        JournalDraftEditorView(text: $editText, loading: model.isLoading,
                            error: model.errorMessage, onCancel: { showingEdit = false },
                            onUpdate: { Task { await updateDraft() } })
                    }
            }
        }
    }
    @ViewBuilder private func messageView(_ message: ChatMessage) -> some View {
        if message.sender == .user {
            if message.attachments.isEmpty {
                HStack {
                    Spacer(minLength: 31)
                    Text(message.text).font(JournalTheme.font(15)).lineSpacing(8)
                        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(JournalTheme.soft, in: RoundedRectangle(cornerRadius: 18))
                        .accessibilityIdentifier("chat.message.text.\(message.id)")
                }
            } else {
                JournalUserMessage(message: message, api: chatAPI) { previewPhoto = $0 }
            }
        } else {
            VStack(alignment: .leading, spacing: 16) {
                Text("AI  回忆助手").font(JournalTheme.font(11, medium: true)).foregroundStyle(JournalTheme.accent)
                Text(message.text).font(JournalTheme.font(16)).lineSpacing(8).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
    private var composer: some View {
        VStack(spacing: 10) {
            if readingPhotos { ProgressView("正在读取与压缩照片…") }
            VStack(spacing: 4) {
                if !model.photos.isEmpty {
                    if verticalSizeClass == .compact || dynamicTypeSize.isAccessibilitySize {
                        Button("管理已选照片（\(model.photos.count)/9）") { managingPhotos = true }
                            .font(JournalTheme.font(14)).frame(minHeight: 44)
                            .accessibilityIdentifier("chat.managePhotos")
                    } else {
                        selectedPhotoStrip.padding(.top, 8)
                    }
                }
                if dynamicTypeSize.isAccessibilitySize {
                    inputField.padding(.horizontal, 16).padding(.top, 8)
                    HStack(spacing: 8) { photoPicker; Spacer(); dictationButton; if hasSendContent { sendButton } }
                } else {
                    HStack(spacing: 8) { photoPicker; inputField; dictationButton; if hasSendContent { sendButton } }
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 6)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 20))
            .padding(.horizontal, 24)
        }.padding(.top, 12).padding(.bottom, 12).background(JournalTheme.paper)
    }

    private var hasSendContent: Bool {
        !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !model.photos.isEmpty || model.hasPendingSend
    }

    private var inputField: some View {
        TextField(model.photos.isEmpty ? "继续讲讲那一天…" : "也可以写几句话…", text: $input, axis: .vertical)
            .font(JournalTheme.font(16)).lineLimit(1...4)
            .disabled(model.isLoading || model.hasPendingSend).focused($inputFocused).submitLabel(.send)
            .accessibilityLabel("讲述文字").accessibilityIdentifier("chat.input")
    }

    private var photoPicker: some View {
        PhotosPicker(selection: $photoItems, maxSelectionCount: max(1, 9 - model.photos.count), selectionBehavior: .ordered, matching: .images) {
            Image(systemName: "plus").font(.system(size: 20)).frame(width: 44, height: 44)
        }
        .disabled(model.photos.count >= 9 || readingPhotos || model.isLoading || model.hasPendingSend)
        .foregroundStyle(JournalTheme.muted).accessibilityLabel("添加照片")
        .accessibilityHint("每条消息最多九张照片，已选 \(model.photos.count) 张")
        .accessibilityIdentifier("chat.addPhotos")
    }

    private var dictationButton: some View {
        Button {
            inputFocused = false
            if dictation.isRecording { dictation.stop() } else { Task { await dictation.start() } }
        } label: {
            Image(systemName: dictation.isRecording ? "stop.circle.fill" : "mic")
                .font(.system(size: 20)).frame(width: 44, height: 44)
        }
        .foregroundStyle(JournalTheme.ink).disabled(model.isLoading || model.hasPendingSend)
        .accessibilityLabel(dictation.isRecording ? "停止语音输入" : "语音输入")
    }

    private var sendButton: some View {
        Button { Task { await send() } } label: {
            Image(systemName: "arrow.up").font(.system(size: 19, weight: .medium))
                .foregroundStyle(JournalTheme.surface).frame(width: 36, height: 36)
                .background(JournalTheme.accent, in: Circle()).frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .disabled(model.isLoading || readingPhotos).opacity(model.isLoading || readingPhotos ? 0.45 : 1)
        .accessibilityLabel(model.hasPendingSend ? "重试发送" : "发送").accessibilityIdentifier("chat.send")
    }

    private var selectedPhotoStrip: some View {
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 8) {
                ForEach(Array(model.photos.enumerated()), id: \.element.id) { index, photo in
                    JournalSelectedPhoto(photo: photo, index: index, disabled: model.isLoading || model.hasPendingSend) {
                        Task { await model.removePhoto(id: photo.id) }
                    }
                }
            }.padding(.horizontal, 8)
        }
        .scrollIndicators(.hidden).accessibilityIdentifier("chat.selectedPhotos")
    }
    /// 复用当前会话重新生成草稿，更新失败时保留编辑内容供用户重试。
    private func updateDraft() async {
        guard let snapshot = await model.send(text: "请根据以下由我修订的内容更新回忆，保留事实，不要编造：\n" + editText, person: person) else { return }
        messages = snapshot.messages
        if let updated = await model.generate() { draft = updated; showingEdit = false }
    }
    private func start() async {
        guard messages.isEmpty else { return }
        if let snapshot = await model.start(person: person) { messages = snapshot.messages }
        #if DEBUG
        if previewScreen == "review" { await generate() }
        #endif
    }
    private func send() async {
        dictation.stop()
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !readingPhotos, !text.isEmpty || !model.photos.isEmpty else { return }
        guard let snapshot = await model.send(text: text, person: person) else {
            if let saved = model.latestSnapshot { messages = saved.messages }
            return
        }
        messages = snapshot.messages; input = ""; inputFocused = false
    }
    private func generate() async {
        dictation.stop()
        inputFocused = false
        if let value = await model.generate() {
            if let attachment = messages.flatMap(\.attachments).first { imageData = try? await chatAPI.loadPhoto(attachment) }
            draft = value; showingDraft = true
        }
    }
}

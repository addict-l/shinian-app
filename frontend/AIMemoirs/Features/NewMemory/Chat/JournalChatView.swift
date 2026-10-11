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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var messages: [ChatMessage] { model.messages }
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

    init(person: FamilyMember, chatAPI: any ChatAPI, memoryAPI: any MemoryAPI, previewScreen: String?, resumedDraft: LocalChatDraft? = nil, onBack: @escaping () -> Void, onSaved: @escaping () async -> Void) {
        self.person = person; self.chatAPI = chatAPI; self.previewScreen = previewScreen; self.onBack = onBack; self.onSaved = onSaved
        _model = StateObject(wrappedValue: ChatViewModel(api: chatAPI, store: ChatDraftStore.current(previewScreen: previewScreen), draft: resumedDraft, person: person))
        _saveModel = StateObject(wrappedValue: MemorySaveViewModel(api: memoryAPI))
    }
    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                if verticalSizeClass == .compact {
                    Text("关于\(person.relationship.isEmpty ? person.name : person.relationship) · \(person.name)")
                        .font(JournalTheme.font(14)).lineLimit(1)
                        .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                } else {
                    VStack(spacing: 5) {
                        Text("关于\(person.relationship.isEmpty ? person.name : person.relationship)").font(JournalTheme.font(16, medium: true))
                        Text(person.name).font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted)
                    }
                }
                HStack {
                    Button { dictation.cancel(); model.pause(); onBack() } label: { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                        .foregroundStyle(JournalTheme.ink).accessibilityLabel("暂停并返回选择家人").accessibilityIdentifier("newMemory.step.1")
                    Spacer()
                }
            }.frame(minHeight: verticalSizeClass == .compact ? 44 : 77).padding(.horizontal, 12)
            ScrollViewReader { reader in
                ScrollView {
                    VStack(alignment: .leading, spacing: 34) {
                        ForEach(messages) { message in
                            messageView(message).id(message.id)
                        }
                        if model.isLoading { ProgressView(model.progressText).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted) }
                        if let error = model.errorMessage { JournalError(message: error, retryTitle: model.hasPendingSend ? "重试这条讲述" : "重试") { Task { if model.hasPendingSend { await send() } else if model.latestSnapshot == nil || model.canGenerate == false { await start() } else if !model.inputText.isEmpty || !model.photos.isEmpty { await send() } else { await generate() } } } }
                        if let error = model.storageError { JournalError(message: error, retryTitle: "重试本机保存") { model.retryLocalSave() } }
                        if model.isCompleted && model.storageError == nil && (!model.inputText.isEmpty || model.hasPendingSend || !model.photos.isEmpty) {
                            JournalButton(title: "继续聊天", secondary: true) { Task { await model.startNewWithLocalContent(person: person) } }
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(.horizontal, 24).padding(.top, 28).padding(.bottom, 16)
                }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
                    .accessibilityIdentifier("chat.history")
                    .onChange(of: messages.last?.id) { _, _ in
                        if reduceMotion { reader.scrollTo("bottom", anchor: .bottom) }
                        else { withAnimation { reader.scrollTo("bottom", anchor: .bottom) } }
                    }
            }
            composer.fixedSize(horizontal: false, vertical: true)
                .dynamicTypeSize(...(verticalSizeClass == .compact ? DynamicTypeSize.accessibility1 : DynamicTypeSize.accessibility5))
        }
        .task { await start() }
        .onDisappear { dictation.cancel(); model.pause() }
        .onChange(of: navigation.tab) { _, tab in if tab != .compose { dictation.cancel(); model.pause() } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { dictation.cancel(); model.pause() } }
        .onChange(of: dictation.transcript) { _, text in model.inputText = text }
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
                        model.finish(); showingDraft = false
                        _ = await model.beginNextStory(person: person)
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
            JournalUserMessage(message: message, api: chatAPI,
                               localPhotos: model.pendingUserMessage?.id == message.id && message.attachments.isEmpty ? model.photos : []) {
                previewPhoto = $0
            }
        } else {
            VStack(alignment: .leading, spacing: 16) {
                Text(message.id == model.openingNotice.id ? "开始讲述" : "AI  回忆助手").font(JournalTheme.font(11, medium: true)).foregroundStyle(JournalTheme.accent)
                Text(message.text).font(JournalTheme.font(16)).lineSpacing(8).fixedSize(horizontal: false, vertical: true)
                if model.generationOfferMessageID == message.id && model.photos.isEmpty && !model.hasPendingSend && model.inputText.isEmpty && !dictation.isBusy {
                    VStack(alignment: .leading, spacing: 12) {
                        JournalButton(title: "整理成一段回忆", secondary: true, loading: model.isLoading) { Task { await generate() } }
                            .accessibilityIdentifier("chat.generate")
                            .accessibilityHint("先生成草稿，查看并确认后再保存")
                        Text("先看看草稿，确认后再保存。")
                            .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }.padding(.top, 4)
                }
            }
        }
    }
    private var composer: some View {
        VStack(spacing: 10) {
            if dictation.isBusy { Text(dictation.statusText).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.accent).accessibilityIdentifier("chat.dictationStatus") }
            if readingPhotos { ProgressView("正在读取与压缩照片…") }
            VStack(spacing: 4) {
                if !model.photos.isEmpty && !model.hasPendingSend {
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
        !model.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !model.photos.isEmpty || model.hasPendingSend
    }

    private var inputField: some View {
        TextField(model.photos.isEmpty ? "继续讲讲那一天…" : "也可以写几句话…", text: $model.inputText, axis: .vertical)
            .font(JournalTheme.font(16)).lineLimit(1...4)
            .disabled((model.isLoading && model.latestSnapshot != nil) || model.hasPendingSend || dictation.isBusy || model.isCompleted).focused($inputFocused).submitLabel(.send)
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
            if dictation.phase == .preparing { dictation.cancel() } else if dictation.isRecording { dictation.stop() } else { Task { await dictation.start(existingText: model.inputText) } }
        } label: {
            Image(systemName: dictation.isRecording ? "stop.circle.fill" : "mic")
                .font(.system(size: 20)).frame(width: 44, height: 44)
        }
        .foregroundStyle(JournalTheme.ink).disabled((model.isLoading && model.latestSnapshot != nil) || model.hasPendingSend || model.isCompleted || dictation.phase == .finishing)
        .accessibilityLabel(dictation.isRecording ? "停止语音输入" : dictation.phase == .preparing ? "取消准备语音" : "语音输入").accessibilityIdentifier("chat.dictation")
    }

    private var sendDisabled: Bool { model.isLoading || readingPhotos || dictation.isBusy || model.isCompleted }
    private var sendButton: some View {
        Button { Task { await send() } } label: {
            Image(systemName: "arrow.up").font(.system(size: 19, weight: .medium))
                .foregroundStyle(JournalTheme.surface).frame(width: 36, height: 36)
                .background(JournalTheme.accent, in: Circle()).frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .disabled(sendDisabled).opacity(sendDisabled ? 0.45 : 1)
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
        guard await model.send(text: "请根据以下由我修订的内容更新回忆，保留事实，不要编造：\n" + editText, person: person) != nil else { return }
        if let updated = await model.generate() { draft = updated; showingEdit = false }
    }
    private func start() async {
        _ = await model.start(person: person)
        #if DEBUG
        if previewScreen == "review" { await generate() }
        #endif
    }
    private func send() async {
        dictation.stop()
        let text = model.pendingText ?? model.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !readingPhotos, !model.isLoading, !text.isEmpty || !model.photos.isEmpty || model.hasPendingSend else { return }
        inputFocused = false
        if await model.send(text: text, person: person) == nil && !model.hasPendingSend {
            // Validation/rejection returns editable text; transient failures keep
            // the pending message in the conversation and retry its original ID.
            model.inputText = text
        }
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

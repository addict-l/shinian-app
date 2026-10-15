import SwiftUI
import PhotosUI

/// 对话页面：协调输入、附件和草稿预览；远端会话与保存状态由独立 ViewModel 管理。
struct JournalChatView: View {
    let person: FamilyMember
    private let chatAPI: any ChatAPI
    private let memoryAPI: any MemoryAPI
    let previewScreen: String?
    let onBack: () -> Void
    let onSaved: () async -> Void
    @StateObject private var model: ChatViewModel
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
    @State private var draftPreview: JournalDraftPresentation?
    @State private var preparingDraft = false
    @State private var mediaError: String?
    @FocusState private var inputFocused: Bool
    @State private var openedAt = Date()
    @State private var lifePresented = false

    init(person: FamilyMember, chatAPI: any ChatAPI, memoryAPI: any MemoryAPI, previewScreen: String?, resumedDraft: LocalChatDraft? = nil, onBack: @escaping () -> Void, onSaved: @escaping () async -> Void) {
        self.person = person; self.chatAPI = chatAPI; self.memoryAPI = memoryAPI; self.previewScreen = previewScreen; self.onBack = onBack; self.onSaved = onSaved
        _model = StateObject(wrappedValue: ChatViewModel(api: chatAPI, store: ChatDraftStore.current(previewScreen: previewScreen), draft: resumedDraft, person: person))
    }
    private var personTitle: String {
        person.relationship.isEmpty ? "关于\(person.name)" : "关于\(person.relationship) · \(person.name)"
    }
    private var offersGeneration: Bool {
        guard let id = model.generationOfferMessageID, messages.contains(where: { $0.id == id }) else { return false }
        return model.photos.isEmpty && !model.hasPendingSend && model.inputText.isEmpty && !dictation.isBusy
    }
    var body: some View {
        Group {
            if previewScreen == nil, model.latestSnapshot == nil {
                initialLoading
            } else if needsInitialLifeInterview, let snapshot = model.latestSnapshot {
                LifeInterviewView(person: person, api: chatAPI, snapshot: snapshot,
                    onUpdated: { model.receiveInterviewSnapshot($0) },
                    onClose: onBack,
                    onEnter: { model.receiveInterviewSnapshot($0) })
            } else {
                conversation
            }
        }
        .task { await start() }
        .onDisappear { dictation.cancel(); model.pause() }
        .onChange(of: navigation.tab) { _, tab in if tab != .compose { dictation.cancel(); model.pause() } }
        .onChange(of: scenePhase) { _, phase in if phase != .active { dictation.cancel(); model.pause() } }
    }

    private var needsInitialLifeInterview: Bool {
        previewScreen == nil && model.latestSnapshot?.lifeOverview?.required == true &&
            model.latestSnapshot?.information.guided_interview?.module_selected == false
    }

    private var initialLoading: some View {
        VStack(spacing: 20) {
            HStack {
                JournalRoundButton(icon: "back", label: "返回选择家人", action: onBack)
                    .accessibilityIdentifier("newMemory.step.1")
                Spacer()
            }.padding(.horizontal, 16)
            Spacer()
            if let error = model.storageError ?? model.errorMessage {
                JournalError(message: error, retryTitle: "重试") {
                    model.retryLocalSave()
                    Task { await start() }
                }
            } else {
                ProgressView("正在打开记录…")
                    .accessibilityIdentifier("chat.initialLoading")
            }
            Spacer()
        }.padding(.vertical, 12)
    }

    private var conversation: some View {
        VStack(spacing: 0) {
            ZStack {
                if verticalSizeClass == .compact {
                    Text(personTitle).font(JournalTheme.font(14, medium: true)).lineLimit(1)
                        .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                } else {
                    VStack(spacing: 2) {
                        Text(personTitle).font(JournalTheme.font(15.5, medium: true)).foregroundStyle(JournalTheme.ink).lineLimit(1)
                        HStack(spacing: 4) {
                            Circle().fill(JournalTheme.sage).frame(width: 6, height: 6).accessibilityHidden(true)
                            Text("AI 回忆助手").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        }
                    }.padding(.horizontal, 56)
                }
                HStack {
                    JournalRoundButton(icon: "back", label: "暂停并返回选择家人") { dictation.cancel(); model.pause(); onBack() }
                        .accessibilityIdentifier("newMemory.step.1")
                    Spacer()
                    if verticalSizeClass != .compact { JournalAvatar(person: person, size: 40) }
                }
            }.frame(height: verticalSizeClass == .compact ? 44 : 58).padding(.horizontal, 14)
            .overlay(alignment: .bottom) { JournalTheme.line.frame(height: 1) }
            if model.latestSnapshot?.lifeOverview != nil {
                Button("人生概览") { lifePresented = true }
                    .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .accessibilityIdentifier("chat.lifeOverview")
            }
            ScrollViewReader { reader in
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if !messages.isEmpty {
                            Text(previewScreen == "chat" ? "10月12日 上午 8:20" : JournalFormat.chatDate(openedAt))
                                .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).frame(maxWidth: .infinity)
                                .padding(.bottom, -2)
                        }
                        ForEach(messages) { message in
                            messageView(message).id(message.id)
                        }
                        if model.isLoading || previewScreen == "chat" {
                            HStack(spacing: 6) {
                                Circle().fill(JournalTheme.accent).frame(width: 6, height: 6)
                                Circle().fill(JournalTheme.accent.opacity(0.6)).frame(width: 6, height: 6)
                                Circle().fill(JournalTheme.accent.opacity(0.3)).frame(width: 6, height: 6)
                                Text(previewScreen == "chat" || model.progressText.isEmpty ? "正在倾听与整理…" : model.progressText)
                            }.font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.leading, 38).padding(.top, -2)
                                .accessibilityElement(children: .combine)
                        }
                        if let error = model.errorMessage { JournalError(message: error, retryTitle: model.hasPendingSend ? "重试这条讲述" : "重试") { Task { if model.hasPendingSend { await send() } else if model.latestSnapshot == nil || model.canGenerate == false { await start() } else if !model.inputText.isEmpty || !model.photos.isEmpty { await send() } else { await generate() } } } }
                        if let error = model.storageError { JournalError(message: error, retryTitle: "重试本机保存") { model.retryLocalSave() } }
                        if model.isCompleted && model.storageError == nil && (!model.inputText.isEmpty || model.hasPendingSend || !model.photos.isEmpty) {
                            JournalButton(title: "继续聊天", secondary: true) { Task { await model.startNewWithLocalContent(person: person) } }
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(.horizontal, JournalTheme.gutter).padding(.top, 14).padding(.bottom, 16)
                }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
                    .accessibilityIdentifier("chat.history")
                    .onChange(of: messages.last?.id) { _, _ in
                        if reduceMotion { reader.scrollTo("bottom", anchor: .bottom) }
                        else { withAnimation { reader.scrollTo("bottom", anchor: .bottom) } }
                    }
                    .safeAreaInset(edge: .bottom, spacing: 0) {
                        composer.fixedSize(horizontal: false, vertical: true)
                            .dynamicTypeSize(...(verticalSizeClass == .compact ? DynamicTypeSize.accessibility1 : DynamicTypeSize.accessibility5))
                    }
            }
        }
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
        .fullScreenCover(isPresented: $lifePresented) {
            if let snapshot = model.latestSnapshot {
                LifeInterviewView(person: person, api: chatAPI, snapshot: snapshot,
                    onUpdated: { model.receiveInterviewSnapshot($0) },
                    onClose: { lifePresented = false },
                    onEnter: { model.receiveInterviewSnapshot($0); lifePresented = false })
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
        .fullScreenCover(item: $draftPreview) { presentation in
            JournalDraftPreviewView(presentation: presentation,
                identity: "\(person.relationship) · \(person.name)", api: memoryAPI,
                onBack: { draftPreview = nil },
                onSaved: {
                    model.finish(); draftPreview = nil
                    _ = await model.beginNextStory(person: person)
                    await onSaved()
                })
        }
    }
    @ViewBuilder private func messageView(_ message: ChatMessage) -> some View {
        if message.sender == .user {
            JournalUserMessage(message: message, api: chatAPI,
                               localPhotos: model.pendingUserMessage?.id == message.id && message.attachments.isEmpty ? model.photos : []) {
                previewPhoto = $0
            }
        } else {
            HStack(alignment: .top, spacing: 8) {
                DesignIcon("spark", size: 16).foregroundStyle(JournalTheme.butterInk)
                    .frame(width: 30, height: 30).background(JournalTheme.butterSoft, in: Circle()).accessibilityHidden(true)
                Text(message.text).font(JournalTheme.story(14.5)).lineSpacing(4).foregroundStyle(JournalTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 14).padding(.vertical, 12)
                    .background(JournalTheme.surface, in: UnevenRoundedRectangle(topLeadingRadius: 4, bottomLeadingRadius: 20, bottomTrailingRadius: 20, topTrailingRadius: 20))
                    .overlay { UnevenRoundedRectangle(topLeadingRadius: 4, bottomLeadingRadius: 20, bottomTrailingRadius: 20, topTrailingRadius: 20).stroke(JournalTheme.line, lineWidth: 1) }
                    .frame(maxWidth: 272, alignment: .leading)
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            .padding(.top, 0)
        }
    }

    /// 浮在输入框上方的“整理成一段回忆”胶囊。
    private var generatePill: some View {
        Button { Task { await generate() } } label: {
            HStack(spacing: 8) {
                if model.isLoading { ProgressView().tint(JournalTheme.accentDeep) } else { DesignIcon("book", size: 18) }
                Text("整理成一段回忆").font(JournalTheme.font(14))
                Text("· 先看草稿再保存").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.leading, 2)
            }
            .foregroundStyle(JournalTheme.accentDeep)
            .padding(.horizontal, 18).frame(height: 42)
            .background(JournalTheme.surface, in: Capsule())
            .overlay { Capsule().stroke(JournalTheme.soft, lineWidth: 1.5) }
            .shadow(color: JournalTheme.shadow.opacity(0.08), radius: 7, x: 0, y: 4)
            .contentShape(Capsule())
        }
        .buttonStyle(JournalActionButtonStyle()).disabled(model.isLoading)
        .accessibilityIdentifier("chat.generate")
        .accessibilityHint("先生成草稿，查看并确认后再保存")
    }

    private var composer: some View {
        VStack(spacing: 10) {
            if offersGeneration { generatePill.padding(.bottom, 14) }
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
                    HStack(spacing: 8) { photoPicker; Spacer(); dictationButton; sendButton }
                } else {
                    HStack(spacing: 8) { photoPicker; inputField; dictationButton; sendButton }
                }
            }
            .padding(.leading, 6).padding(.trailing, 4).padding(.vertical, 4)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: 28, style: .continuous).stroke(JournalTheme.line, lineWidth: 1) }
            .journalLiftedShadow()
            .padding(.horizontal, 16)
        }
        .padding(.top, 12).padding(.bottom, 8)
        .background {
            LinearGradient(stops: [.init(color: JournalTheme.paper.opacity(0), location: 0), .init(color: JournalTheme.paper, location: offersGeneration ? 0.45 : 0.3)],
                           startPoint: .top, endPoint: .bottom).ignoresSafeArea(edges: .bottom).allowsHitTesting(false)
        }
    }

    private var hasSendContent: Bool {
        !model.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !model.photos.isEmpty || model.hasPendingSend
    }

    private var inputField: some View {
        TextField("", text: $model.inputText, prompt: Text(model.photos.isEmpty ? "继续讲讲那一天…" : "也可以写几句话…").foregroundStyle(JournalTheme.placeholder), axis: .vertical)
            .font(JournalTheme.font(15)).foregroundStyle(JournalTheme.ink).lineLimit(1...4)
            .disabled((model.isLoading && model.latestSnapshot != nil) || model.hasPendingSend || dictation.isBusy || model.isCompleted).focused($inputFocused).submitLabel(.send)
            .accessibilityLabel("讲述文字").accessibilityIdentifier("chat.input")
    }

    private var photoPicker: some View {
        PhotosPicker(selection: $photoItems, maxSelectionCount: max(1, 9 - model.photos.count), selectionBehavior: .ordered, matching: .images) {
            DesignIcon("image")
                .frame(width: 40, height: 40).background(JournalTheme.paper2, in: Circle())
                .frame(width: 44, height: 44)
        }
        .disabled(model.photos.count >= 9 || readingPhotos || model.isLoading || model.hasPendingSend)
        .foregroundStyle(JournalTheme.secondaryInk).accessibilityLabel("添加照片")
        .accessibilityHint("每条消息最多九张照片，已选 \(model.photos.count) 张")
        .accessibilityIdentifier("chat.addPhotos")
    }

    private var dictationButton: some View {
        Button {
            inputFocused = false
            if dictation.phase == .preparing { dictation.cancel() } else if dictation.isRecording { dictation.stop() } else { Task { await dictation.start(existingText: model.inputText) } }
        } label: {
            Group {
                if dictation.isRecording { Image(systemName: "stop.circle.fill").font(.system(size: 22)).foregroundStyle(JournalTheme.accent) }
                else { DesignIcon("mic") }
            }.frame(width: 44, height: 44)
        }
        .foregroundStyle(JournalTheme.ink2).disabled((model.isLoading && model.latestSnapshot != nil) || model.hasPendingSend || model.isCompleted || dictation.phase == .finishing)
        .accessibilityLabel(dictation.isRecording ? "停止语音输入" : dictation.phase == .preparing ? "取消准备语音" : "语音输入").accessibilityIdentifier("chat.dictation")
    }

    private var sendDisabled: Bool { model.isLoading || readingPhotos || dictation.isBusy || model.isCompleted }
    private var sendButton: some View {
        Button { Task { await send() } } label: {
            DesignIcon("up")
                .foregroundStyle(.white).frame(width: 40, height: 40)
                .background(JournalTheme.accent, in: Circle())
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .disabled(sendDisabled || !hasSendContent).opacity(sendDisabled ? 0.45 : 1)
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
    private func start() async {
        _ = await model.start(person: person)
        if previewScreen == "review" { await generate() }
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
        guard !preparingDraft, draftPreview == nil else { return }
        preparingDraft = true
        defer { preparingDraft = false }
        if let value = await model.generate() {
            // The server replays an unchanged draft (including manual edits), or
            // generates from the current story. A local preview may belong to
            // an earlier saved story or an earlier version of this dialogue.
            var imageData: Data?
            let currentIDs = Set(model.latestSnapshot?.currentMessageIDs ?? messages.map(\.id))
            if let attachment = messages.filter({ currentIDs.contains($0.id) }).flatMap(\.attachments).first {
                imageData = try? await chatAPI.loadPhoto(attachment)
            }
            draftPreview = JournalDraftPresentation(draft: value, imageData: imageData)
        }
    }
}

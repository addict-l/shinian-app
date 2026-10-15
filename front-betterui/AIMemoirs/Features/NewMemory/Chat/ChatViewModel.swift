import SwiftUI

struct MessagePhoto: Identifiable {
    enum Status { case selected, uploading, uploaded, failed }
    let id: UUID
    let data: Data
    let thumbnail: UIImage?
    var attachment: ChatAttachment?
    var status: Status = .selected
    init(id: UUID = UUID(), data: Data, attachment: ChatAttachment? = nil) {
        self.id = id; self.data = data; self.attachment = attachment
        thumbnail = PhotoCompression.thumbnail(data); status = attachment == nil ? .selected : .uploaded
    }
}

/// Retains partial uploads and stable message identities until the complete send succeeds.
@MainActor final class ChatViewModel: ObservableObject {
    @Published private(set) var isLoading = false
    @Published private(set) var canGenerate = false
    @Published private(set) var generationOfferMessageID: UUID?
    @Published private(set) var photos: [MessagePhoto] = []
    @Published private(set) var hasPendingSend = false
    @Published private(set) var progressText = "正在倾听与整理…"
    @Published private(set) var latestSnapshot: ChatSnapshot?
    @Published private(set) var pendingUserMessage: ChatMessage?
    @Published var errorMessage: String?
    @Published var inputText = "" { didSet { if inputText != oldValue { _ = persist() } } }
    @Published private(set) var storageError: String?
    @Published private(set) var isCompleted = false
    private let store: ChatDraftStore?
    private var localDraft: LocalChatDraft?
    private var unreadablePhotos = false
    private var hydrating = true
    private var switchingStory = false
    private let api: any ChatAPI
    private var sessionID: UUID?
    private var startID = UUID()
    private var pendingMessage: (text: String, id: UUID, attachments: [UUID])?
    private var preparedOpening: ChatMessage?

    init(api: (any ChatAPI)? = nil, store: ChatDraftStore? = nil, draft: LocalChatDraft? = nil, person: FamilyMember? = nil) {
        self.api = api ?? BackendRepository.shared; self.store = store
        if person?.hasChatHistory == false { preparedOpening = person?.openingMessage }
        var draft = draft
        if draft == nil, let person {
            do { draft = try store?.draft(for: person.id) }
            catch { unreadablePhotos = true; storageError = "本机聊天暂时无法读取，原文件仍保留。请稍后重新进入。" }
        }
        localDraft = draft
        if let draft {
            startID = draft.id; sessionID = draft.sessionID; inputText = draft.input == draft.pendingText ? "" : draft.input
            latestSnapshot = draft.snapshot
            if let id = draft.pendingMessageID, let text = draft.pendingText {
                pendingMessage = (text, id, draft.pendingAttachments)
                pendingUserMessage = ChatMessage(id: id, sender: .user, text: text)
                hasPendingSend = true
            }
            do { photos = try store?.photos(for: draft) ?? [] }
            catch { unreadablePhotos = true; storageError = "本机照片暂时无法读取，原文件仍保留，请重试读取。" }
        }
        hydrating = false
        if let person { prepare(person) }
    }

    private func prepare(_ person: FamilyMember) {
        if localDraft == nil {
            localDraft = LocalChatDraft(id: person.id, sessionID: sessionID, personID: person.id,
                personName: person.name, relationship: person.relationship)
        }
    }
    @discardableResult private func persist() -> Bool {
        guard !hydrating else { return true }
        guard !unreadablePhotos else { return false }
        guard let store, var draft = localDraft else { return true }
        draft.sessionID = sessionID; draft.input = inputText; draft.snapshot = latestSnapshot
        draft.pendingText = pendingMessage?.text; draft.pendingMessageID = pendingMessage?.id
        draft.pendingAttachments = pendingMessage?.attachments ?? []
        draft.photos = photos.map { StoredChatPhoto(id: $0.id, attachment: $0.attachment) }
        draft.updatedAt = Date()
        do { try store.save(draft, photos: photos); localDraft = draft; storageError = nil; return true }
        catch { storageError = "未能保存本机待发送内容，请检查设备存储空间并重试；当前内容仍在此页面。"; return false }
    }
    func pause() { _ = persist() }
    func retryLocalSave() {
        if unreadablePhotos, let draft = localDraft {
            do { photos = try store?.photos(for: draft) ?? []; unreadablePhotos = false }
            catch { return }
        }
        _ = persist()
    }
    func finish() {
        isCompleted = true; canGenerate = false; generationOfferMessageID = nil
        guard let id = localDraft?.id else { return }
        do { try store?.remove(id: id); localDraft = nil }
        catch { storageError = "回忆已保存，但本机缓存清理失败。" }
    }

    private func clearPending() {
        pendingMessage = nil; pendingUserMessage = nil; hasPendingSend = false; photos = []
    }
    private func reconcile(_ value: ChatSnapshot) {
        let ids = value.currentMessageIDs ?? value.messages.map(\.id)
        if let pending = pendingMessage, let index = ids.firstIndex(of: pending.id), index + 1 < ids.count {
            clearPending(); errorMessage = nil
        }
        // Another device can resume the exact unanswered message, including its attachments.
        if pendingMessage == nil, let latest = value.messages.last, latest.sender == .user,
           ids.contains(latest.id), value.status != "completed" {
            pendingMessage = (latest.text, latest.id, latest.attachments.map(\.id))
            pendingUserMessage = latest; hasPendingSend = true
            errorMessage = "上次讲述已保存，回复尚未完成。点击重试继续，不会重复保存。"
        }
    }

    /// The server uses the client request ID as the user message ID. A recovered
    /// snapshot replaces the local echo, including when only the reply was lost.
    var messages: [ChatMessage] {
        // Reuse the server's prepared message ID while history is loading.
        // A known existing conversation never gets a new placeholder welcome.
        let history = latestSnapshot?.messages ?? []
        let saved = history.isEmpty ? preparedOpening.map { [$0] } ?? [] : history
        guard let pendingUserMessage, !saved.contains(where: { $0.id == pendingUserMessage.id }) else { return Array(saved.suffix(20)) }
        return Array((saved + [pendingUserMessage]).suffix(20))
    }
    var pendingText: String? { pendingMessage?.text }

    func reset() {
        pause(); localDraft = nil; preparedOpening = nil; inputText = ""; isCompleted = false
        sessionID = nil; startID = UUID(); pendingMessage = nil; pendingUserMessage = nil; photos = []
        canGenerate = false; generationOfferMessageID = nil; hasPendingSend = false; latestSnapshot = nil
    }
    func startNewWithLocalContent(person: FamilyMember) async {
        _ = await beginNextStory(person: person)
    }
    @discardableResult func beginNextStory(person: FamilyMember) async -> ChatSnapshot? {
        guard !switchingStory else { return nil }
        switchingStory = true
        let wasLoading = isLoading; isLoading = true; progressText = "正在恢复聊天…"
        defer { switchingStory = false; isLoading = wasLoading }
        let text = [inputText, pendingText ?? ""].filter { !$0.isEmpty }.joined(separator: "\n")
        let retainedPhotos = photos.map { MessagePhoto(data: $0.data) }
        do {
            let value = try await api.start(person: person, requestID: startID)
            // Only clear obsolete pending identities after the server provides a new segment.
            // Opening a segment never sends local input or photos.
            guard value.status != "completed" else { return nil }
            clearPending(); photos = retainedPhotos; inputText = text
            localDraft?.sessionID = value.sessionID; sessionID = value.sessionID; prepare(person)
            reconcile(value); errorMessage = nil
            return accept(value)
        } catch { errorMessage = error.localizedDescription; return nil }
    }
    func appendPhotos(_ data: [Data]) throws {
        guard !isLoading, !hasPendingSend else { throw APIError.server("请先完成当前消息的发送或重试。") }
        guard photos.count + data.count <= 9 else { throw APIError.server("每条消息最多 9 张照片，更多照片可以分多条发送。") }
        guard data.allSatisfy({ !$0.isEmpty && $0.count <= 8 * 1024 * 1024 }) else { throw APIError.server("每张照片压缩后不能超过 8 MB。") }
        photos.append(contentsOf: data.map { MessagePhoto(data: $0) }); _ = persist()
    }
    func removePhoto(id: UUID) async {
        guard !isLoading, !hasPendingSend, let photo = photos.first(where: { $0.id == id }) else { return }
        isLoading = true; errorMessage = nil; progressText = "正在移除未发送的照片…"
        defer { isLoading = false }
        do {
            if photo.attachment != nil, let sessionID { try await api.removePhoto(sessionID: sessionID, id: id) }
            photos.removeAll { $0.id == id }; _ = persist()
        } catch { errorMessage = error.localizedDescription }
    }
    func receiveInterviewSnapshot(_ value: ChatSnapshot) { _ = accept(value) }
    private func accept(_ value: ChatSnapshot) -> ChatSnapshot {
        var value = value; value.messages = Array(value.messages.suffix(20))
        sessionID = value.sessionID; canGenerate = value.canGenerate; latestSnapshot = value
        isCompleted = value.status == "completed"; _ = persist()
        let offerID = value.generationOffer?.message_id
        generationOfferMessageID = value.canGenerate && value.messages.last?.sender == .ai && value.messages.last?.id == offerID ? offerID : nil
        return value
    }
    func start(person: FamilyMember) async -> ChatSnapshot? {
        guard !isLoading else { return nil }
        isLoading = true; errorMessage = nil; progressText = "正在打开故事…"
        defer { isLoading = false }
        prepare(person)
        guard persist() else { return nil }
        do {
            let value: ChatSnapshot
            if let sessionID {
                value = try await api.resume(sessionID: sessionID)
                // Old clients can leave a cached empty session. Reading it does
                // not publish a prepared welcome or generate a missing legacy one.
                // Re-enter through the idempotent member endpoint in that case.
                if value.messages.isEmpty { return await beginNextStory(person: person) }
            }
            else { value = try await api.start(person: person, requestID: startID) }
            reconcile(value)
            let accepted = accept(value)
            if isCompleted { return await beginNextStory(person: person) }
            return accepted
        }
        catch is CancellationError { return nil }
        catch { errorMessage = error.localizedDescription; return nil }
    }
    func send(text: String, person: FamilyMember) async -> ChatSnapshot? {
        guard !isCompleted else { errorMessage = "这段回忆已保存，请开始新的故事。"; return nil }
        prepare(person)
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count <= 12000 else { errorMessage = "单条文字最多 12000 字，请分多条发送。"; return nil }
        guard !text.isEmpty || !photos.isEmpty || pendingMessage != nil else { errorMessage = "请先写下文字或选择照片。"; return nil }
        guard !isLoading else { return nil }
        if let pendingMessage, pendingMessage.text != text {
            errorMessage = "上一条消息尚未完成，请先重试。"; return nil
        }
        if pendingMessage == nil {
            let id = UUID()
            pendingMessage = (text, id, [])
            pendingUserMessage = ChatMessage(id: id, sender: .user, text: text)
        }
        hasPendingSend = true; generationOfferMessageID = nil
        guard persist() else { return nil }
        inputText = ""
        if sessionID == nil, await start(person: person) == nil { return nil }
        guard let sessionID else { return nil }
        isLoading = true; errorMessage = nil; generationOfferMessageID = nil
        defer { isLoading = false }
        do {
            for index in photos.indices where photos[index].attachment == nil {
                progressText = "正在上传照片 \(index + 1)/\(photos.count)…"
                photos[index].status = .uploading
                do {
                    let photo = photos[index]
                    let result = try await api.uploadPhoto(sessionID: sessionID, image: photo.data, requestID: photo.id)
                    photos[index].attachment = result; photos[index].status = .uploaded
                    guard persist() else { return nil }
                } catch { photos[index].status = .failed; _ = persist(); throw error }
            }
            if !photos.isEmpty { pendingMessage?.attachments = photos.compactMap { $0.attachment?.id } }
            guard persist() else { return nil }
            guard let request = pendingMessage else { return nil }
            hasPendingSend = true
            progressText = text.isEmpty ? "正在保存照片消息…" : "正在倾听与整理…"
            let value = try await api.send(sessionID: sessionID, text: request.text,
                                          attachmentIDs: request.attachments, requestID: request.id)
            clearPending()
            return accept(value)
        } catch is CancellationError { _ = persist(); return nil }
        catch {
            errorMessage = error.localizedDescription
            if hasPendingSend, let value = try? await api.state(sessionID: sessionID) {
                reconcile(value); _ = accept(value)
                if !hasPendingSend { return value }
            }
            if case APIError.rejected = error { pendingMessage = nil; pendingUserMessage = nil; hasPendingSend = false; inputText = text }
            if case APIError.httpStatus(let status) = error, (400..<500).contains(status) { pendingMessage = nil; pendingUserMessage = nil; hasPendingSend = false; inputText = text }
            _ = persist()
            return nil
        }
    }
    func generate() async -> GeneratedMemory? {
        guard !isLoading, !hasPendingSend, photos.isEmpty, inputText.isEmpty, canGenerate, let sessionID else { return nil }
        isLoading = true; errorMessage = nil; progressText = "正在整理回忆草稿…"
        defer { isLoading = false }
        do { return try await api.generate(sessionID: sessionID) }
        catch is CancellationError { return nil }
        catch { errorMessage = error.localizedDescription; return nil }
    }
}

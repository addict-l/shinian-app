import SwiftUI

struct MessagePhoto: Identifiable {
    enum Status { case selected, uploading, uploaded, failed }
    let id = UUID()
    let data: Data
    let thumbnail: UIImage?
    var attachment: ChatAttachment?
    var status: Status = .selected
    init(data: Data) { self.data = data; thumbnail = PhotoCompression.thumbnail(data) }
}

/// Retains partial uploads and stable message identities until the complete send succeeds.
@MainActor final class ChatViewModel: ObservableObject {
    @Published private(set) var isLoading = false
    @Published private(set) var canGenerate = false
    @Published private(set) var photos: [MessagePhoto] = []
    @Published private(set) var hasPendingSend = false
    @Published private(set) var progressText = "正在倾听与整理…"
    @Published private(set) var latestSnapshot: ChatSnapshot?
    @Published var errorMessage: String?
    private let api: any ChatAPI
    private var sessionID: UUID?
    private var startID = UUID()
    private var pendingMessage: (text: String, id: UUID, attachments: [UUID])?

    init(api: (any ChatAPI)? = nil) { self.api = api ?? BackendRepository.shared }

    func reset() {
        sessionID = nil; startID = UUID(); pendingMessage = nil; photos = []
        canGenerate = false; hasPendingSend = false; latestSnapshot = nil
    }
    func appendPhotos(_ data: [Data]) throws {
        guard !isLoading, !hasPendingSend else { throw APIError.server("请先完成当前消息的发送或重试。") }
        guard photos.count + data.count <= 9 else { throw APIError.server("每条消息最多 9 张照片，更多照片可以分多条发送。") }
        guard data.allSatisfy({ !$0.isEmpty && $0.count <= 8 * 1024 * 1024 }) else { throw APIError.server("每张照片压缩后不能超过 8 MB。") }
        photos.append(contentsOf: data.map { MessagePhoto(data: $0) })
    }
    func removePhoto(id: UUID) async {
        guard !isLoading, !hasPendingSend, let photo = photos.first(where: { $0.id == id }) else { return }
        isLoading = true; errorMessage = nil; progressText = "正在移除未发送的照片…"
        defer { isLoading = false }
        do {
            if photo.attachment != nil, let sessionID { try await api.removePhoto(sessionID: sessionID, id: id) }
            photos.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }
    private func accept(_ value: ChatSnapshot) -> ChatSnapshot {
        sessionID = value.sessionID; canGenerate = value.canGenerate; latestSnapshot = value
        return value
    }
    func start(person: FamilyMember) async -> ChatSnapshot? {
        guard !isLoading else { return nil }
        isLoading = true; errorMessage = nil; progressText = "正在打开故事…"
        defer { isLoading = false }
        do { return accept(try await api.start(person: person, requestID: startID)) }
        catch is CancellationError { return nil }
        catch { errorMessage = error.localizedDescription; return nil }
    }
    func send(text: String, person: FamilyMember) async -> ChatSnapshot? {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count <= 12000 else { errorMessage = "单条文字最多 12000 字，请分多条发送。"; return nil }
        guard !text.isEmpty || !photos.isEmpty else { errorMessage = "请先写下文字或选择照片。"; return nil }
        if sessionID == nil, await start(person: person) == nil { return nil }
        guard !isLoading, let sessionID else { return nil }
        if let pendingMessage, pendingMessage.text != text {
            errorMessage = "上一条消息尚未完成，请先重试。"; return nil
        }
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            for index in photos.indices where photos[index].attachment == nil {
                progressText = "正在上传照片 \(index + 1)/\(photos.count)…"
                photos[index].status = .uploading
                do {
                    let photo = photos[index]
                    let result = try await api.uploadPhoto(sessionID: sessionID, image: photo.data, requestID: photo.id)
                    photos[index].attachment = result; photos[index].status = .uploaded
                } catch { photos[index].status = .failed; throw error }
            }
            if pendingMessage == nil { pendingMessage = (text, UUID(), photos.compactMap { $0.attachment?.id }) }
            guard let request = pendingMessage else { return nil }
            hasPendingSend = true
            progressText = text.isEmpty ? "正在保存照片消息…" : "正在倾听与整理…"
            let value = try await api.send(sessionID: sessionID, text: request.text,
                                          attachmentIDs: request.attachments, requestID: request.id)
            pendingMessage = nil; hasPendingSend = false; photos = []
            return accept(value)
        } catch is CancellationError { return nil }
        catch {
            errorMessage = error.localizedDescription
            if case APIError.rejected = error { pendingMessage = nil; hasPendingSend = false }
            if case APIError.httpStatus(let status) = error, (400..<500).contains(status) { pendingMessage = nil; hasPendingSend = false }
            if hasPendingSend, let value = try? await api.state(sessionID: sessionID) { _ = accept(value) }
            return nil
        }
    }
    func generate() async -> GeneratedMemory? {
        guard !isLoading, !hasPendingSend, photos.isEmpty, canGenerate, let sessionID else { return nil }
        isLoading = true; errorMessage = nil; progressText = "正在整理回忆草稿…"
        defer { isLoading = false }
        do { return try await api.generate(sessionID: sessionID) }
        catch is CancellationError { return nil }
        catch { errorMessage = error.localizedDescription; return nil }
    }
}
